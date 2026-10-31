"""Run ALFRED's local, synthetic-data desk. No cloud keys or external services."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import time
from .knowledge import KnowledgeStore as DeskStore
from .knowledge import KnowledgeSupervisor as Supervisor
from .desk_http import DeskHTTPServer
from .disk_encryption import MODES as DISK_MODES, at_start as disk_encryption_at_start
from .hub_host import CHOICES as HUB_CHOICES, start_goal_hub
from .local import Fault
from .knowledge_demo import seed_vault
from .local_model import LocalOllama
from .placement import check_data_directory


def private_home(path):
    path = Path(path).expanduser().absolute()
    repo = Path(__file__).resolve().parents[1]
    if path == repo or repo in path.parents:
        raise Fault('runtime_data_must_be_outside_repository')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise Fault('private_directory_required')
    info = path.stat()
    if hasattr(os, 'getuid') and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise Fault('private_directory_permissions_required')
    return path


def init_demo(path):
    # Live files never go where a sync tool, Git or a vault could hold them (MEM-014).
    check_data_directory(path)
    path = private_home(path)
    config = path / 'desk-access.json'
    if config.exists() or config.is_symlink() or (path / 'desk.sqlite').exists():
        raise Fault('desk_already_initialised', 409)
    store = DeskStore(path / 'desk.sqlite')
    credentials = {role: store.provision('demo-production', 'demo-' + role, role) for role in ('owner', 'reader', 'source')}
    # Strict grants by default (SYS-001): nobody, the owner included, sees a source until it
    # is granted. The demo grants its owner read and model on its one source, explicitly and
    # journalled like any grant. The reader key holds nothing until the owner grants it.
    from .policy import IdentityPolicy
    policy = IdentityPolicy(store)
    source_expires = store.principal(credentials['source'], {'source'})['expires']
    for capability in ('read', 'model'):
        policy.grant(credentials['owner'], 'demo-source', capability, source_expires, policy.view(credentials['owner'])['epoch'])
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(credentials, stream)
    source = path / 'project'
    source.mkdir(mode=0o700)
    now = store.now()
    samples = [
        ('schedule', 'Call time has changed', 'The sample production call has moved from 09:30 to 10:00. The crew update still needs review.'),
        ('equipment', 'Equipment confirmation outstanding', 'The sample camera package is recorded as reserved. Collection has not yet been confirmed.'),
        ('treatment', 'A revised treatment is ready', 'The sample treatment now requests a monochrome opening. Review this against the previously agreed approach.'),
    ]
    for i, (identity, title, summary) in enumerate(samples):
        value = {'document_id': identity, 'title': title, 'revision': 1,
                 'observed_at': now - 30 - i, 'expires_at': now + 3600, 'summary': summary}
        (source / (identity + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    seed_vault(path / 'vault')
    return credentials


def load_keys(path):
    file = path / 'desk-access.json'
    fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or stat.S_IMODE(info.st_mode) & 0o077:
            raise Fault('private_access_file_required')
        value = json.loads(os.read(fd, 4097))
        if set(value) != {'owner', 'reader', 'source'}:
            raise Fault('invalid_access_file')
        return value
    finally:
        os.close(fd)


def serve(path, port, vault=None, model=None, model_port=11434, model_timeout=60, *, vault_exclusions=(), vault_id_key=None, hub='off',
          disk_encryption='warn'):
    # POSIX development target. A lock prevents accidental duplicate supervisors.
    import fcntl
    import signal
    import threading
    from . import recovery
    check_data_directory(path, (vault,) if vault else ())
    # Asked before anything starts, so `require` refuses with nothing created (master plan phase 1).
    disk_lines = disk_encryption_at_start(path, vault, disk_encryption)
    fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    server = supervisor = start = None
    clean, previous_handler, hub_stop = False, None, None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Fault('desk_already_running', 409) from None
        keys = load_keys(path)
        store = DeskStore(path / 'desk.sqlite')
        # Holding the lock, record this start and settle what an earlier process left (RUN-001).
        start = recovery.begin(path)
        report = recovery.reconcile(store, keys['owner'], start)
        recovery.record_recovery(path, start['run'], report)
        if threading.current_thread() is threading.main_thread():
            # A service manager stops the host with SIGTERM; treat it like Ctrl+C so the stop is clean.
            def terminate(_signum, _frame):
                raise KeyboardInterrupt
            previous_handler = signal.signal(signal.SIGTERM, terminate)
        supervisor = Supervisor(store, keys['owner'], keys['source'], path / 'project', vault=vault or (path / 'vault' if (path / 'vault').is_dir() else None), vault_exclusions=vault_exclusions, vault_id_key=vault_id_key)
        jobs, job_stop = start_local_jobs(store, keys['owner'], path)
        # Off unless asked for; only the synthetic test brain exists (alfred/hub_host.py).
        goals, hub_stop = start_goal_hub(store, jobs, keys['owner'], hub)
        server = DeskHTTPServer(store, supervisor, port=port, local_model=LocalOllama(model, model_port, timeout=model_timeout) if model else None, jobs=jobs, goals=goals)
        server.recovery = report
        supervisor.start()
        print('ALFRED local desk:', server.origin, flush=True)
        print('Local development data. Microphone OFF. No external messages are sent.', flush=True)
        print('Local model available only on explicit request.' if model else 'Source mode: no model configured.', flush=True)
        if goals is not None:
            print('Goal hub on: synthetic test brain only. No model, no cloud, no tools.', flush=True)
        for line in disk_lines:
            print(line, flush=True)
        print(recovery_line(report), flush=True)
        print('Use the access command to reveal your local sign-in key in a private terminal. Ctrl+C stops the desk.', flush=True)
        server.serve_forever(poll_interval=0.1)
        clean = True
    except KeyboardInterrupt:
        clean = True
        raise
    finally:
        try:
            if supervisor:
                supervisor.stop()
            if hub_stop is not None and not hub_stop():
                clean = False
            if 'job_stop' in locals() and not job_stop():
                clean = False  # A job was still running; the next start reports it honestly.
            if server:
                server.server_close()
            if clean and start is not None:
                recovery.mark_clean_stop(path, start['run'])
        finally:
            if previous_handler is not None:
                signal.signal(signal.SIGTERM, previous_handler)
            os.close(fd)


def open_workspace(path):
    """Before anything touches a sealed workspace's database: unlock its keyring and attach
    its sealer, or refuse to start. A plain workspace needs nothing.

    A sealed workspace never runs unprotected: if no unlock method works here (the keychain
    on a Mac, the server's secret store, or the passphrase typed at the prompt), ALFRED stops
    with ``workspace_locked`` rather than open it without its keys."""
    from . import keys, sealing
    from .seal_workspace import incomplete
    database = path / 'desk.sqlite'
    step = incomplete(database)
    if step:
        error = Fault('sealing_incomplete', 409)
        error.detail = (f'A {step} did not finish. Run python3 -m alfred.desk '
                        f'{"seal" if step == "seal" else "rotate-area"} again to finish it before starting ALFRED.')
        raise error
    recorded = sealing.recorded(database)
    if recorded is None or sealing.for_path(database).sealed:
        return
    keyring_file = keys.keyring_path(path)
    if not keyring_file.is_file():
        error = Fault('workspace_locked', 423)
        error.detail = 'This workspace is sealed and its keyring is not in the data folder. Restore it from your recovery kit.'
        raise error
    try:
        opened, _ = keys.unlock(keys.Keyring.read(keyring_file), prompt=keys._ask, warn=keys._warn)
    except Fault as exc:
        if exc.code != 'no_unlock_available':
            raise
        error = Fault('workspace_locked', 423)
        error.detail = 'This workspace is sealed and no unlock method worked here, so ALFRED will not open it.'
        raise error from None
    if opened.id != recorded:
        opened.close()
        raise Fault('wrong_keyring', 409)
    sealing.attach(database, sealing.Sealed(opened))


def _locked(path, code):
    """Hold the desk lock for an offline command, or refuse while ALFRED runs."""
    import fcntl
    fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise Fault(code, 409) from None
    return fd


def seal_command(path):
    """Convert this workspace to sealed, once, with the keyring in its data folder."""
    from . import keys, sealing
    from .seal_workspace import seal
    keyring_file = keys.keyring_path(path)
    if not keyring_file.is_file():
        error = Fault('keyring_required', 409)
        error.detail = 'Make the keyring first: python3 -m alfred.keys --data-dir <this folder> init'
        raise error
    fd = _locked(path, 'stop_alfred_before_sealing')
    try:
        opened, how = keys.unlock(keys.Keyring.read(keyring_file), prompt=keys._ask, warn=keys._warn)
        with opened:
            if not any(a['id'] == sealing.DEFAULT_AREA for a in opened.areas()):
                opened.add_area(sealing.DEFAULT_AREA, 'personal', 'Personal')
                print(f'Added the {sealing.DEFAULT_AREA} area to the keyring: every record is sealed in it for now.')
            sealer = sealing.Sealed(opened)
            result = seal(path / 'desk.sqlite', sealer, cache_dir=path / 'job-cache')
    finally:
        os.close(fd)
    if result['already_sealed']:
        print(f'The workspace was already sealed. Compacted it again; backups newly sealed: {result["backups_sealed"]}.')
    else:
        print(f'Sealed the workspace with the keyring opened by the {how}: {result["values_sealed"]} values sealed, '
              f'{result["fingerprints_keyed"]} fingerprints and {result["ids_keyed"]} ids keyed, '
              f'{result["backups_sealed"]} backups sealed.')
        print('ALFRED now unlocks the keyring each time it starts, and will not start if it cannot.')
    print('Exports you wrote before sealing are still readable files: delete them if you no longer need them.')
    return result


def rotate_area_command(path, area):
    """A new key for one area: its values are sealed again under it, then the older keys go."""
    from . import keys, sealing
    from .seal_workspace import RESEALING, marker, reseal
    database = path / 'desk.sqlite'
    if sealing.recorded(database) is None:
        raise Fault('workspace_not_sealed', 409)
    fd = _locked(path, 'stop_alfred_before_rotation')
    try:
        opened, _ = keys.unlock(keys.Keyring.read(keys.keyring_path(path)), prompt=keys._ask, warn=keys._warn)
        with opened:
            resuming = marker(database, RESEALING)
            if not resuming.exists() or resuming.read_text() != area:
                opened.rotate_area(area)
            result = reseal(database, sealing.Sealed(opened), area)
    finally:
        os.close(fd)
    print(f"The {area} area now seals with key version {result['key_version']}: {result['values_resealed']} values sealed again, "
          f"{result['key_versions_retired']} older keys deleted.")
    print('Keyring copies made before now still hold the older keys: make a new recovery-kit backup and delete the old ones.')
    return result


def recovery_line(report):
    """One plain line about the previous stop. Counts only; no question text or job content."""
    stop = {'clean': 'The previous run stopped cleanly.', 'first_start': 'First start of this data directory.',
            'unclean': 'The previous run did not stop cleanly.', 'unknown': 'The previous stop is unknown.'}[report['previous_stop']]
    missed = sum(report['routine_slots_due_while_stopped'].values())
    return (f"{stop} Interrupted questions: {report['questions_interrupted']}. "
            f"Jobs needing reconciliation (effect unknown): {len(report['jobs_effect_unknown'])}. "
            f"Jobs returned to the queue: {len(report['jobs_requeued'])}. Routine slots due while stopped: {missed}.")


def rotate_key(path, role):
    """Offline credential rotation. The host must be stopped because it holds the old keys."""
    import fcntl
    from .policy import IdentityPolicy
    fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Fault('stop_alfred_before_rotation', 409) from None
        keys = load_keys(path)
        store = DeskStore(path / 'desk.sqlite')
        if role not in keys:
            raise Fault('invalid_role')
        policy = IdentityPolicy(store)
        with store.transaction() as db:
            generation = store.authenticate(db, keys[role], {'owner', 'reader', 'source'})['generation']
        import secrets
        # Stage the new key on disk first, so a failure can never leave a key nobody holds.
        replacement, old = secrets.token_urlsafe(32), keys[role]
        staging = path / 'desk-access.json.rotating'
        staging.unlink(missing_ok=True)
        handle = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(handle, 'w') as stream:
            json.dump(keys | {role: replacement}, stream); stream.flush(); os.fsync(stream.fileno())
        try:
            policy.rotate(old, generation, replacement=replacement)
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
        os.replace(staging, path / 'desk-access.json')
        return replacement
    finally:
        os.close(fd)


def start_local_jobs(store, owner, path):
    """One local-subprocess worker thread for this host. Not a sandbox or remote worker."""
    import threading
    from .jobs import BoundedCache, JobCoordinator, JobWorker, LocalSubprocessBackend
    from .job_kinds import SUBPROCESS_KINDS
    jobs = JobCoordinator(store, cache=BoundedCache(path / 'job-cache', 256 * 1024 * 1024))
    if not any(w['id'] == 'local-host' for w in jobs.workers(owner)):
        jobs.enrol_worker(owner, 'local-host', 'This computer (local subprocess)', list(SUBPROCESS_KINDS))
    worker = JobWorker(jobs, LocalSubprocessBackend(), owner, 'local-host', poll_seconds=0.2)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), kwargs={'idle_seconds': 0.75}, name='alfred-local-jobs', daemon=True)
    thread.start()
    def halt():
        stop.set(); thread.join(10)
        return not thread.is_alive()
    return jobs, halt


def recovery_command(args):
    from . import recovery
    if args.command == 'doctor':
        results = recovery.doctor(args.data_dir, (args.vault,) if args.vault else ())
        if args.json:
            print(json.dumps({'data_dir': str(Path(args.data_dir).expanduser().absolute()), 'checks': results,
                              'changes_made': False}, indent=2))
        else:
            for item in results:
                print(f"{item['status'].upper():4}  {item['check']:<14} {item['detail']}")
            print('Doctor only reads. It changed nothing, repaired nothing and installed nothing.')
        return 1 if any(item['status'] == 'fail' for item in results) else 0
    if not 1024 <= args.port <= 65535:
        raise Fault('invalid_port')
    kind = args.service or recovery.default_kind()
    arguments = recovery.serve_arguments(args.data_dir, args.port, args.vault, tuple(args.vault_exclude),
                                         args.local_model, args.model_port)
    text = recovery.service_text(kind, arguments, args.data_dir)
    if args.output:
        target = recovery.write_service_file(text, args.output)
        print('Wrote', kind, 'service text to', target)
        print('ALFRED has not installed, loaded, enabled or started it. Review it, then install it yourself if you want it.')
    else:
        print(text, end='')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'access', 'serve', 'revoke', 'backup', 'restore', 'rotate', 'export', 'rebuild-index',
                                            'connector-add', 'connector-import', 'connectors', 'doctor', 'service-file',
                                            'deletion-report', 'seal', 'rotate-area', 'open-export'))
    parser.add_argument('--backup-file', help='Backup to restore; ALFRED must be stopped')
    parser.add_argument('--export-dir', help='New or empty folder for an export; never inside a vault')
    parser.add_argument('--plain', action='store_true', help='export: write readable files from a sealed workspace; anyone holding them can read them')
    parser.add_argument('--sealed-export', help='open-export: a sealed export to open into --export-dir')
    parser.add_argument('--area', help='rotate-area: the area whose key is replaced')
    parser.add_argument('--data-dir', default='~/.local/share/alfred/desk-demo')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--credential-id')
    parser.add_argument('--vault', help='Explicit read-only Markdown folder; no Obsidian plugins are loaded')
    parser.add_argument('--vault-exclude', action='append', default=[], help='Exclude a relative folder and its descendants; repeat as needed')
    parser.add_argument('--vault-id-key', choices=('alfred_id',), help='Explicitly adopt stable alfred_id frontmatter properties')
    parser.add_argument('--local-model', help='Opt-in tool-free model on an operator-managed local Ollama server; no model is downloaded')
    parser.add_argument('--model-port', type=int, default=11434)
    parser.add_argument('--model-timeout', type=int, default=60, help='Bounded conversation model deadline, 1 to 90 seconds')
    parser.add_argument('--role', choices=('owner', 'reader', 'source'), default='owner')
    parser.add_argument('--disk-encryption', choices=DISK_MODES, default='warn',
                        help='serve: say whether the data folder and vault are on an encrypted disk (warn), or refuse to start unless they are (require)')
    parser.add_argument('--hub', choices=HUB_CHOICES, default='off', help='serve: build the goal hub with the synthetic test brain only (default: off)')
    # Read-only connectors over export files you select (CON-001). ALFRED must be stopped.
    parser.add_argument('--connector', choices=('ics-export', 'vcf-export'), help='Calendar (.ics) or contacts (.vcf) export connector')
    parser.add_argument('--connector-label', help='Label for a new connector source, for example "Calendar export"')
    parser.add_argument('--connector-scope', action='append', default=[], help='Read scope for a new connector; repeat as needed (default: the least)')
    parser.add_argument('--connector-source', help='Connector source ID printed by connector-add')
    parser.add_argument('--export-file', help='The export file you selected; it is only ever read')
    parser.add_argument('--dry-run', action='store_true', help='Show what an import would change, changing nothing')
    parser.add_argument('--allow-remove-all', action='store_true', help='Accept an export that removes every current item')
    # Host recovery (RUN-001). doctor only reads; service-file only prints or writes text and never installs.
    parser.add_argument('--json', action='store_true', help='doctor and deletion-report: print as JSON')
    parser.add_argument('--service', choices=('launchd', 'systemd'), help='service-file: launchd plist or systemd user unit (default: this platform)')
    parser.add_argument('--output', help='service-file: write to this new file instead of standard output; never a folder a service manager loads from')
    # Deletion accounting (MEM-010): what the workspace still holds about one subject, and where.
    parser.add_argument('--subject-kind', choices=('source', 'entity', 'statement'), help='Kind of subject for deletion-report')
    parser.add_argument('--subject', help='Source, entity or statement identifier for deletion-report')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command in ('doctor', 'service-file'):
            # Neither creates the data directory nor touches the database.
            raise SystemExit(recovery_command(args))
        if args.command in ('init', 'serve', 'restore'):
            # Checked before anything is created; backup and access stay available to move out.
            check_data_directory(args.data_dir, (args.vault,) if args.vault else ())
        path = private_home(args.data_dir)
        if args.command == 'seal':
            seal_command(path)
            return
        if args.command == 'rotate-area':
            if not args.area:
                raise Fault('area_required')
            rotate_area_command(path, args.area)
            return
        if args.command != 'init':
            # A sealed workspace is unlocked here or not at all, before any store opens it.
            open_workspace(path)
        if args.command == 'init':
            init_demo(path)
            print('Created a private synthetic workspace. No access keys printed.')
            print('Next: python3 -m alfred.desk access; then python3 -m alfred.desk serve')
        elif args.command == 'access':
            # Explicit secret-reveal command, never used in CI logs or screenshots.
            print(load_keys(path)[args.role])
        elif args.command == 'backup':
            from .lifecycle import backup
            manifest = backup(DeskStore(path / 'desk.sqlite'), load_keys(path)['owner'], path / 'backups')
            print('Backup written:', manifest['file'], 'sha256', manifest['sha256'])
            print('It is a sealed SQLite copy: it opens only with this workspace\'s keyring.' if manifest['sealed']
                  else 'It is an unencrypted SQLite copy. Keep it private.')
        elif args.command == 'export':
            if not args.export_dir:
                raise Fault('export_dir_required')
            from .export import export
            from . import sealing
            result = export(DeskStore(path / 'desk.sqlite'), load_keys(path)[args.role], args.export_dir,
                            vaults=(args.vault, path / 'vault'), plain=args.plain)
            print('Export written:', result['directory'])
            print('Statements:', result['counts']['statements'], '- executive records:', result['counts']['executive_records'],
                  '- left out (forgotten, withheld or past retention):',
                  sum(result['excluded'][k] for k in ('forgotten_statements', 'withheld_statements', 'retention_ended_statements')))
            if result.get('sealed'):
                print('Sealed JSON and Markdown: they open only with this workspace\'s keyring (open-export). Not a backup.')
            elif sealing.for_path(path / 'desk.sqlite').sealed:
                print('Warning: you asked for a plain export, so these files are not sealed. Anyone who gets them can read them.')
                print('Readable JSON and Markdown with SHA256SUMS. Not a backup and not encrypted. Keep it private.')
            else:
                print('Readable JSON and Markdown with SHA256SUMS. Not a backup and not encrypted. Keep it private.')
        elif args.command == 'open-export':
            if not args.sealed_export or not args.export_dir:
                raise Fault('export_dir_required')
            from .export import open_export
            from . import sealing
            opened = open_export(args.sealed_export, sealing.for_path(path / 'desk.sqlite'), args.export_dir)
            print('Opened the sealed export into', opened['directory'])
            print('These files are readable: keep them private and delete them when you are done.')
        elif args.command == 'rotate':
            rotate_key(path, args.role)
            print('Rotated the', args.role, 'key. The old key no longer works. Use the access command to reveal the new one.')
        elif args.command == 'restore':
            if not args.backup_file:
                raise Fault('backup_file_required')
            import fcntl
            from .lifecycle import restore
            fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise Fault('stop_alfred_before_restore', 409) from None
                cache = None
                if (path / 'job-cache').is_dir():
                    from .jobs import BoundedCache
                    cache = BoundedCache(path / 'job-cache', 256 * 1024 * 1024)
                result = restore(args.backup_file, path / 'desk.sqlite', cache=cache)
            finally:
                os.close(fd)
            print('Restored', result['restored_from'], '- applied again', result['journal_entries_replayed'],
                  'absolute forget and revocation entries.')
            if result['came_back']:
                # Ordinary forgets are not applied again, so what the backup held comes back. Say what.
                print('Came back from the backup (ordinary forgets):')
                for item in result['came_back']:
                    what = {'claim_forgotten': 'statement', 'entity_forgotten': 'record', 'source_forgotten': 'source'}[item['kind']]
                    when = time.strftime('%d %B %Y', time.gmtime(item['deleted_at'])) if item.get('deleted_at') else 'an unknown date'
                    print(f"  {what} {item['label']} ({item['subject']}), forgotten on {when}")
            again = result['removed_again']
            print('Removed again from the backup:', ', '.join(f'{k} {v}' for k, v in sorted(again['totals'].items())) or 'nothing',
                  '- cached results removed:', again['cached_results_removed'])
        elif args.command == 'rebuild-index':
            import fcntl
            from .rebuild import rebuild_index
            fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise Fault('stop_alfred_before_rebuild', 409) from None
                keys = load_keys(path)
                report = rebuild_index(DeskStore(path / 'desk.sqlite'), keys['owner'], keys['source'],
                                       Path(args.vault) if args.vault else path / 'vault',
                                       exclude_folders=tuple(args.vault_exclude), id_key=args.vault_id_key)
            finally:
                os.close(fd)
            notes = report['notes']
            print('Rebuilt', notes['after'], 'notes from the vault;', notes['same_identity_and_revision'], 'kept the same identity and revision.')
            print('New revisions:', len(notes['new_revision']), '- no longer present:', len(notes['no_longer_present']),
                  '- new:', len(notes['new']), '- links unchanged:', report['links']['unchanged'],
                  '- reviewed statements whose state changed:', len(report['reviewed_statements']['state_changed']))
        elif args.command == 'deletion-report':
            if not args.subject_kind or not args.subject:
                raise Fault('subject_required')
            from .deletion import lines, report
            cache = path / 'job-cache'
            result = report(DeskStore(path / 'desk.sqlite'), load_keys(path)['owner'], args.subject_kind, args.subject,
                            cache_dir=cache if cache.is_dir() else None)
            for line in ([json.dumps(result, indent=1, sort_keys=True)] if args.json else lines(result)):
                print(line)
        elif args.command in ('connector-add', 'connector-import', 'connectors'):
            from .connectors import command
            for line in command(path, args):
                print(line)
        elif args.command == 'revoke':
            if not args.credential_id:
                raise Fault('credential_id_required')
            DeskStore(path / 'desk.sqlite').revoke(args.credential_id)
            print('Credential revoked. Existing browser access and queued work will be rechecked.')
        else:
            if not 1024 <= args.port <= 65535:
                raise Fault('invalid_port')
            serve(path, args.port, args.vault, args.local_model, args.model_port, args.model_timeout, vault_exclusions=args.vault_exclude, vault_id_key=args.vault_id_key, hub=args.hub,
                  disk_encryption=args.disk_encryption)
    except KeyboardInterrupt:
        print('ALFRED desk stopped. Stored events and drafts remain on disk.')
    except (Fault, OSError, ValueError) as exc:
        print('Cannot start:', exc.code if isinstance(exc, Fault) else type(exc).__name__)
        if getattr(exc, 'detail', None):
            print(exc.detail)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
