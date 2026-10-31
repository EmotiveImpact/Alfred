"""Host restart and recovery, the doctor check and service-file text (RUN-001, M09).

ALFRED's host runs only while the foreground `serve` command is alive. A computer
can lose power, a terminal can be closed and a service manager can kill the process.
This module makes the next start honest about what that interrupted:

* A small private marker, `host-state.json` in the data directory, records each start
  and each clean stop. A start that finds the previous run without a clean stop
  reports an unclean stop. The marker holds no secrets, request text or note content.
* Questions still queued or running are marked `interrupted`, with a visible reason;
  they are never re-asked on the person's behalf.
* Jobs this host had started become `effect_unknown` and wait for the owner's
  reconciliation; they are never re-run blindly. A lease that never started ran
  nothing and returns to the queue.
* Routine slots that fell due while the host was stopped are counted. The routine
  itself still records them as missed and never turns downtime into a burst of runs.

`doctor` only reads. `service_file` only returns text. ALFRED never installs, loads,
enables or starts a background service, and refuses to write a service file straight
into a folder a service manager would load from.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import sqlite3
import stat
import sys
import time
from . import keys
from .local import Fault

STATE_FILE = 'host-state.json'
STATE_VERSION = 1
BACKUP_WARN_SECONDS = 7 * 86400
REPOSITORY = Path(__file__).resolve().parents[1]
LOCAL_WORKER = 'local-host'


# The clean-stop marker -------------------------------------------------------

def read_state(path):
    """The marker as written, or None when there is none. Unreadable markers are reported, not trusted."""
    file = Path(path) / STATE_FILE
    try:
        fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        return {'unreadable': True}  # For example a symbolic link, which is never followed.
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            return {'unreadable': True}
        value = json.loads(os.read(fd, 16385))
        return value if type(value) is dict and value.get('version') == STATE_VERSION else {'unreadable': True}
    except (OSError, ValueError):
        return {'unreadable': True}
    finally:
        os.close(fd)


def _write_state(path, value):
    """Atomic private replace, flushed, so a crash leaves the old or the new marker, never half of one."""
    path = Path(path)
    staging = path / (STATE_FILE + '.writing')
    staging.unlink(missing_ok=True)
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path / STATE_FILE)


def begin(path, clock=time.time):
    """Record this start and say how the previous run ended. Call only while holding the host lock."""
    previous = read_state(path)
    now = int(clock())
    if previous is None:
        status = 'first_start'
    elif previous.get('unreadable'):
        status = 'unknown'
    else:
        status = 'clean' if previous.get('clean_stop') is True else 'unclean'
    known = previous if previous and not previous.get('unreadable') else {}
    start = {'run': secrets.token_hex(8), 'started_at': now, 'previous_stop': status,
             'previous_started_at': known.get('started_at'),
             'previous_stopped_at': known.get('stopped_at') if status == 'clean' else None,
             'last_clean_stop': known.get('last_clean_stop')}
    _write_state(path, {'version': STATE_VERSION, 'run': start['run'], 'pid': os.getpid(), 'started_at': now,
                        'clean_stop': False, 'stopped_at': None, 'last_clean_stop': known.get('last_clean_stop'),
                        'last_recovery': known.get('last_recovery')})
    return start


def record_recovery(path, run, report):
    """Keep the latest recovery report beside the marker so `doctor` can show it with the host stopped."""
    state = read_state(path)
    if not state or state.get('unreadable') or state.get('run') != run:
        return False
    _write_state(path, state | {'last_recovery': report})
    return True


def mark_clean_stop(path, run, clock=time.time):
    """Record a clean stop for this run only. A different run's marker is never overwritten."""
    state = read_state(path)
    if not state or state.get('unreadable') or state.get('run') != run:
        return False
    now = int(clock())
    _write_state(path, state | {'clean_stop': True, 'stopped_at': now, 'last_clean_stop': now})
    return True


# Reconciliation at start -----------------------------------------------------

