"""Read-only, bounded project-file connector and foreground-owned supervisor."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import stat
import threading
from .local import Fault, parse_json


class ProjectFiles:
    def __init__(self, store, source_bearer, root):
        self.store, self.bearer, self.root = store, source_bearer, Path(root).absolute()
        self.principal = store.principal(source_bearer, {'source'})
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or self.root.is_symlink():
            raise Fault('source_directory_required')
        self.identity = (info.st_dev, info.st_ino)
        self.health = {'configured': True, 'status': 'starting', 'last_scan': None, 'errors': [], 'scanned_files': 0}

    def read_file(self, directory_fd, name):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        fd = os.open(name, flags, dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise Fault('regular_file_required')
            if before.st_size > 16384:
                raise Fault('source_file_too_large')
            raw = b''
            while len(raw) <= 16384:
                part = os.read(fd, min(4096, 16385 - len(raw)))
                if not part:
                    break
                raw += part
            after = os.fstat(fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise Fault('source_changed_during_read')
            if len(raw) > 16384:
                raise Fault('source_file_too_large')
            return parse_json(raw), hashlib.sha256(raw).hexdigest()
        finally:
            os.close(fd)

    def scan(self):
        p = self.principal
        if self.store.paused(p['scope']):
            return self.health
        errors, names = [], []
        try:
            self.store.principal(self.bearer, {'source'})
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != self.identity:
                    raise Fault('source_directory_replaced')
                entries = os.listdir(fd)
                if len(entries) > 128:
                    raise Fault('source_directory_capacity')
                names = sorted(n for n in entries if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.json', n))
                if len(names) > 32:
                    raise Fault('source_document_capacity')
                for name in names:
                    try:
                        data, digest = self.read_file(fd, name)
                        self.store.document(self.bearer, name, data, digest)
                    except (Fault, OSError) as exc:
                        code = exc.code if isinstance(exc, Fault) else 'source_read_failed'
                        errors.append({'file': name, 'code': code})
                        self.store.document_status(p['scope'], p['id'], name, 'error')
                self.store.missing_documents(p['scope'], p['id'], set(names))
            finally:
                os.close(fd)
        except (Fault, OSError) as exc:
            code = exc.code if isinstance(exc, Fault) else 'source_unavailable'
            errors.append({'file': None, 'code': code})
            self.store.source_failed(p['scope'], p['id'])
        self.health = {'configured': True, 'status': 'attention' if errors else 'ready',
                       'last_scan': self.store.now(), 'errors': errors[:32], 'scanned_files': len(names)}
        return self.health


class Supervisor:
    """Runs only while the explicitly launched desk command is alive.

    Ingests a fixed local source and processes one previously approved local draft
    per cycle. Pausing waits for an in-progress cycle, then prevents new scans/effects.
    """
    def __init__(self, store, owner_bearer, source_bearer, root, interval=2.0):
        if not 0.05 <= interval <= 60:
            raise Fault('invalid_interval')
        self.store, self.owner = store, owner_bearer
        self.principal = store.principal(owner_bearer, {'owner'})
        self.source = ProjectFiles(store, source_bearer, root)
        if self.principal['scope'] != self.source.principal['scope']:
            raise Fault('connector_scope_mismatch')
        self.scope, self.interval = self.principal['scope'], interval
        self.lock, self.stop_event = threading.RLock(), threading.Event()
        self.thread = None
        self.last_cycle = None
        self.worker_status = 'starting'
        self.error = None

    def cycle(self):
        with self.lock:
            if self.store.paused(self.scope):
                self.worker_status = 'paused'
                return
            try:
                self.store.principal(self.owner, {'owner'})
                self.source.scan()
                result = self.store.tick(self.owner)
                self.worker_status, self.error = result['state'], None
            except Fault as exc:
                self.worker_status, self.error = 'attention', exc.code
            except Exception:
                # Never leak file contents, request text or credentials in diagnostics.
                self.worker_status, self.error = 'attention', 'worker_failed'
            self.last_cycle = self.store.now()

    def set_paused(self, bearer, paused):
        with self.lock:
            p = self.store.principal(bearer, {'owner'})
            if p['scope'] != self.scope:
                raise Fault('worker_not_configured', 409)
            result = self.store.set_paused(bearer, paused)
            if paused:
                self.worker_status = 'paused'
            return result

    def view(self, scope):
        if scope != self.scope:
            return {'configured': False, 'status': 'not_configured', 'source': None}
        with self.lock:
            return {'configured': True, 'status': 'paused' if self.store.paused(scope) else self.worker_status,
                    'last_cycle': self.last_cycle, 'error': self.error, 'interval_seconds': self.interval,
                    'source': dict(self.source.health), 'foreground_process_required': True,
                    'capability': 'message.draft', 'external_effects': False}

    def start(self):
        if self.thread and self.thread.is_alive():
            raise Fault('supervisor_already_running')
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                self.cycle()
                self.stop_event.wait(self.interval)
        self.thread = threading.Thread(target=loop, name='alfred-desk-loop', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise Fault('supervisor_stop_timeout')
