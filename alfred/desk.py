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


def serve(path, port, vault=None):
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
        supervisor = Supervisor(store, keys['owner'], keys['source'], path / 'project', vault=vault or (path / 'vault' if (path / 'vault').is_dir() else None))
        server = DeskHTTPServer(store, supervisor, port=port)
        supervisor.start()
        print('ALFRED local desk:', server.origin, flush=True)
        print('Synthetic project files only. Microphone and live AI are OFF. No external messages are sent.', flush=True)
        print('Use the access command to reveal your local sign-in key in a private terminal. Ctrl+C stops the desk.', flush=True)
        server.serve_forever(poll_interval=0.1)
    finally:
        if supervisor:
            supervisor.stop()
        if server:
            server.server_close()
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'access', 'serve', 'revoke'))
    parser.add_argument('--data-dir', default='~/.local/share/alfred/desk-demo')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--credential-id')
    parser.add_argument('--vault', help='Explicit read-only Markdown folder; no Obsidian plugins are loaded')
    parser.add_argument('--role', choices=('owner', 'reader'), default='owner')
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
        elif args.command == 'revoke':
            if not args.credential_id:
                raise Fault('credential_id_required')
            DeskStore(path / 'desk.sqlite').revoke(args.credential_id)
            print('Credential revoked. Existing browser access and queued work will be rechecked.')
        else:
            if not 1024 <= args.port <= 65535:
                raise Fault('invalid_port')
            serve(path, args.port, args.vault)
    except KeyboardInterrupt:
        print('ALFRED desk stopped. Stored events and drafts remain on disk.')
    except (Fault, OSError, ValueError) as exc:
        print('Cannot start:', exc.code if isinstance(exc, Fault) else type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
