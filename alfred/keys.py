"""Key custody for ALFRED's encryption: one master key, a key per area, several ways in.

Integration plan phase 1, plan item 1.1 (SYS-002, M05). A keyring file holds:

* the master key, locked once for each unlock method (the macOS keychain, a passphrase,
  a secret file that a server's secret store provides, and the recovery key), so any one
  of them opens it and none of their secrets is stored in the file;
* one key for each area (personal, company, each client), locked by the master key.
  Destroying an area's key makes everything sealed with it unreadable, wherever copies of
  the sealed data went.

The keyring is a file of its own beside the database, so a database backup never carries
the keys that open it. Unlock methods are pluggable: ``register`` adds another (a cloud key
vault, for example) without changing the file format. This module reads and writes the
keyring and seals and opens values; the host starts sealing its records in the next phase 1
step. Design, risks and limits: docs/ENCRYPTION.md.

Sealing needs the ``cryptography`` package (AES-256-GCM), pinned in
requirements/encryption.txt. Passphrases are stretched with the standard library's scrypt.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import copy
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import unicodedata

from .local import Fault, ident

FORMAT, VERSION = 'alfred-keyring', 1
KEYRING_FILE = 'desk-keyring.json'
DEFAULT_DATA_DIR = '~/.local/share/alfred/desk-demo'
# The same three classes as alfred.brain.SCOPE_CLASSES; a test keeps them equal.
AREA_KINDS = ('personal', 'company', 'client')
KEY_BYTES, NONCE_BYTES, TAG_BYTES, SALT_BYTES = 32, 12, 16, 16
# scrypt at N=2**17, r=8, p=1 takes 128 MiB and about a second. The limits stop a tampered
# keyring from asking for more memory than that allows.
SCRYPT = {'n': 2 ** 17, 'r': 8, 'p': 1}
SCRYPT_LIMITS = {'n': 2 ** 18, 'r': 8, 'p': 2}
SCRYPT_MAXMEM = 2 ** 29
MIN_PASSPHRASE = 12
MIN_SECRET_FILE, MAX_SECRET_FILE = 32, 4096
# 23 random bytes (184 bits) and a 2-byte check: 40 Crockford base32 characters in 8 groups.
RECOVERY_RANDOM, RECOVERY_CHECK, RECOVERY_LENGTH = 23, 2, 40
CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
KEYCHAIN_SERVICE = 'alfred.keyring'
SEAL_PREFIX = 'alfred-seal'
MAX_SLOTS, MAX_AREAS, MAX_VERSIONS, MAX_KEYRING_BYTES = 16, 256, 16, 1 << 20
MAX_AREA_NAME = 80
HEX_ID = re.compile(r'[0-9a-f]{8}')
# No length cap here: every keyring field checks its decoded length, and sealed values may be large.
B64 = re.compile(r'[A-Za-z0-9_-]*')


# Encoding and derivation -------------------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(bytes(raw)).decode('ascii').rstrip('=')


def _unb64(value) -> bytes:
    if not isinstance(value, str) or not B64.fullmatch(value) or len(value) % 4 == 1:
        raise Fault('keyring_damaged', 409)
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _label(*parts) -> bytes:
    """Unambiguous, domain-separated context for every derivation and every sealed value."""
    return json.dumps(['alfred-keyring', VERSION, *parts], separators=(',', ':'), ensure_ascii=True).encode()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def hkdf(ikm: bytes, salt: bytes, info: bytes, length: int = KEY_BYTES) -> bytes:
    """HKDF with SHA-256 (RFC 5869)."""
    prk = hmac.new(bytes(salt) or bytes(32), bytes(ikm), hashlib.sha256).digest()
    out, block, counter = b'', b'', 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _aesgcm(key):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise Fault('encryption_library_missing', 503) from None
    return AESGCM(bytes(key))


def _lock(key, plaintext, aad: bytes) -> str:
    nonce = secrets.token_bytes(NONCE_BYTES)
    return _b64(nonce + _aesgcm(key).encrypt(nonce, bytes(plaintext), aad))


def _open(key, blob, aad: bytes, fault='wrong_key') -> bytes:
    raw = _unb64(blob)
    if len(raw) < NONCE_BYTES + TAG_BYTES:
        raise Fault('keyring_damaged', 409)
    cipher = _aesgcm(key)
    from cryptography.exceptions import InvalidTag
    try:
        return cipher.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad)
    except InvalidTag:
        raise Fault(fault, 403) from None


def _zero(buffer: bytearray) -> None:
    for i in range(len(buffer)):
        buffer[i] = 0


# Recovery key ------------------------------------------------------------

def _recovery_check(raw: bytes) -> bytes:
    return hashlib.sha256(_label('recovery-check') + raw).digest()[:RECOVERY_CHECK]


def recovery_text(raw: bytes) -> str:
    """Print form of a recovery key: 8 groups of 5 characters, with a check against typos."""
    if len(raw) != RECOVERY_RANDOM:
        raise Fault('invalid_recovery_key')
    number = int.from_bytes(raw + _recovery_check(raw), 'big')
    digits = ''.join(CROCKFORD[(number >> (5 * i)) & 31] for i in reversed(range(RECOVERY_LENGTH)))
    return '-'.join(digits[i:i + 5] for i in range(0, RECOVERY_LENGTH, 5))


def parse_recovery(value) -> bytes:
    """Read a typed recovery key. Case, spaces and hyphens do not matter; O reads as 0, and I and L as 1."""
    if not isinstance(value, str) or len(value) > 200:
        raise Fault('recovery_key_mistyped')
    cleaned = ''.join(value.split()).replace('-', '').upper().translate(str.maketrans('OIL', '011'))
    if len(cleaned) != RECOVERY_LENGTH or any(c not in CROCKFORD for c in cleaned):
        raise Fault('recovery_key_mistyped')
    number = 0
    for character in cleaned:
        number = number * 32 + CROCKFORD.index(character)
    whole = number.to_bytes(RECOVERY_RANDOM + RECOVERY_CHECK, 'big')
    raw, check = whole[:RECOVERY_RANDOM], whole[RECOVERY_RANDOM:]
    if not hmac.compare_digest(check, _recovery_check(raw)):
        raise Fault('recovery_key_mistyped')
    return raw


# Unlock methods ----------------------------------------------------------

class UnlockMethod:
    """One way to open the master key. The secret it supplies never goes into the keyring file.

    ``enrol`` creates or fetches the secret for a new slot and returns the slot's non-secret
    settings with it; ``secret`` supplies it again at unlock, or raises
    ``Fault('unlock_unavailable')`` when it cannot here; ``withdraw`` removes anything the
    method stored elsewhere when its slot is removed.
    """
    name = ''
    title = ''

    def enrol(self, keyring_id: str, slot_id: str) -> tuple[dict, bytes]:
        raise NotImplementedError

    def secret(self, keyring_id: str, slot_id: str, settings: dict) -> bytes:
        raise NotImplementedError

    def withdraw(self, keyring_id: str, slot_id: str, settings: dict) -> None:
        return None

    @staticmethod
    def where(settings: dict) -> str:
        return ''


def _security(arguments, stdin=None) -> str:
    """Run macOS's own keychain tool. Secrets go in on standard input, never in arguments."""
    if sys.platform != 'darwin':
        raise Fault('keychain_unavailable', 503)
    try:
        run = subprocess.run(['/usr/bin/security', *arguments], input=stdin, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise Fault('keychain_unavailable', 503) from None
    if run.returncode:
        raise Fault('keychain_unavailable', 503)
    return run.stdout


class Keychain(UnlockMethod):
    """A random secret in your macOS login keychain, which opens while you are logged in."""
    name, title = 'keychain', 'macOS keychain'

    def __init__(self, run=None):
        self._run = run or _security

    @staticmethod
    def _account(keyring_id, slot_id):
        return f'{keyring_id}.{slot_id}'

    def enrol(self, keyring_id, slot_id):
        secret = secrets.token_bytes(KEY_BYTES)
        account = self._account(keyring_id, slot_id)
        # Interactive mode reads the command from standard input, so the secret never shows
        # in a process listing. Reading it back is the check that it was stored.
        self._run(['-i'], f'add-generic-password -U -a {account} -s {KEYCHAIN_SERVICE} -w {secret.hex()}\n')
        settings = {'service': KEYCHAIN_SERVICE, 'account': account}
        if not hmac.compare_digest(self.secret(keyring_id, slot_id, settings), secret):
            raise Fault('keychain_unavailable', 503)
        return settings, secret

    def secret(self, keyring_id, slot_id, settings):
        if settings != {'service': KEYCHAIN_SERVICE, 'account': self._account(keyring_id, slot_id)}:
            raise Fault('keyring_damaged', 409)
        value = self._run(['find-generic-password', '-a', settings['account'], '-s', settings['service'], '-w']).strip()
        if not re.fullmatch(r'[0-9a-f]{64}', value):
            raise Fault('keychain_unavailable', 503)
        return bytes.fromhex(value)

    def withdraw(self, keyring_id, slot_id, settings):
        try:
            self._run(['delete-generic-password', '-a', settings['account'], '-s', settings['service']])
        except Fault:
            pass  # already gone, or not on this Mac

    @staticmethod
    def where(settings):
        return f"login keychain item {settings.get('service')} / {settings.get('account')}"


class Passphrase(UnlockMethod):
    """A passphrase you type, stretched with scrypt. It is kept nowhere but in your memory."""
    name, title = 'passphrase', 'passphrase'

    def __init__(self, passphrase: str | None = None):
        if passphrase is not None and not isinstance(passphrase, str):
            raise Fault('invalid_passphrase')
        self._value = None if passphrase is None else unicodedata.normalize('NFC', passphrase)

    def enrol(self, keyring_id, slot_id):
        if self._value is None or len(self._value) < MIN_PASSPHRASE:
            raise Fault('passphrase_too_short')
        settings = {'kdf': 'scrypt', **SCRYPT, 'salt': _b64(secrets.token_bytes(SALT_BYTES))}
        return settings, self._stretch(settings)

    def secret(self, keyring_id, slot_id, settings):
        if self._value is None:
            raise Fault('unlock_unavailable', 503)
        return self._stretch(settings)

    def _stretch(self, settings):
        if set(settings) != {'kdf', 'n', 'r', 'p', 'salt'} or settings['kdf'] != 'scrypt':
            raise Fault('keyring_damaged', 409)
        for name in ('n', 'r', 'p'):
            value = settings[name]
            if type(value) is not int or not 1 <= value <= SCRYPT_LIMITS[name]:
                raise Fault('keyring_damaged', 409)
        if settings['n'] < 2 or settings['n'] & (settings['n'] - 1):
            raise Fault('keyring_damaged', 409)
        return hashlib.scrypt(self._value.encode('utf-8'), salt=_unb64(settings['salt']), n=settings['n'],
                              r=settings['r'], p=settings['p'], maxmem=SCRYPT_MAXMEM, dklen=KEY_BYTES)

    @staticmethod
    def where(settings):
        return f"typed at start (scrypt N={settings.get('n')}, r={settings.get('r')}, p={settings.get('p')})"


def read_secret_file(path) -> bytes:
    """A server secret: a regular file only its owner (or root) can read, at least 32 bytes long."""
    try:
        # Non-blocking, so a pipe or device put in its place cannot hang the start.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    except OSError:
        raise Fault('unlock_unavailable', 503) from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Fault('secret_file_not_regular', 409)
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise Fault('secret_file_too_open', 409)
        if hasattr(os, 'getuid') and info.st_uid not in (os.getuid(), 0):
            raise Fault('secret_file_wrong_owner', 409)
        if info.st_size > MAX_SECRET_FILE:
            raise Fault('secret_file_too_long', 409)
        raw = b''
        while len(raw) <= MAX_SECRET_FILE:
            chunk = os.read(fd, MAX_SECRET_FILE + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)
    raw = raw.strip()
    if len(raw) > MAX_SECRET_FILE:
        raise Fault('secret_file_too_long', 409)
    if len(raw) < MIN_SECRET_FILE:
        raise Fault('secret_file_too_short', 409)
    return raw


def new_server_secret() -> str:
    """A fresh secret for a server's secret store: 48 random bytes, base64."""
    return base64.b64encode(secrets.token_bytes(48)).decode('ascii') + '\n'


class SecretFile(UnlockMethod):
    """A secret file that a server's secret store puts in place before ALFRED starts.

    ``path`` names the file directly (a Docker or Kubernetes secret, a HashiCorp Vault agent
    template). ``credential`` names a systemd credential, found in ``$CREDENTIALS_DIRECTORY``
    at start, which systemd can keep encrypted at rest and bound to the server's TPM. Given
    both, the slot is enrolled from the file at ``path`` (the plain copy, before it goes into
    systemd and is deleted) and opened from the credential afterwards.
    """
    name, title = 'secret-file', 'server secret file'

    def __init__(self, path=None, *, credential=None, environ=None):
        self._path, self._credential = path, credential
        self._environ = os.environ if environ is None else environ

    def _absolute(self):
        path = Path(self._path).expanduser()
        if not path.is_absolute():
            raise Fault('secret_file_path_not_absolute')
        return path

    def enrol(self, keyring_id, slot_id):
        if self._credential is not None:
            settings = {'credential': ident(self._credential)}
            if self._path is not None:
                return settings, read_secret_file(self._absolute())
        elif self._path is not None:
            settings = {'path': str(self._absolute())}
        else:
            raise Fault('invalid_secret_file')
        return settings, self.secret(keyring_id, slot_id, settings)

    def secret(self, keyring_id, slot_id, settings):
        if set(settings) == {'credential'}:
            directory = self._environ.get('CREDENTIALS_DIRECTORY')
            if not directory:
                raise Fault('unlock_unavailable', 503)
            path = Path(directory) / ident(settings['credential'])
        elif set(settings) == {'path'} and isinstance(settings['path'], str) and Path(settings['path']).is_absolute():
            path = Path(settings['path'])
        else:
            raise Fault('keyring_damaged', 409)
        return read_secret_file(path)

    @staticmethod
    def where(settings):
        if 'credential' in settings:
            return f"systemd credential {settings['credential']}"
        return f"file {settings.get('path')}"


class RecoveryKey(UnlockMethod):
    """The recovery key, shown once when the keyring is made, for paper or a password manager."""
    name, title = 'recovery', 'recovery key'

    def __init__(self, text: str | None = None):
        self.text = text

    def enrol(self, keyring_id, slot_id):
        raw = secrets.token_bytes(RECOVERY_RANDOM)
        self.text = recovery_text(raw)
        return {}, raw

    def secret(self, keyring_id, slot_id, settings):
        if self.text is None:
            raise Fault('unlock_unavailable', 503)
        if settings != {}:
            raise Fault('keyring_damaged', 409)
        return parse_recovery(self.text)

    @staticmethod
    def where(settings):
        return 'kept offline by you'


METHODS: dict[str, type[UnlockMethod]] = {m.name: m for m in (Keychain, Passphrase, SecretFile, RecoveryKey)}


def register(method: type[UnlockMethod]) -> type[UnlockMethod]:
    """Add another unlock method, such as a cloud key vault, under a name of its own."""
    if not (isinstance(method, type) and issubclass(method, UnlockMethod)) or \
            not re.fullmatch(r'[a-z][a-z0-9-]{1,31}', method.name or '') or method.name in METHODS:
        raise Fault('invalid_unlock_method')
    METHODS[method.name] = method
    return method


# The keyring file ----------------------------------------------------------

def _validate(data) -> dict:
    """Check every field of a keyring read from disk; anything unexpected is damage."""
    def bad():
        return Fault('keyring_damaged', 409)

    def number(value):
        if type(value) is not int or not 0 <= value <= 2 ** 53:
            raise bad()

    def label(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 80 or any(ord(c) < 32 for c in value):
            raise bad()

    if type(data) is not dict or set(data) != {'format', 'version', 'id', 'created', 'generation', 'slots', 'areas',
                                               'destroyed', 'mac'}:
        raise bad()
    if data['format'] != FORMAT:
        raise bad()
    if data['version'] != VERSION:
        raise Fault('unsupported_keyring_version', 409)
    if not isinstance(data['id'], str) or not re.fullmatch(r'[0-9a-f]{32}', data['id']):
        raise bad()
    number(data['created']); number(data['generation'])
    if not isinstance(data['mac'], str) or not re.fullmatch(r'[0-9a-f]{64}', data['mac']):
        raise bad()
    slots, areas, destroyed = data['slots'], data['areas'], data['destroyed']
    if type(slots) is not list or not 1 <= len(slots) <= MAX_SLOTS or type(areas) is not list \
            or len(areas) > MAX_AREAS or type(destroyed) is not list or len(destroyed) > 4 * MAX_AREAS:
        raise bad()
    for slot in slots:
        if type(slot) is not dict or set(slot) != {'id', 'method', 'label', 'created', 'salt', 'settings', 'master'}:
            raise bad()
        if not isinstance(slot['id'], str) or not HEX_ID.fullmatch(slot['id']):
            raise bad()
        if not isinstance(slot['method'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,31}', slot['method']):
            raise bad()
        label(slot['label']); number(slot['created'])
        if len(_unb64(slot['salt'])) != SALT_BYTES or type(slot['settings']) is not dict:
            raise bad()
        if len(_canonical(slot['settings'])) > 1024 or len(_unb64(slot['master'])) != NONCE_BYTES + KEY_BYTES + TAG_BYTES:
            raise bad()
    if len({s['id'] for s in slots}) != len(slots) or sum(s['method'] == 'recovery' for s in slots) != 1:
        raise bad()
    for area in areas:
        if type(area) is not dict or set(area) != {'id', 'kind', 'name', 'created', 'keys'}:
            raise bad()
        try:
            ident(area['id'])
        except Fault:
            raise bad() from None
        if area['kind'] not in AREA_KINDS or type(area['keys']) is not list or not 1 <= len(area['keys']) <= MAX_VERSIONS:
            raise bad()
        number(area['created'])
        if not NONCE_BYTES + TAG_BYTES < len(_unb64(area['name'])) <= NONCE_BYTES + TAG_BYTES + 4 * MAX_AREA_NAME:
            raise bad()
        for position, key in enumerate(area['keys'], 1):
            if type(key) is not dict or set(key) != {'version', 'created', 'key'} or key['version'] != position:
                raise bad()
            number(key['created'])
            if len(_unb64(key['key'])) != NONCE_BYTES + KEY_BYTES + TAG_BYTES:
                raise bad()
    for entry in destroyed:
        if type(entry) is not dict or set(entry) != {'id', 'kind', 'destroyed'} or entry['kind'] not in AREA_KINDS:
            raise bad()
        number(entry['destroyed'])
        try:
            ident(entry['id'])
        except Fault:
            raise bad() from None
    names = [a['id'] for a in areas] + [d['id'] for d in destroyed]
    if len(set(names)) != len(names):
        raise bad()
    return data


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write(path: Path, data: dict, *, new=False) -> None:
    """Write the whole file to a private temporary file, then move it into place in one step."""
    raw = json.dumps(data, indent=1, sort_keys=True).encode() + b'\n'
    temporary = path.with_name(f'.{path.name}.{secrets.token_hex(6)}.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if new and (path.exists() or path.is_symlink()):
            raise Fault('keyring_exists', 409)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    _fsync_directory(path.parent)


@contextmanager
def _file_lock(path: Path):
    import fcntl
    fd = os.open(path.with_name(path.name + '.lock'), os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def keyring_path(data_dir=DEFAULT_DATA_DIR, keyring=None) -> Path:
    return Path(keyring if keyring else Path(data_dir) / KEYRING_FILE).expanduser().absolute()


class Keyring:
    """A keyring as read from disk. Reading opens nothing: it shows the unlock methods and areas only."""

    def __init__(self, path: Path, data: dict):
        self.path, self.data = path, data

    @property
    def id(self) -> str:
        return self.data['id']

    @classmethod
    def read(cls, path) -> 'Keyring':
        path = Path(path).expanduser().absolute()
        if path.is_symlink():
            raise Fault('keyring_symlink_rejected', 409)
        try:
            with open(path, 'rb') as stream:
                raw = stream.read(MAX_KEYRING_BYTES + 1)
        except FileNotFoundError:
            raise Fault('keyring_not_found', 404) from None
        if len(raw) > MAX_KEYRING_BYTES:
            raise Fault('keyring_damaged', 409)
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeError, ValueError, RecursionError):
            raise Fault('keyring_damaged', 409) from None
        return cls(path, _validate(data))

    @classmethod
    def create(cls, path, first: UnlockMethod, *, label=None, clock=time.time) -> tuple['OpenKeyring', str]:
        """A new keyring with a fresh master key, a recovery key and one other unlock method.

        Returns the open keyring and the recovery key's print form, which is shown once and
        kept nowhere.
        """
        path = Path(path).expanduser().absolute()
        if path.exists() or path.is_symlink():
            raise Fault('keyring_exists', 409)
        if first.name == RecoveryKey.name:
            raise Fault('invalid_unlock_method')
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = int(clock())
        data = {'format': FORMAT, 'version': VERSION, 'id': secrets.token_hex(16), 'created': now, 'generation': 1,
                'slots': [], 'areas': [], 'destroyed': [], 'mac': ''}
        opened = OpenKeyring(cls(path, data), bytearray(secrets.token_bytes(KEY_BYTES)), None, clock)
        recovery = RecoveryKey()
        enrolled = []
        try:
            with _file_lock(path):
                opened._enrol(data, recovery, None, now)
                opened._enrol(data, first, label, now)
                enrolled.append(data['slots'][-1])
                data['mac'] = opened._mac(data)
                _write(path, _validate(data), new=True)
        except BaseException:
            for slot in enrolled:
                first.withdraw(data['id'], slot['id'], slot['settings'])
            opened.close()
            raise
        return opened, recovery.text

    def slots(self, method: str | None = None) -> list[dict]:
        return [s for s in self.data['slots'] if method is None or s['method'] == method]

    def view(self) -> dict:
        """Everything about the keyring that is safe to show: no key and no secret."""
        def where(slot):
            method = METHODS.get(slot['method'])
            return method.where(slot['settings']) if method else 'an unlock method this ALFRED does not know'
        return {'keyring': str(self.path), 'id': self.id, 'created': self.data['created'],
                'generation': self.data['generation'],
                'unlock': [{'slot': s['id'], 'method': s['method'], 'label': s['label'], 'created': s['created'],
                            'where': where(s)} for s in self.data['slots']],
                'areas': [{'id': a['id'], 'kind': a['kind'], 'created': a['created'],
                           'key_versions': len(a['keys'])} for a in self.data['areas']],
                'destroyed': [dict(d) for d in self.data['destroyed']]}

    def unlock(self, method: UnlockMethod, slot: str | None = None, *, clock=time.time) -> 'OpenKeyring':
        """Open the master key with ``method``, trying each of its slots (or only ``slot``)."""
        candidates = [s for s in self.slots(method.name) if slot is None or s['id'] == slot]
        if not candidates:
            raise Fault('no_such_unlock_method', 404)
        failure = None
        for record in candidates:
            try:
                secret = method.secret(self.id, record['id'], record['settings'])
                key = hkdf(secret, _unb64(record['salt']), _label('slot', record['method'], self.id, record['id']))
                master = _open(key, record['master'], _label('master', self.id, record['id'], record['method']))
            except Fault as exc:
                failure = exc
                continue
            opened = OpenKeyring(self, bytearray(master), record['id'], clock)
            try:
                opened._verify(self.data)
            except Fault:
                opened.close()
                raise
            return opened
        raise failure


class OpenKeyring:
    """The keyring with its master key open in memory. Close it when done.

    Python cannot promise to wipe every copy of a key from memory; ``close`` clears the
    master key's buffer and forgets the area keys, which is the best it offers.
    """

    def __init__(self, keyring: Keyring, master: bytearray, slot: str | None, clock=time.time):
        self.keyring, self._master, self.slot, self.clock = keyring, master, slot, clock
        self._areas: dict[tuple[str, int], bytes] = {}

    @property
    def id(self) -> str:
        return self.keyring.id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        if self._master is not None:
            _zero(self._master)
        self._master = None
        self._areas.clear()

    def _key(self, purpose: str) -> bytes:
        if self._master is None:
            raise Fault('keyring_closed', 409)
        return hkdf(bytes(self._master), b'', _label(purpose, self.id))

    def _mac(self, data: dict) -> str:
        body = {k: v for k, v in data.items() if k != 'mac'}
        return hmac.new(self._key('mac'), _canonical(body), hashlib.sha256).hexdigest()

    def _verify(self, data: dict) -> None:
        if not hmac.compare_digest(self._mac(data), data['mac']):
            raise Fault('keyring_tampered', 409)

    def _enrol(self, data: dict, method: UnlockMethod, label, now) -> str:
        if len(data['slots']) >= MAX_SLOTS:
            raise Fault('too_many_unlock_methods', 409)
        taken = {s['id'] for s in data['slots']}
        slot_id = secrets.token_hex(4)
        while slot_id in taken:
            slot_id = secrets.token_hex(4)
        settings, secret = method.enrol(self.id, slot_id)
        salt = secrets.token_bytes(SALT_BYTES)
        key = hkdf(secret, salt, _label('slot', method.name, self.id, slot_id))
        data['slots'].append({'id': slot_id, 'method': method.name, 'label': label or method.title or method.name,
                              'created': now, 'salt': _b64(salt), 'settings': settings,
                              'master': _lock(key, self._master, _label('master', self.id, slot_id, method.name))})
        return slot_id

    @contextmanager
    def _change(self):
        """Read the file again under a lock, apply one change and write it back with a new seal."""
        self._key('mac')
        with _file_lock(self.keyring.path):
            current = Keyring.read(self.keyring.path)
            if current.id != self.id or current.data['generation'] != self.keyring.data['generation']:
                raise Fault('keyring_changed', 409)
            self._verify(current.data)
            data = copy.deepcopy(current.data)
            yield data
            data['generation'] += 1
            data['mac'] = self._mac(data)
            _write(self.keyring.path, _validate(data))
            self.keyring.data = data

    # Unlock methods ------------------------------------------------------

    def add_unlock(self, method: UnlockMethod, label: str | None = None) -> str:
        if method.name == RecoveryKey.name:
            raise Fault('use_new_recovery', 409)
        enrolled = None
        try:
            with self._change() as data:
                slot = self._enrol(data, method, label, int(self.clock()))
                enrolled = data['slots'][-1]
        except BaseException:
            if enrolled:
                method.withdraw(self.id, enrolled['id'], enrolled['settings'])
            raise
        return slot

    def remove_unlock(self, slot: str, *, method: UnlockMethod | None = None) -> dict:
        """Remove an unlock method; ``method`` withdraws its stored secret (a keychain item, say)."""
        with self._change() as data:
            found = [s for s in data['slots'] if s['id'] == slot]
            if not found:
                raise Fault('no_such_unlock_method', 404)
            if found[0]['method'] == RecoveryKey.name:
                raise Fault('recovery_key_required', 409)
            data['slots'].remove(found[0])
        if method is None and found[0]['method'] in METHODS:
            method = METHODS[found[0]['method']]()
        if method is not None:
            method.withdraw(self.id, slot, found[0]['settings'])
        return {'slot': slot, 'method': found[0]['method']}

    def new_recovery(self) -> str:
        """Replace the recovery key. The old one stops opening this keyring, though not older copies of it."""
        recovery = RecoveryKey()
        with self._change() as data:
            data['slots'] = [s for s in data['slots'] if s['method'] != RecoveryKey.name]
            self._enrol(data, recovery, None, int(self.clock()))
        return recovery.text

    # Areas ---------------------------------------------------------------

    def _wrap_label(self, area: str, version: int) -> bytes:
        return _label('area', self.id, area, version)

    def add_area(self, area: str | None, kind: str, label: str | None = None) -> dict:
        """Add an area with its own key. ``label`` is its name for people ("Acme Ltd"), kept sealed.

        The area's id is written in the clear beside every value sealed with it, so with no
        ``area`` ALFRED makes a neutral one, such as ``client-3f9a2b1c``, that names no one.
        """
        if kind not in AREA_KINDS:
            raise Fault('invalid_area_kind')
        if area is not None:
            ident(area)
        if label is not None and (not isinstance(label, str) or not 1 <= len(label) <= MAX_AREA_NAME
                                  or any(ord(c) < 32 for c in label)):
            raise Fault('invalid_label')
        with self._change() as data:
            taken = {a['id'] for a in data['areas']} | {d['id'] for d in data['destroyed']}
            if area is None:
                area = f'{kind}-{secrets.token_hex(4)}'
                while area in taken:
                    area = f'{kind}-{secrets.token_hex(4)}'
            if any(a['id'] == area for a in data['areas']):
                raise Fault('area_exists', 409)
            if any(d['id'] == area for d in data['destroyed']):
                raise Fault('area_was_destroyed', 409)
            if len(data['areas']) >= MAX_AREAS:
                raise Fault('too_many_areas', 409)
            now = int(self.clock())
            key = _lock(self._key('wrap'), secrets.token_bytes(KEY_BYTES), self._wrap_label(area, 1))
            name = _lock(self._key('names'), (label or area).encode('utf-8'), _label('area-name', self.id, area))
            data['areas'].append({'id': area, 'kind': kind, 'name': name, 'created': now,
                                  'keys': [{'version': 1, 'created': now, 'key': key}]})
        return {'area': area, 'kind': kind, 'key_versions': 1}

    def areas(self) -> list[dict]:
        """The areas with their names opened; ``Keyring.view`` shows them without names."""
        return [{'id': a['id'], 'kind': a['kind'],
                 'label': _open(self._key('names'), a['name'], _label('area-name', self.id, a['id']),
                                fault='keyring_tampered').decode('utf-8'),
                 'created': a['created'], 'key_versions': len(a['keys'])} for a in self.keyring.data['areas']]

    def rotate_area(self, area: str) -> dict:
        """A new key version for new seals. Older versions stay until their values are sealed again."""
        with self._change() as data:
            record = self._area(data, area)
            if len(record['keys']) >= MAX_VERSIONS:
                raise Fault('too_many_key_versions', 409)
            version = len(record['keys']) + 1
            record['keys'].append({'version': version, 'created': int(self.clock()),
                                   'key': _lock(self._key('wrap'), secrets.token_bytes(KEY_BYTES),
                                                self._wrap_label(area, version))})
        return {'area': area, 'key_versions': version}

    def destroy_area(self, area: str) -> dict:
        """Delete an area's keys. Everything sealed with them becomes unreadable; this cannot be undone."""
        with self._change() as data:
            record = self._area(data, area)
            data['areas'].remove(record)
            data['destroyed'].append({'id': area, 'kind': record['kind'], 'destroyed': int(self.clock())})
        for cached in [k for k in self._areas if k[0] == area]:
            del self._areas[cached]
        return {'area': area, 'destroyed': True, 'key_versions_deleted': len(record['keys'])}

    def _area(self, data: dict, area: str) -> dict:
        for record in data['areas']:
            if record['id'] == area:
                return record
        if any(d['id'] == area for d in data['destroyed']):
            raise Fault('area_destroyed', 410)
        raise Fault('unknown_area', 404)

    def area_key(self, area: str, version: int | None = None) -> tuple[int, bytes]:
        record = self._area(self.keyring.data, area)
        version = len(record['keys']) if version is None else version
        if type(version) is not int or not 1 <= version <= len(record['keys']):
            raise Fault('unknown_key_version', 404)
        if (area, version) not in self._areas:
            self._areas[(area, version)] = _open(self._key('wrap'), record['keys'][version - 1]['key'],
                                                 self._wrap_label(area, version), fault='keyring_tampered')
        return version, self._areas[(area, version)]

    # Sealing ---------------------------------------------------------------

    def _value_key(self, key: bytes, salt: bytes, area: str, version: int) -> bytes:
        return hkdf(key, salt, _label('value-key', self.id, area, version))

    def seal(self, area: str, plaintext: bytes | str, context: str) -> str:
        """Seal a value with its area's newest key. ``context`` (table, column, row) must match to open it.

        Each value is sealed under its own key, derived from the area key and a random salt.
        An area key can then seal any number of values without reaching AES-GCM's limit on
        random nonces under one key, and the area key itself is only ever used to derive keys.
        """
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        if not isinstance(context, str):
            raise Fault('invalid_context')
        version, key = self.area_key(area)
        salt, nonce = secrets.token_bytes(SALT_BYTES), secrets.token_bytes(NONCE_BYTES)
        sealed = _aesgcm(self._value_key(key, salt, area, version)).encrypt(
            nonce, plaintext, _label('seal', self.id, area, version, context))
        return f'{SEAL_PREFIX}:{VERSION}:{area}:{version}:{_b64(salt + nonce + sealed)}'

    def open(self, area: str, sealed: str, context: str) -> bytes:
        parts = sealed.split(':') if isinstance(sealed, str) else []
        if len(parts) != 5 or parts[0] != SEAL_PREFIX or parts[1] != str(VERSION) or not re.fullmatch(r'[1-9][0-9]?', parts[3]):
            raise Fault('not_sealed')
        if parts[2] != area:
            raise Fault('sealed_for_another_area', 403)
        if not isinstance(context, str):
            raise Fault('invalid_context')
        version, key = self.area_key(area, int(parts[3]))
        raw = _unb64(parts[4])
        if len(raw) < SALT_BYTES + NONCE_BYTES + TAG_BYTES:
            raise Fault('seal_does_not_match', 403)
        salt, nonce, body = raw[:SALT_BYTES], raw[SALT_BYTES:SALT_BYTES + NONCE_BYTES], raw[SALT_BYTES + NONCE_BYTES:]
        cipher = _aesgcm(self._value_key(key, salt, area, version))
        from cryptography.exceptions import InvalidTag
        try:
            return cipher.decrypt(nonce, body, _label('seal', self.id, area, version, context))
        except InvalidTag:
            raise Fault('seal_does_not_match', 403) from None

    # Copies ----------------------------------------------------------------

    def backup(self, directory) -> Path:
        """A copy for the recovery kit, with only the recovery key's slot, so only that key opens it."""
        directory = Path(directory).expanduser().absolute()
        if directory.is_symlink() or not directory.is_dir():
            raise Fault('backup_directory_missing', 404)
        data = copy.deepcopy(self.keyring.data)
        self._verify(data)
        data['slots'] = [s for s in data['slots'] if s['method'] == RecoveryKey.name]
        data['mac'] = self._mac(data)
        stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime(self.clock()))
        target = directory / f'alfred-keyring-{self.id[:8]}-{stamp}.json'
        _write(target, _validate(data), new=True)
        return target


def restore(source, path, recovery: RecoveryKey, *, clock=time.time) -> OpenKeyring:
    """Put a recovery-kit copy in place, after the recovery key has opened and checked it."""
    path = Path(path).expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise Fault('keyring_exists', 409)
    copy_of = Keyring.read(source)
    opened = copy_of.unlock(recovery, clock=clock)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _file_lock(path):
        _write(path, copy_of.data, new=True)
    opened.keyring = Keyring(path, copy.deepcopy(copy_of.data))
    return opened


def unlock(keyring: Keyring, *, prompt=None, environ=None, run=None, attempts=3, clock=time.time):
    """Open with the first method that works here: a server secret file, the macOS keychain, then a
    typed passphrase if ``prompt`` is given. The recovery key is only ever used when asked for.

    Returns the open keyring and the name of the method that opened it.
    """
    reasons = []
    order = [('secret-file', lambda: SecretFile(environ=environ))]
    if run is not None or sys.platform == 'darwin':
        order.append(('keychain', lambda: Keychain(run)))
    for name, make in order:
        if keyring.slots(name):
            try:
                return keyring.unlock(make(), clock=clock), name
            except Fault as exc:
                if exc.code == 'keyring_tampered':
                    raise
                reasons.append(f'{name}: {exc.code}')
    if keyring.slots('passphrase') and prompt is not None:
        for _ in range(attempts):
            try:
                return keyring.unlock(Passphrase(prompt('ALFRED passphrase: ')), clock=clock), 'passphrase'
            except Fault as exc:
                if exc.code != 'wrong_key':
                    raise
                reasons.append('passphrase: wrong_key')
    error = Fault('no_unlock_available', 423)
    error.reasons = reasons
    raise error


# Full-disk encryption ------------------------------------------------------

def _command(arguments) -> str:
    try:
        run = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise Fault('command_unavailable', 503) from None
    if run.returncode:
        raise Fault('command_failed', 503)
    return run.stdout


def _dm_crypt(sysfs: Path, device: tuple[int, int]) -> str | None:
    """Walk from a block device down through what it sits on; the name of a dm-crypt layer, '' if none, None if unknown."""
    start = sysfs / 'dev' / 'block' / f'{device[0]}:{device[1]}'
    if not start.exists():
        return None
    seen, stack = set(), [start.resolve()]
    while stack:
        node = stack.pop()
        if node in seen or len(seen) > 64:
            continue
        seen.add(node)
        try:
            if (node / 'dm' / 'uuid').read_text().startswith('CRYPT-'):
                return (node / 'dm' / 'name').read_text().strip() if (node / 'dm' / 'name').exists() else node.name
        except OSError:
            pass
        slaves = node / 'slaves'
        if slaves.is_dir():
            stack.extend(child.resolve() for child in slaves.iterdir())
    return ''


def disk_encryption(path, *, system=None, run=None, sysfs='/sys', device=None) -> dict:
    """Whether full-disk encryption protects ``path``: on, off, not_detected or unknown, and why."""
    system = sys.platform if system is None else system
    path = Path(path).expanduser().absolute()
    if system == 'darwin':
        try:
            output = (run or _command)(['/usr/bin/fdesetup', 'status'])
        except Fault:
            return {'status': 'unknown', 'detail': 'fdesetup could not report whether FileVault is on.'}
        if 'FileVault is On' in output:
            return {'status': 'on', 'detail': 'FileVault is on.'}
        if 'FileVault is Off' in output:
            return {'status': 'off', 'detail': 'FileVault is off. Turn it on in System Settings, Privacy & Security.'}
        return {'status': 'unknown', 'detail': 'fdesetup gave an answer ALFRED does not recognise.'}
    if system.startswith('linux'):
        if device is None:
            probe = path
            while not probe.exists() and probe != probe.parent:
                probe = probe.parent
            info = os.stat(probe)
            device = (os.major(info.st_dev), os.minor(info.st_dev))
        if device[0] == 0:
            return {'status': 'unknown', 'detail': f'{path} is on a virtual or network file system (such as overlay, tmpfs, '
                    'btrfs or NFS), so ALFRED cannot see whether the disk beneath it is encrypted.'}
        found = _dm_crypt(Path(sysfs), device)
        if found is None:
            return {'status': 'unknown', 'detail': 'The block device could not be found under /sys.'}
        if found:
            return {'status': 'on', 'detail': f'{path} is on the dm-crypt (LUKS) device {found}.'}
        return {'status': 'not_detected', 'detail': f'{path} is not on a dm-crypt (LUKS) device. A cloud provider may encrypt '
                'the disk outside the server, which ALFRED cannot see; check the provider\'s settings.'}
    return {'status': 'unknown', 'detail': f'ALFRED cannot check full-disk encryption on {system}.'}


# Command line ----------------------------------------------------------------

MESSAGES = {
    'keyring_not_found': 'No keyring here yet. Make one with "python3 -m alfred.keys init --unlock keychain".',
    'keyring_exists': 'A keyring already exists there. ALFRED never overwrites one.',
    'keyring_tampered': 'The keyring opened, but its contents do not match its seal. Restore it from your recovery kit.',
    'keyring_damaged': 'The keyring file is not in a form ALFRED recognises.',
    'keyring_changed': 'Another ALFRED command changed the keyring meanwhile. Run the command again.',
    'wrong_key': 'That did not open the keyring.',
    'recovery_key_mistyped': 'That recovery key has a typing error: check each group of five.',
    'no_unlock_available': 'No unlock method worked here.',
    'passphrase_too_short': f'Use a passphrase of at least {MIN_PASSPHRASE} characters.',
    'keychain_unavailable': 'The macOS keychain could not be used. It works only on a Mac, while you are logged in.',
    'secret_file_too_open': 'The secret file can be read by other users. Make it mode 400 or 600.',
    'secret_file_wrong_owner': 'The secret file belongs to another user.',
    'secret_file_too_short': 'The secret file holds less than 32 bytes. Make one with "python3 -m alfred.keys server-secret".',
    'secret_file_not_regular': 'The secret file is not an ordinary file.',
    'unlock_unavailable': 'That unlock method is not available here.',
    'recovery_key_required': 'The recovery key cannot be removed. Replace it with "new-recovery" instead.',
    'area_destroyed': 'That area\'s keys were destroyed.',
    'area_was_destroyed': 'An area with that name was destroyed before. Choose another name.',
    'encryption_library_missing': 'Install the encryption library first: '
                                  'python3 -m pip install --require-hashes --only-binary :all: -r requirements/encryption.txt',
}


def _ask(label: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(label)
    # Piped in, for example from systemd-ask-password on a server.
    return sys.stdin.readline().rstrip('\n')


def _method(name: str, args) -> UnlockMethod:
    if name == 'keychain':
        return Keychain()
    if name == 'passphrase':
        first = _ask('New ALFRED passphrase: ')
        if sys.stdin.isatty() and _ask('Type it again: ') != first:
            raise Fault('passphrases_differ')
        return Passphrase(first)
    if name == 'secret-file':
        if not args.secret_file and not args.credential:
            raise Fault('secret_file_or_credential_required')
        return SecretFile(args.secret_file, credential=args.credential)
    raise Fault('invalid_unlock_method')


def _open_keyring(args) -> tuple[OpenKeyring, str]:
    keyring = Keyring.read(keyring_path(args.data_dir, args.keyring))
    if args.using == 'recovery':
        return keyring.unlock(RecoveryKey(_ask('Recovery key: '))), 'recovery'
    if args.using == 'passphrase':
        return keyring.unlock(Passphrase(_ask('ALFRED passphrase: '))), 'passphrase'
    if args.using == 'keychain':
        return keyring.unlock(Keychain()), 'keychain'
    if args.using == 'secret-file':
        return keyring.unlock(SecretFile()), 'secret-file'
    return unlock(keyring, prompt=_ask)


def _show_recovery(text: str) -> None:
    print('\nRECOVERY KEY. It is shown once and ALFRED keeps no copy:\n')
    print('    ' + text + '\n')
    print('Write it on paper or keep it in your password manager, away from this computer. With it and a\n'
          'copy of the keyring ("python3 -m alfred.keys backup --to FOLDER"), ALFRED opens on another\n'
          'machine. If you lose it and every other unlock method, your memory cannot be recovered.')


def _print_view(view: dict, disk: dict) -> None:
    print(f"Keyring {view['keyring']}")
    print('Unlock methods:')
    for slot in view['unlock']:
        print(f"  {slot['slot']}  {slot['method']:<12} {slot['label']} ({slot['where']})")
    print('Areas (names are sealed; "areas" shows them):' if view['areas'] else 'Areas: none yet')
    for area in view['areas']:
        print(f"  {area['id']:<24} {area['kind']:<9} key versions: {area['key_versions']}")
    for area in view['destroyed']:
        print(f"  {area['id']:<24} {area['kind']:<9} destroyed")
    print(f"Disk encryption: {disk['status']}. {disk['detail']}")


def run_command(args) -> int:
    path = keyring_path(args.data_dir, args.keyring)
    if args.command == 'disk':
        result = disk_encryption(args.path or path.parent)
        print(json.dumps(result, indent=2) if args.json else f"{result['status']}: {result['detail']}")
        return 0 if result['status'] == 'on' else 1
    if args.command == 'server-secret':
        target = Path(args.output).expanduser().absolute()
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(new_server_secret())
        print(f'Wrote a new server secret to {target} (mode 600).')
        print('Load it into your secret store, then delete this copy. ALFRED only ever reads the store\'s copy.')
        return 0
    if args.command == 'status':
        view = Keyring.read(path).view()
        disk = disk_encryption(path.parent)
        if args.json:
            print(json.dumps(dict(view, disk_encryption=disk), indent=2))
        else:
            _print_view(view, disk)
        return 0
    if args.command == 'init':
        from .placement import check_data_directory
        check_data_directory(path.parent)
        opened, recovery = Keyring.create(path, _method(args.unlock, args), label=args.label)
        with opened:
            print(f'Made a keyring at {path}, opened by the {args.unlock} and by a recovery key.')
            disk = disk_encryption(path.parent)
            print(f"Disk encryption: {disk['status']}. {disk['detail']}")
            _show_recovery(recovery)
        return 0
    if args.command == 'restore':
        from .placement import check_data_directory
        check_data_directory(path.parent)
        opened = restore(args.source, path, RecoveryKey(_ask('Recovery key: ')))
        with opened:
            print(f'Restored the keyring to {path}. Add an unlock method for this machine with "add-unlock".')
        return 0
    opened, how = _open_keyring(args)
    with opened:
        if args.command == 'check':
            print(f'The keyring opened with the {how} and its seal matches.')
        elif args.command == 'add-unlock':
            slot = opened.add_unlock(_method(args.method, args), args.label)
            print(f'Added unlock method {args.method} as slot {slot}.')
        elif args.command == 'remove-unlock':
            opened.remove_unlock(args.slot)
            print(f'Removed unlock slot {args.slot}.')
        elif args.command == 'new-recovery':
            _show_recovery(opened.new_recovery())
            print('The old recovery key no longer opens this keyring. Older backups of the keyring still open with it\n'
                  'until you delete them, so make a new backup and delete the old ones.')
        elif args.command == 'areas':
            listed = opened.areas()
            if args.json:
                print(json.dumps(listed, indent=2))
            else:
                for area in listed:
                    print(f"  {area['id']:<24} {area['kind']:<9} {area['label']}")
                if not listed:
                    print('No areas yet.')
        elif args.command == 'area-add':
            added = opened.add_area(args.area, args.kind, args.label)
            print(f"Added the {args.kind} area {added['area']}.")
        elif args.command == 'area-rotate':
            result = opened.rotate_area(args.area)
            print(f"The {args.area} area now seals with key version {result['key_versions']}.")
        elif args.command == 'area-destroy':
            if args.confirm != args.area:
                raise Fault('confirmation_mismatch')
            opened.destroy_area(args.area)
            print(f'Destroyed the keys of the {args.area} area. What was sealed with them can no longer be read.\n'
                  'Older keyring backups still hold them until you delete those backups.')
        elif args.command == 'backup':
            target = opened.backup(args.to)
            print(f'Wrote {target}. Only the recovery key opens it, so it can be kept anywhere.\n'
                  'Delete older copies after a short while: a destroyed area stays readable from any copy that still has its keys.')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='python3 -m alfred.keys', description='ALFRED key custody: the keyring, its unlock methods and areas.')
    parser.add_argument('--data-dir', default=DEFAULT_DATA_DIR, help='ALFRED data directory; the keyring is desk-keyring.json in it')
    parser.add_argument('--keyring', help='Keyring file, instead of the one in the data directory')
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument('--json', action='store_true', help='Print as JSON')
    opening = argparse.ArgumentParser(add_help=False)
    opening.add_argument('--with', dest='using', choices=tuple(m for m in METHODS),
                         help='Unlock with this method, instead of the first that works here')
    secret = argparse.ArgumentParser(add_help=False)
    secret.add_argument('--secret-file', help='secret-file: absolute path of the secret your secret store provides')
    secret.add_argument('--credential', help='secret-file: name of a systemd credential in $CREDENTIALS_DIRECTORY; '
                        'with --secret-file, enrolled from that plain copy')
    secret.add_argument('--label', help='A name for this unlock method, such as "MacBook" or "server"')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', parents=[secret], help='Make a keyring with a recovery key and one unlock method')
    init.add_argument('--unlock', required=True, choices=('keychain', 'passphrase', 'secret-file'))
    commands.add_parser('status', parents=[output], help='Show unlock methods, areas and disk encryption; opens nothing')
    commands.add_parser('check', parents=[opening], help='Open the keyring and check its seal')
    add = commands.add_parser('add-unlock', parents=[opening, secret], help='Add another unlock method')
    add.add_argument('method', choices=('keychain', 'passphrase', 'secret-file'))
    remove = commands.add_parser('remove-unlock', parents=[opening], help='Remove an unlock method by its slot')
    remove.add_argument('slot')
    commands.add_parser('new-recovery', parents=[opening], help='Replace the recovery key')
    commands.add_parser('areas', parents=[opening, output], help='Open the keyring and list areas with their names')
    area = commands.add_parser('area-add', parents=[opening], help='Add an area with its own key')
    area.add_argument('area', nargs='?', help='A short id, written in the clear beside sealed values; '
                      'left out, ALFRED makes a neutral one')
    area.add_argument('--kind', required=True, choices=AREA_KINDS)
    area.add_argument('--label', help='Its name, such as "Acme Ltd"; kept sealed')
    rotate = commands.add_parser('area-rotate', parents=[opening], help='Start a new key version for an area')
    rotate.add_argument('area')
    destroy = commands.add_parser('area-destroy', parents=[opening], help='Destroy an area\'s keys, for good')
    destroy.add_argument('area')
    destroy.add_argument('--confirm', required=True, help='The area name again')
    backup = commands.add_parser('backup', parents=[opening], help='Write a recovery-kit copy of the keyring')
    backup.add_argument('--to', required=True, help='Folder for the copy')
    restore_command = commands.add_parser('restore', help='Put a recovery-kit copy in place, opened with the recovery key')
    restore_command.add_argument('--from', dest='source', required=True)
    server = commands.add_parser('server-secret', help='Write a new secret for a server\'s secret store')
    server.add_argument('--output', required=True)
    disk = commands.add_parser('disk', parents=[output], help='Check full-disk encryption for the data directory or a path')
    disk.add_argument('path', nargs='?')
    args = parser.parse_args(argv)
    for name in ('using', 'secret_file', 'credential', 'label', 'json'):
        if not hasattr(args, name):
            setattr(args, name, None)
    try:
        return run_command(args)
    except Fault as exc:
        detail = getattr(exc, 'detail', None) or MESSAGES.get(exc.code, '')
        print(f'Refused ({exc.code}). {detail}'.rstrip(), file=sys.stderr)
        for reason in getattr(exc, 'reasons', ()):
            print(f'  {reason}', file=sys.stderr)
        return 1
    except FileExistsError:
        print('Refused (file_exists). ALFRED never overwrites an existing file.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
