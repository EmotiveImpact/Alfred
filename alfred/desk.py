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
from .local import Fault
from .knowledge_demo import seed_vault
from .local_model import LocalOllama


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
    path = private_home(path)
    config = path / 'desk-access.json'
    if config.exists() or config.is_symlink() or (path / 'desk.sqlite').exists():
        raise Fault('desk_already_initialised', 409)
    store = DeskStore(path / 'desk.sqlite')
    credentials = {role: store.provision('demo-production', 'demo-' + role, role) for role in ('owner', 'reader', 'source')}
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


def serve(path, port, vault=None, model=None, model_port=11434, model_timeout=60, *, vault_exclusions=(), vault_id_key=None):
    # POSIX development target. A lock prevents accidental duplicate supervisors.
    import fcntl
    fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    server = supervisor = None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Fault('desk_already_running', 409) from None
        keys = load_keys(path)
        store = DeskStore(path / 'desk.sqlite')
        supervisor = Supervisor(store, keys['owner'], keys['source'], path / 'project', vault=vault or (path / 'vault' if (path / 'vault').is_dir() else None), vault_exclusions=vault_exclusions, vault_id_key=vault_id_key)
        jobs, job_stop = start_local_jobs(store, keys['owner'], path)
        server = DeskHTTPServer(store, supervisor, port=port, local_model=LocalOllama(model, model_port, timeout=model_timeout) if model else None, jobs=jobs)
        supervisor.start()
        print('ALFRED local desk:', server.origin, flush=True)
        print('Local development data. Microphone OFF. No external messages are sent.', flush=True)
        print('Local model available only on explicit request.' if model else 'Source mode: no model configured.', flush=True)
        print('Use the access command to reveal your local sign-in key in a private terminal. Ctrl+C stops the desk.', flush=True)
        server.serve_forever(poll_interval=0.1)
    finally:
        if supervisor:
            supervisor.stop()
        if 'job_stop' in locals():
            job_stop()
        if server:
            server.server_close()
        os.close(fd)


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
    from .job_kinds import KINDS
    jobs = JobCoordinator(store, cache=BoundedCache(path / 'job-cache', 256 * 1024 * 1024))
    if not any(w['id'] == 'local-host' for w in jobs.workers(owner)):
        jobs.enrol_worker(owner, 'local-host', 'This computer (local subprocess)', sorted(KINDS))
    worker = JobWorker(jobs, LocalSubprocessBackend(), owner, 'local-host', poll_seconds=0.2)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), kwargs={'idle_seconds': 0.75}, name='alfred-local-jobs', daemon=True)
    thread.start()
    def halt():
        stop.set(); thread.join(10)
    return jobs, halt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'access', 'serve', 'revoke', 'backup', 'restore', 'rotate',
                                            'connector-add', 'connector-import', 'connectors'))
    parser.add_argument('--backup-file', help='Backup to restore; ALFRED must be stopped')
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
    # Read-only connectors over export files you select (CON-001). ALFRED must be stopped.
    parser.add_argument('--connector', choices=('ics-export', 'vcf-export'), help='Calendar (.ics) or contacts (.vcf) export connector')
    parser.add_argument('--connector-label', help='Label for a new connector source, for example "Calendar export"')
    parser.add_argument('--connector-scope', action='append', default=[], help='Read scope for a new connector; repeat as needed (default: the least)')
    parser.add_argument('--connector-source', help='Connector source ID printed by connector-add')
    parser.add_argument('--export-file', help='The export file you selected; it is only ever read')
    parser.add_argument('--dry-run', action='store_true', help='Show what an import would change, changing nothing')
    parser.add_argument('--allow-remove-all', action='store_true', help='Accept an export that removes every current item')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        path = private_home(args.data_dir)
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
            print('It is an unencrypted SQLite copy. Keep it private.')
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
                result = restore(args.backup_file, path / 'desk.sqlite')
            finally:
                os.close(fd)
            print('Restored', result['restored_from'], '- replayed', result['journal_entries_replayed'], 'forget/revocation entries.')
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
            serve(path, args.port, args.vault, args.local_model, args.model_port, args.model_timeout, vault_exclusions=args.vault_exclude, vault_id_key=args.vault_id_key)
    except KeyboardInterrupt:
        print('ALFRED desk stopped. Stored events and drafts remain on disk.')
    except (Fault, OSError, ValueError) as exc:
        print('Cannot start:', exc.code if isinstance(exc, Fault) else type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