def _table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _routine_slots(db, scope, now):
    from .routines import next_slot
    missed = {}
    if _table(db, 'routine_settings'):
        for row in db.execute('SELECT kind,settings,next_due FROM routine_settings WHERE scope=? AND enabled=1 '
                              'AND next_due>0 AND next_due<=? ORDER BY kind', (scope, now)):
            settings, moment, count = json.loads(row['settings']), row['next_due'], 0
            while moment <= now and count < 1000:
                count += 1
                moment = next_slot(settings, moment)
            missed[row['kind']] = count
    if _table(db, 'pulse_routines'):
        for row in db.execute('SELECT id,interval_seconds,next_due FROM pulse_routines WHERE scope=? AND enabled=1 '
                              'AND next_due>0 AND next_due<=? ORDER BY id', (scope, now)):
            missed['pulse:' + row['id']] = min(1000, (now - row['next_due']) // max(row['interval_seconds'], 1) + 1)
    if _table(db, 'hub_mandates'):
        # Goal heartbeats (AGENT_HUB.md H2): counted here, never replayed.
        from .hub_goals import missed_slots
        from .sealing import of, open_row
        for row in db.execute('SELECT id,schedule,next_due FROM hub_mandates WHERE scope=? AND next_due>0 AND next_due<=? '
                              'AND schedule IS NOT NULL ORDER BY id', (scope, now)):
            schedule = open_row(of(db), 'hub_mandates', row)['schedule']
            missed['hub:' + row['id']] = missed_slots(json.loads(schedule), row['next_due'], now)
    return missed


def reconcile(store, owner_bearer, start, worker_id=LOCAL_WORKER):
    """Settle what the previous process left unfinished. Call before any worker or question loop starts."""
    owner = store.principal(owner_bearer, {'owner'})
    now = store.now()
    with store.transaction() as db:
        questions = 0
        if _table(db, 'conversation_turns'):
            questions = db.execute("SELECT count(*) FROM conversation_turns WHERE state IN ('queued','running')").fetchone()[0]
            # The same transition ConversationService.recover makes; the view gives the visible reason.
            db.execute("UPDATE conversation_turns SET state='interrupted',completed=?,result=NULL WHERE state IN ('queued','running')", (now,))
        has_jobs = _table(db, 'jobs')
        routines = _routine_slots(db, owner['scope'], now)
    jobs = {'effect_unknown': [], 'requeued': []}
    if has_jobs:
        from .jobs import JobCoordinator
        jobs = JobCoordinator(store).settle_host_restart(owner_bearer, worker_id)
    return {'previous_stop': start['previous_stop'], 'last_clean_stop': start['last_clean_stop'],
            'previous_started_at': start['previous_started_at'], 'started_at': start['started_at'],
            'reconciled_at': now, 'questions_interrupted': questions,
            'question_reason': 'host_stopped_before_answer',
            'jobs_effect_unknown': jobs['effect_unknown'], 'jobs_requeued': jobs['requeued'],
            'job_reason': 'host_stopped_while_running',
            'routine_slots_due_while_stopped': routines,
            'routine_note': 'Each routine runs once for its latest due slot and records the rest as missed; none is replayed.',
            'basis': 'reconciled_at_host_start'}


# Doctor ----------------------------------------------------------------------

def _mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


def _host_running(path):
    """True when a host holds the lock. Never creates the lock file."""
    import fcntl
    try:
        fd = os.open(Path(path) / 'desk.lock', os.O_RDWR | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def doctor(data_dir, vaults=(), *, console_dist=None, clock=time.time):
    """Read-only checks of one data directory. Returns a list of {check, status, detail}; status is ok, warn or fail."""
    from .placement import check_data_directory, PlacementFault
    path = Path(os.path.normpath(Path(data_dir).expanduser().absolute()))
    results = []
    add = lambda check, status, detail: results.append({'check': check, 'status': status, 'detail': detail})
    try:
        check_data_directory(path, tuple(v for v in vaults if v))
        add('placement', 'ok', f'{path} is not inside a recognised sync folder, Git working tree or vault.')
    except PlacementFault as exc:
        add('placement', 'fail', exc.detail)
    if path == REPOSITORY or REPOSITORY in path.parents:
        add('placement', 'fail', 'The data directory is inside the ALFRED repository. Runtime data must be kept outside it.')
    if not path.is_dir() or path.is_symlink():
        add('data_directory', 'fail', f'{path} does not exist as a real directory. Run "python3 -m alfred.desk init" first.')
        return results
    info = os.lstat(path)
    problems = []
    if hasattr(os, 'getuid') and info.st_uid != os.getuid():
        problems.append('the data directory belongs to another user')
    if stat.S_IMODE(info.st_mode) & 0o077:
        problems.append(f'the data directory is mode {stat.S_IMODE(info.st_mode):o}; it should be 700')
    for name in ('desk-access.json', 'desk.sqlite', 'desk.sqlite-wal', 'desk.sqlite-shm', 'desk.lock', STATE_FILE,
                 keys.KEYRING_FILE):
        file = path / name
        if file.is_symlink():
            problems.append(f'{name} is a symbolic link')
        elif file.exists() and _mode(file) & 0o077:
            problems.append(f'{name} is mode {_mode(file):o}; it should be 600')
    if not (path / 'desk-access.json').exists():
        problems.append('desk-access.json is missing')
    add('permissions', 'fail' if problems else 'ok',
        '; '.join(problems) + '.' if problems else 'The data directory and its live files are private to you.')
    running = _host_running(path)
    database, wal = path / 'desk.sqlite', path / 'desk.sqlite-wal'
    if not database.is_file():
        add('database', 'fail', 'desk.sqlite is missing.')
    else:
        wal_size = wal.stat().st_size if wal.is_file() else 0
        with open(database, 'rb') as stream:
            header = stream.read(100)
        # Bytes 18 and 19 of the SQLite header are 2 for a WAL database; read directly, nothing is opened for writing.
        journal = 'wal' if len(header) == 100 and header[18:20] == b'\x02\x02' else 'rollback'
        detail = check = backup = None
        if not running and wal_size:
            # Opening would apply the waiting log; doctor leaves that to the next start.
            check = 'skipped'
        else:
            try:
                # Read-only, and immutable when no host is running and no log waits, so no -wal or -shm
                # file is created. Doctor never creates tables, never checkpoints and never repairs.
                quoted = str(database).replace('%', '%25').replace('?', '%3f').replace('#', '%23')
                uri = 'file:' + quoted + ('?mode=ro' if running else '?mode=ro&immutable=1')
                db = sqlite3.connect(uri, uri=True, timeout=2)
                try:
                    db.row_factory = sqlite3.Row
                    check = db.execute('PRAGMA quick_check').fetchone()[0]
                    backup = (db.execute('SELECT created,file FROM lifecycle_backups ORDER BY created DESC LIMIT 1').fetchone()
                              if _table(db, 'lifecycle_backups') else None)
                finally:
                    db.close()
            except sqlite3.Error as exc:
                detail = type(exc).__name__
        if detail:
            add('database', 'fail', f'desk.sqlite could not be opened read-only ({detail}).')
        else:
            if check == 'skipped':
                add('database', 'warn', 'Integrity check skipped: a write-ahead log is waiting and opening the database would apply it.')
            else:
                add('database', 'ok' if check == 'ok' else 'fail',
                    'Quick integrity check passed.' if check == 'ok' else f'Quick integrity check reported: {check}.')
            if journal != 'wal':
                add('wal', 'warn', f'The journal mode is {journal}, not WAL.')
            elif running:
                add('wal', 'ok', f'A host is running; its write-ahead log is {wal_size} bytes and in use.')
            elif wal_size:
                add('wal', 'warn', f'No host is running but a {wal_size}-byte write-ahead log remains, usually from a host that did not '
                    'stop cleanly. SQLite applies it on the next open. Never copy desk.sqlite without it; use the backup command.')
            else:
                add('wal', 'ok', 'No host is running and no write-ahead log is waiting.')
            if check == 'skipped':
                add('backup', 'warn', 'Backup age not read while a write-ahead log is waiting.')
            elif backup is None:
                add('backup', 'warn', 'No backup is recorded. Run "python3 -m alfred.desk backup".')
            else:
                age = int(clock()) - backup['created']
                days = age // 86400
                present = Path(backup['file']).is_file()
                status = 'warn' if age > BACKUP_WARN_SECONDS or not present else 'ok'
                add('backup', status, f'The last backup is {days} day{"s" if days != 1 else ""} old'
                    + ('' if present else ' and its file is no longer where it was written') + '.')
    state = read_state(path)
    if running:
        add('last_stop', 'ok', 'A host is running now.')
    elif state is None:
        add('last_stop', 'ok', 'No host has started with this data directory yet.')
    elif state.get('unreadable'):
        add('last_stop', 'warn', f'{STATE_FILE} could not be read, so the last stop is unknown.')
    elif state.get('clean_stop'):
        add('last_stop', 'ok', 'The last host stopped cleanly at ' + _when(state.get('stopped_at')) + '.')
    else:
        add('last_stop', 'warn', 'The last host did not stop cleanly. The next start marks interrupted questions and '
            'reports started jobs as effect unknown for you to reconcile.')
    disk = keys.disk_encryption(path)
    add('disk_encryption', 'ok' if disk['status'] == 'on' else 'warn', disk['detail'])
    keyring = path / keys.KEYRING_FILE
    if keyring.exists() or keyring.is_symlink():
        # Read only: the keyring's layout is checked, and nothing is unlocked.
        try:
            view = keys.Keyring.read(keyring).view()
        except Fault as exc:
            add('keyring', 'fail', f'{keys.KEYRING_FILE} could not be read ({exc.code}).')
        else:
            methods = sorted({slot['method'] for slot in view['unlock']})
            areas = len(view['areas'])
            add('keyring', 'ok', f'The keyring has {areas} area{"s" if areas != 1 else ""} and opens with: '
                + ', '.join(methods) + '. Doctor did not unlock it.')
    dist = Path(console_dist) if console_dist else REPOSITORY / 'console' / 'dist'
    if (dist / 'index.html').is_file():
        add('console_build', 'ok', f'The console build is present at {dist}.')
    else:
        add('console_build', 'warn', 'The console is not built; the host serves the classic web desk only. '
            'Build it with "cd console && npm ci && npm run build".')
    return results


def _when(moment):
    return time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(moment)) if type(moment) is int else 'an unknown time'


# Service-file text -----------------------------------------------------------

LABEL = 'local.alfred.desk'
UNIT = 'alfred-desk.service'
INSTALL_FOLDERS = (('Library', 'LaunchAgents'), ('Library', 'LaunchDaemons'), ('.config', 'systemd'),
                   ('systemd',), ('launchd.conf',))
SYSTEM_FOLDERS = (Path('/etc/systemd'), Path('/lib/systemd'), Path('/usr/lib/systemd'),
                  Path('/Library/LaunchAgents'), Path('/Library/LaunchDaemons'), Path('/System'))


def serve_arguments(data_dir, port=8765, vault=None, vault_exclusions=(), local_model=None, model_port=11434,
                    python=None):
    """The exact `serve` command a service manager would run. Loopback only; nothing here widens the listener."""
    if not 1024 <= port <= 65535:
        raise Fault('invalid_port')
    arguments = [python or sys.executable, '-m', 'alfred.desk', 'serve',
                 '--data-dir', str(Path(data_dir).expanduser().absolute()), '--port', str(port)]
    if vault:
        arguments += ['--vault', str(Path(vault).expanduser().absolute())]
    for folder in vault_exclusions:
        arguments += ['--vault-exclude', folder]
    if local_model:
        arguments += ['--local-model', local_model, '--model-port', str(model_port)]
    for item in arguments:
        if any(ord(c) < 32 or c == '\x7f' for c in item):
            raise Fault('invalid_service_argument')
    return arguments


def _systemd_quote(item):
    escaped = item.replace('%', '%%').replace('$', '$$')
    if re.fullmatch(r'[A-Za-z0-9_@%+=:,./-]+', escaped):
        return escaped
    return '"' + escaped.replace('\\', '\\\\').replace('"', '\\"') + '"'


def systemd_unit(arguments):
    command = ' '.join(_systemd_quote(a) for a in arguments)
    return '\n'.join([
        '# Generated by "python3 -m alfred.desk service-file". ALFRED has not installed this file.',
        '# Review it first. To use it yourself as a user service, copy it to ~/.config/systemd/user/' + UNIT,
        '# and run: systemctl --user daemon-reload && systemctl --user start ' + UNIT,
        '# The host listens on 127.0.0.1 only. Stopping the unit sends SIGTERM, which ALFRED records as a clean stop.',
        '[Unit]',
        'Description=ALFRED local desk (foreground host, loopback only)',
        '',
        '[Service]',
        'Type=simple',
        'WorkingDirectory=' + _systemd_quote(str(REPOSITORY)),
        'Environment=PYTHONUNBUFFERED=1',
        'ExecStart=' + command,
        'Restart=on-failure',
        'RestartSec=10',
        'TimeoutStopSec=30',
        'UMask=0077',
        'NoNewPrivileges=yes',
        '',
        '[Install]',
        'WantedBy=default.target',
        ''])


def launchd_plist(arguments, data_dir):
    log = str(Path(data_dir).expanduser().absolute() / 'host-output.log')
    body = plistlib.dumps({'Label': LABEL, 'ProgramArguments': list(arguments), 'WorkingDirectory': str(REPOSITORY),
                           'EnvironmentVariables': {'PYTHONUNBUFFERED': '1'}, 'RunAtLoad': False,
                           'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 10, 'Umask': 63,
                           'ExitTimeOut': 30, 'StandardOutPath': log, 'StandardErrorPath': log}, sort_keys=True).decode()
    note = ('<!-- Generated by "python3 -m alfred.desk service-file". ALFRED has not installed this file.\n'
            '     Review it first. To use it yourself, copy it to ~/Library/LaunchAgents/' + LABEL + '.plist and run:\n'
            '     launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/' + LABEL + '.plist\n'
            '     launchctl kickstart gui/$(id -u)/' + LABEL + '\n'
            '     RunAtLoad is off: it does not start at login unless you change that yourself.\n'
            '     The host listens on 127.0.0.1 only. launchd stops it with SIGTERM, recorded as a clean stop. -->\n')
    head, rest = body.split('\n', 1)
    return head + '\n' + note + rest


def service_text(kind, arguments, data_dir):
    if kind == 'systemd':
        return systemd_unit(arguments)
    if kind == 'launchd':
        return launchd_plist(arguments, data_dir)
    raise Fault('invalid_service_kind')


def default_kind():
    return 'launchd' if sys.platform == 'darwin' else 'systemd'


def write_service_file(text, output):
    """Write the text to a new file. Refuses a folder a service manager loads from, so writing never installs."""
    target = Path(os.path.normpath(Path(output).expanduser().absolute()))
    for view in {target, target.parent.resolve() / target.name}:
        parts = view.parts
        for folder in INSTALL_FOLDERS:
            if any(tuple(parts[i:i + len(folder)]) == folder for i in range(len(parts))):
                raise Fault('service_file_output_would_install', 409)
        if any(view == root or root in view.parents for root in SYSTEM_FOLDERS):
            raise Fault('service_file_output_would_install', 409)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    return target
