"""Key custody (integration plan phase 1, plan 1.1): the keyring, unlock methods and area keys.

Synthetic secrets only. The macOS keychain is exercised through a stand-in for Apple's
``security`` tool, and full-disk encryption through stand-ins for ``fdesetup`` and /sys;
docs/evidence/encryption/RECEIPT.md says what has not yet run on a real Mac or server.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from alfred import keys, recovery
from alfred.brain import SCOPE_CLASSES
from alfred.desk import init_demo
from alfred.local import Fault

REPOSITORY = Path(__file__).resolve().parents[1]
PASSPHRASE = 'correct horse battery staple'
FAST = {'n': 2 ** 10, 'r': 8, 'p': 1}


class FakeSecurity:
    """Stands in for /usr/bin/security: a dictionary of generic passwords, and a record of every call."""

    def __init__(self):
        self.items, self.calls = {}, []

    def __call__(self, arguments, stdin=None):
        self.calls.append((list(arguments), stdin))
        if arguments == ['-i']:
            words = stdin.split()
            assert words[0] == 'add-generic-password', words
            self.items[(words[words.index('-s') + 1], words[words.index('-a') + 1])] = words[words.index('-w') + 1]
            return ''
        command, account, service = arguments[0], arguments[arguments.index('-a') + 1], arguments[arguments.index('-s') + 1]
        if (service, account) not in self.items:
            raise Fault('keychain_unavailable', 503)
        if command == 'find-generic-password':
            return self.items[(service, account)] + '\n'
        if command == 'delete-generic-password':
            del self.items[(service, account)]
            return ''
        raise AssertionError(arguments)


def secret_file(directory: Path, name='secret', mode=0o600, content=None) -> Path:
    path = directory / name
    path.write_text(content if content is not None else keys.new_server_secret())
    os.chmod(path, mode)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'data' / keys.KEYRING_FILE
        patcher = mock.patch.dict(keys.SCRYPT, FAST)
        patcher.start(); self.addCleanup(patcher.stop)

    def make(self, method=None, **kwargs):
        opened, recovery_key = keys.Keyring.create(self.path, method or keys.Passphrase(PASSPHRASE), **kwargs)
        self.addCleanup(opened.close)
        return opened, recovery_key

    def raw(self) -> str:
        return self.path.read_text()


class DerivationTests(unittest.TestCase):
    def test_hkdf_matches_rfc_5869_case_1(self):
        okm = keys.hkdf(bytes.fromhex('0b' * 22), bytes.fromhex('000102030405060708090a0b0c'),
                        bytes.fromhex('f0f1f2f3f4f5f6f7f8f9'), 42)
        self.assertEqual(okm.hex(), '3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865')

    def test_area_kinds_are_the_brain_plug_scope_classes(self):
        self.assertEqual(keys.AREA_KINDS, SCOPE_CLASSES)

    def test_recovery_key_round_trips_and_forgives_how_it_is_typed(self):
        raw = os.urandom(keys.RECOVERY_RANDOM)
        text = keys.recovery_text(raw)
        self.assertRegex(text, r'^([0-9A-HJKMNP-TV-Z]{5}-){7}[0-9A-HJKMNP-TV-Z]{5}$')
        self.assertEqual(keys.parse_recovery(text), raw)
        typed = ' '.join(text.lower().split('-')).replace('0', 'o').replace('1', 'l')
        self.assertEqual(keys.parse_recovery(typed), raw)

    def test_recovery_key_check_catches_a_typing_error(self):
        text = keys.recovery_text(os.urandom(keys.RECOVERY_RANDOM))
        caught = 0
        for position in [i for i, c in enumerate(text) if c != '-']:
            wrong = keys.CROCKFORD[(keys.CROCKFORD.index(text[position]) + 1) % 32]
            try:
                keys.parse_recovery(text[:position] + wrong + text[position + 1:])
            except Fault as exc:
                self.assertEqual(exc.code, 'recovery_key_mistyped'); caught += 1
        # A 16-bit check misses about one changed character in 65,000; all 40 here are caught.
        self.assertEqual(caught, 40)
        with self.assertRaises(Fault):
            keys.parse_recovery(text[:-1])

    def test_missing_library_is_a_clear_refusal(self):
        with mock.patch.dict(sys.modules, {'cryptography.hazmat.primitives.ciphers.aead': None}):
            with self.assertRaises(Fault) as caught:
                keys._lock(bytes(32), b'x', b'')
        self.assertEqual(caught.exception.code, 'encryption_library_missing')


class KeyringTests(Base):
    def test_file_is_private_and_holds_no_key_or_secret(self):
        opened, recovery_key = self.make()
        opened.add_area('personal', 'personal')
        _, area_key = opened.area_key('personal')
        raw = self.raw()
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.path.parent).st_mode), 0o700)
        for secret in (bytes(opened._master), area_key):
            for form in (secret.hex(), base64.b64encode(secret).decode(), keys._b64(secret)):
                self.assertNotIn(form, raw)
        for words in (PASSPHRASE, recovery_key, recovery_key.replace('-', '')):
            self.assertNotIn(words, raw)
        data = json.loads(raw)
        self.assertEqual(sorted(s['method'] for s in data['slots']), ['passphrase', 'recovery'])
        self.assertEqual(keys.Keyring.read(self.path).view()['areas'][0]['id'], 'personal')

    def test_each_method_opens_the_same_master_key(self):
        opened, recovery_key = self.make()
        master = bytes(opened._master)
        keyring = keys.Keyring.read(self.path)
        for method in (keys.Passphrase(PASSPHRASE), keys.RecoveryKey(recovery_key)):
            with keyring.unlock(method) as again:
                self.assertEqual(bytes(again._master), master)

    def test_wrong_passphrase_and_wrong_recovery_key_open_nothing(self):
        self.make()
        keyring = keys.Keyring.read(self.path)
        with self.assertRaises(Fault) as caught:
            keyring.unlock(keys.Passphrase('not the passphrase at all'))
        self.assertEqual(caught.exception.code, 'wrong_key')
        with self.assertRaises(Fault) as caught:
            keyring.unlock(keys.RecoveryKey(keys.recovery_text(os.urandom(keys.RECOVERY_RANDOM))))
        self.assertEqual(caught.exception.code, 'wrong_key')

    def test_production_passphrase_cost_is_recorded(self):
        with mock.patch.dict(keys.SCRYPT, {'n': 2 ** 17, 'r': 8, 'p': 1}):
            self.make()
        slot = keys.Keyring.read(self.path).slots('passphrase')[0]
        self.assertEqual((slot['settings']['n'], slot['settings']['r'], slot['settings']['p']), (2 ** 17, 8, 1))
        with keys.Keyring.read(self.path).unlock(keys.Passphrase(PASSPHRASE)):
            pass

    def test_short_passphrase_and_recovery_as_first_method_are_refused(self):
        for method, code in ((keys.Passphrase('short'), 'passphrase_too_short'),
                             (keys.RecoveryKey(), 'invalid_unlock_method')):
            with self.assertRaises(Fault) as caught:
                keys.Keyring.create(self.path, method)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(self.path.exists())

    def test_never_overwrites_and_rejects_a_symlink(self):
        self.make()
        with self.assertRaises(Fault) as caught:
            keys.Keyring.create(self.path, keys.Passphrase(PASSPHRASE))
        self.assertEqual(caught.exception.code, 'keyring_exists')
        link = self.root / 'link.json'
        link.symlink_to(self.path)
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(link)
        self.assertEqual(caught.exception.code, 'keyring_symlink_rejected')

    def test_tampering_is_detected_on_unlock(self):
        opened, _ = self.make()
        opened.add_area('acme', 'client')
        opened.destroy_area('acme')
        data = json.loads(self.raw())
        data['destroyed'] = []  # hide that an area was destroyed
        self.path.write_text(json.dumps(data))
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(self.path).unlock(keys.Passphrase(PASSPHRASE))
        self.assertEqual(caught.exception.code, 'keyring_tampered')

    def test_damaged_files_are_refused_before_any_use(self):
        self.make()
        good = json.loads(self.raw())
        for change in (lambda d: d.update(extra=1), lambda d: d.update(version=2),
                       lambda d: d['slots'][0].update(master='!!'),
                       lambda d: d.update(slots=[s for s in d['slots'] if s['method'] != 'recovery']),
                       lambda d: d['slots'][0].update(id='../../x')):
            data = json.loads(json.dumps(good)); change(data)
            self.path.write_text(json.dumps(data))
            with self.assertRaises(Fault) as caught:
                keys.Keyring.read(self.path)
            self.assertIn(caught.exception.code, ('keyring_damaged', 'unsupported_keyring_version'))
        self.path.write_text('{not json')
        with self.assertRaises(Fault):
            keys.Keyring.read(self.path)

    def test_a_tampered_passphrase_cost_cannot_exhaust_memory(self):
        self.make()
        data = json.loads(self.raw())
        slot = next(s for s in data['slots'] if s['method'] == 'passphrase')
        slot['settings']['n'] = 2 ** 24
        self.path.write_text(json.dumps(data))
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(self.path).unlock(keys.Passphrase(PASSPHRASE))
        self.assertEqual(caught.exception.code, 'keyring_damaged')

    def test_two_writers_cannot_overwrite_each_other(self):
        first, _ = self.make()
        second = keys.Keyring.read(self.path).unlock(keys.Passphrase(PASSPHRASE)); self.addCleanup(second.close)
        first.add_area('personal', 'personal')
        with self.assertRaises(Fault) as caught:
            second.add_area('company', 'company')
        self.assertEqual(caught.exception.code, 'keyring_changed')
        self.assertEqual([a['id'] for a in keys.Keyring.read(self.path).view()['areas']], ['personal'])

    def test_closing_clears_the_master_key(self):
        opened, _ = self.make()
        buffer = opened._master
        opened.close()
        self.assertEqual(bytes(buffer), bytes(len(buffer)))
        with self.assertRaises(Fault) as caught:
            opened.add_area('personal', 'personal')
        self.assertEqual(caught.exception.code, 'keyring_closed')


class AreaTests(Base):
    def setUp(self):
        super().setUp()
        self.opened, self.recovery_key = self.make()
        for area, kind in (('personal', 'personal'), ('company', 'company'), ('client-acme', 'client')):
            self.opened.add_area(area, kind)

    def test_seal_and_open_bind_area_and_context(self):
        sealed = self.opened.seal('personal', 'Dentist on Tuesday', 'reviewed_values/value/42')
        self.assertTrue(sealed.startswith('alfred-seal:1:personal:1:'))
        self.assertNotIn('Dentist', sealed)
        self.assertEqual(self.opened.open('personal', sealed, 'reviewed_values/value/42'), b'Dentist on Tuesday')
        with self.assertRaises(Fault) as caught:
            self.opened.open('personal', sealed, 'reviewed_values/value/43')
        self.assertEqual(caught.exception.code, 'seal_does_not_match')
        with self.assertRaises(Fault) as caught:
            self.opened.open('company', sealed, 'reviewed_values/value/42')
        self.assertEqual(caught.exception.code, 'sealed_for_another_area')
        relabelled = sealed.replace(':personal:', ':company:')
        with self.assertRaises(Fault) as caught:
            self.opened.open('company', relabelled, 'reviewed_values/value/42')
        self.assertEqual(caught.exception.code, 'seal_does_not_match')

    def test_each_area_has_its_own_key(self):
        found = {self.opened.area_key(a)[1] for a in ('personal', 'company', 'client-acme')}
        self.assertEqual(len(found), 3)

    def test_destroying_an_area_makes_its_values_unreadable_even_with_the_recovery_key(self):
        sealed = self.opened.seal('client-acme', 'Acme contract renewal terms', 'notes/excerpt/1')
        kept = self.opened.seal('personal', 'Still mine', 'notes/excerpt/2')
        older_copy = self.raw()
        result = self.opened.destroy_area('client-acme')
        self.assertEqual(result, {'area': 'client-acme', 'destroyed': True, 'key_versions_deleted': 1})
        with self.assertRaises(Fault) as caught:
            self.opened.open('client-acme', sealed, 'notes/excerpt/1')
        self.assertEqual(caught.exception.code, 'area_destroyed')
        with keys.Keyring.read(self.path).unlock(keys.RecoveryKey(self.recovery_key)) as again:
            with self.assertRaises(Fault) as caught:
                again.open('client-acme', sealed, 'notes/excerpt/1')
            self.assertEqual(caught.exception.code, 'area_destroyed')
            self.assertEqual(again.open('personal', kept, 'notes/excerpt/2'), b'Still mine')
            with self.assertRaises(Fault) as caught:
                again.add_area('client-acme', 'client')
            self.assertEqual(caught.exception.code, 'area_was_destroyed')
        view = keys.Keyring.read(self.path).view()
        self.assertEqual([d['id'] for d in view['destroyed']], ['client-acme'])
        # The honest limit, stated in docs/ENCRYPTION.md: a copy of the keyring taken before
        # the destruction still opens the area, with the recovery key, until that copy is deleted.
        old = self.root / 'older-copy.json'; old.write_text(older_copy)
        with keys.Keyring.read(old).unlock(keys.RecoveryKey(self.recovery_key)) as before:
            self.assertEqual(before.open('client-acme', sealed, 'notes/excerpt/1'), b'Acme contract renewal terms')

    def test_rotation_seals_with_the_new_version_and_still_opens_the_old(self):
        old = self.opened.seal('company', 'Q3 plan', 'c/1')
        self.assertEqual(self.opened.rotate_area('company'), {'area': 'company', 'key_versions': 2})
        new = self.opened.seal('company', 'Q4 plan', 'c/2')
        self.assertTrue(new.startswith('alfred-seal:1:company:2:'))
        self.assertEqual((self.opened.open('company', old, 'c/1'), self.opened.open('company', new, 'c/2')),
                         (b'Q3 plan', b'Q4 plan'))

    def test_area_names_and_kinds_are_checked(self):
        for area, kind, code in (('../x', 'client', 'invalid_identifier'), ('team', 'family', 'invalid_area_kind'),
                                 ('personal', 'personal', 'area_exists')):
            with self.assertRaises(Fault) as caught:
                self.opened.add_area(area, kind)
            self.assertEqual(caught.exception.code, code)

    def test_swapped_area_keys_are_refused(self):
        data = json.loads(self.raw())
        first, second = data['areas'][0], data['areas'][1]
        first['keys'], second['keys'] = second['keys'], first['keys']
        self.path.write_text(json.dumps(data))
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(self.path).unlock(keys.Passphrase(PASSPHRASE))
        self.assertEqual(caught.exception.code, 'keyring_tampered')


class UnlockMethodTests(Base):
    def test_keychain_secret_never_appears_in_arguments_and_is_withdrawn(self):
        security = FakeSecurity()
        opened, _ = self.make(keys.Keychain(security), label='MacBook')
        (service, account), stored = next(iter(security.items.items()))
        self.assertEqual(service, keys.KEYCHAIN_SERVICE)
        self.assertTrue(all(stored not in ' '.join(arguments) for arguments, _ in security.calls))
        self.assertIn(stored, security.calls[0][1], 'the secret went in on standard input')
        self.assertNotIn(stored, self.raw())
        with keys.Keyring.read(self.path).unlock(keys.Keychain(security)) as again:
            self.assertEqual(bytes(again._master), bytes(opened._master))
        slot = keys.Keyring.read(self.path).slots('keychain')[0]['id']
        opened.remove_unlock(slot, method=keys.Keychain(security))
        self.assertEqual(security.items, {})
        self.assertEqual([s['method'] for s in keys.Keyring.read(self.path).slots()], ['recovery'])

    def test_keychain_unavailable_off_a_mac(self):
        if sys.platform == 'darwin':
            self.skipTest('this checks the refusal on other systems')
        with self.assertRaises(Fault) as caught:
            keys.Keyring.create(self.path, keys.Keychain())
        self.assertEqual(caught.exception.code, 'keychain_unavailable')
        self.assertFalse(self.path.exists())

    def test_a_keychain_slot_pointed_at_another_item_is_refused(self):
        security = FakeSecurity()
        self.make(keys.Keychain(security))
        data = json.loads(self.raw())
        slot = next(s for s in data['slots'] if s['method'] == 'keychain')
        slot['settings']['account'] = 'someone-else'
        self.path.write_text(json.dumps(data))
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(self.path).unlock(keys.Keychain(security))
        self.assertEqual(caught.exception.code, 'keyring_damaged')

    def test_server_secret_file_by_path_and_by_systemd_credential(self):
        secrets_dir = self.root / 'run'; secrets_dir.mkdir()
        path = secret_file(secrets_dir, 'alfred-unlock', 0o400)
        opened, _ = self.make(keys.SecretFile(str(path)), label='server')
        master = bytes(opened._master)
        with keys.Keyring.read(self.path).unlock(keys.SecretFile()) as again:
            self.assertEqual(bytes(again._master), master)
        credentials = self.root / 'credentials'; credentials.mkdir()
        secret_file(credentials, 'alfred-master', 0o400)
        opened.add_unlock(keys.SecretFile(credential='alfred-master', environ={'CREDENTIALS_DIRECTORY': str(credentials)}))
        path.unlink()
        with keys.Keyring.read(self.path).unlock(keys.SecretFile(environ={'CREDENTIALS_DIRECTORY': str(credentials)})) as again:
            self.assertEqual(bytes(again._master), master)
        with self.assertRaises(Fault) as caught:
            keys.Keyring.read(self.path).unlock(keys.SecretFile(environ={}))
        self.assertEqual(caught.exception.code, 'unlock_unavailable')

    def test_systemd_credential_enrolled_from_the_plain_copy_before_it_is_deleted(self):
        plain = secret_file(self.root, 'plain-copy', 0o600)
        opened, _ = self.make(keys.SecretFile(str(plain), credential='alfred-unlock'), label='server')
        self.assertEqual(keys.Keyring.read(self.path).slots('secret-file')[0]['settings'], {'credential': 'alfred-unlock'})
        credentials = self.root / 'run-credentials'; credentials.mkdir()
        (credentials / 'alfred-unlock').write_bytes(plain.read_bytes()); os.chmod(credentials / 'alfred-unlock', 0o400)
        plain.unlink()
        with keys.Keyring.read(self.path).unlock(keys.SecretFile(environ={'CREDENTIALS_DIRECTORY': str(credentials)})) as again:
            self.assertEqual(bytes(again._master), bytes(opened._master))

    def test_secret_file_must_be_private_long_enough_and_a_plain_file(self):
        cases = ((secret_file(self.root, 'open', 0o644), 'secret_file_too_open'),
                 (secret_file(self.root, 'short', 0o600, 'too short\n'), 'secret_file_too_short'),
                 (self.root / 'missing', 'unlock_unavailable'))
        for path, code in cases:
            with self.assertRaises(Fault) as caught:
                keys.read_secret_file(path)
            self.assertEqual(caught.exception.code, code, path.name)
        fifo = self.root / 'fifo'; os.mkfifo(fifo, 0o600)
        with self.assertRaises(Fault) as caught:
            keys.read_secret_file(fifo)
        self.assertEqual(caught.exception.code, 'secret_file_not_regular')

    def test_kubernetes_style_symlinked_secret_is_followed_to_a_private_file(self):
        data = self.root / '..data'; data.mkdir()
        target = secret_file(data, 'alfred', 0o400)
        link = self.root / 'alfred'; link.symlink_to(target)
        self.assertEqual(keys.read_secret_file(link), target.read_bytes().strip())

    def test_recovery_key_cannot_be_removed_and_is_replaced_whole(self):
        opened, old = self.make()
        recovery_slot = keys.Keyring.read(self.path).slots('recovery')[0]['id']
        with self.assertRaises(Fault) as caught:
            opened.remove_unlock(recovery_slot)
        self.assertEqual(caught.exception.code, 'recovery_key_required')
        new = opened.new_recovery()
        self.assertNotEqual(new, old)
        keyring = keys.Keyring.read(self.path)
        self.assertEqual(len(keyring.slots('recovery')), 1)
        with self.assertRaises(Fault):
            keyring.unlock(keys.RecoveryKey(old))
        with keyring.unlock(keys.RecoveryKey(new)):
            pass
        with self.assertRaises(Fault) as caught:
            opened.add_unlock(keys.RecoveryKey())
        self.assertEqual(caught.exception.code, 'use_new_recovery')

    def test_automatic_unlock_order_and_the_recovery_key_is_never_tried_unasked(self):
        security = FakeSecurity()
        opened, _ = self.make(keys.Passphrase(PASSPHRASE))
        opened.add_unlock(keys.Keychain(security))
        path = secret_file(self.root, 'server', 0o600)
        opened.add_unlock(keys.SecretFile(str(path)))
        keyring = keys.Keyring.read(self.path)
        again, how = keys.unlock(keyring, run=security)
        again.close()
        self.assertEqual(how, 'secret-file')
        path.unlink()
        again, how = keys.unlock(keyring, run=security)
        again.close()
        self.assertEqual(how, 'keychain')
        security.items.clear()
        asked = []
        again, how = keys.unlock(keyring, run=security, prompt=lambda label: asked.append(label) or PASSPHRASE)
        again.close()
        self.assertEqual((how, len(asked)), ('passphrase', 1))
        with self.assertRaises(Fault) as caught:
            keys.unlock(keyring, run=security, prompt=lambda label: 'wrong passphrase, three times', attempts=3)
        self.assertEqual(caught.exception.code, 'no_unlock_available')
        self.assertEqual(len(caught.exception.reasons), 5)

    def test_another_method_can_be_registered(self):
        class Vault(keys.UnlockMethod):
            name, title = 'test-vault', 'test vault'
            store = {}

            def enrol(self, keyring_id, slot_id):
                self.store[slot_id] = os.urandom(32)
                return {'key': slot_id}, self.store[slot_id]

            def secret(self, keyring_id, slot_id, settings):
                return self.store[settings['key']]

        keys.register(Vault)
        self.addCleanup(keys.METHODS.pop, 'test-vault')
        with self.assertRaises(Fault):
            keys.register(Vault)
        opened, _ = self.make()
        opened.add_unlock(Vault())
        with keys.Keyring.read(self.path).unlock(Vault()) as again:
            self.assertEqual(bytes(again._master), bytes(opened._master))
        keys.METHODS.pop('test-vault')
        self.assertIn('does not know', keys.Keyring.read(self.path).view()['unlock'][-1]['where'])
        keys.METHODS['test-vault'] = Vault


class RecoveryKitTests(Base):
    def test_backup_opens_only_with_the_recovery_key_and_restores_elsewhere(self):
        security = FakeSecurity()
        opened, recovery_key = self.make(keys.Keychain(security))
        opened.add_area('personal', 'personal')
        sealed = opened.seal('personal', 'kept across machines', 'x/1')
        kit = self.root / 'kit'; kit.mkdir()
        copy = opened.backup(kit)
        self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o600)
        self.assertEqual([s['method'] for s in keys.Keyring.read(copy).slots()], ['recovery'])
        with self.assertRaises(Fault):
            keys.Keyring.read(copy).unlock(keys.Keychain(security))
        # A new machine: the recovery key puts the copy in place, then a local method is added.
        elsewhere = self.root / 'server' / keys.KEYRING_FILE
        with keys.restore(copy, elsewhere, keys.RecoveryKey(recovery_key)) as restored:
            self.assertEqual(restored.open('personal', sealed, 'x/1'), b'kept across machines')
            restored.add_unlock(keys.Passphrase(PASSPHRASE), 'server')
        with keys.Keyring.read(elsewhere).unlock(keys.Passphrase(PASSPHRASE)) as there:
            self.assertEqual(there.open('personal', sealed, 'x/1'), b'kept across machines')
        with self.assertRaises(Fault) as caught:
            keys.restore(copy, elsewhere, keys.RecoveryKey(recovery_key))
        self.assertEqual(caught.exception.code, 'keyring_exists')


class DiskEncryptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sys = Path(self.tmp.name) / 'sys'

    def block(self, name, uuid=None, slaves=()):
        node = self.sys / 'devices' / 'virtual' / 'block' / name
        (node / 'slaves').mkdir(parents=True, exist_ok=True)
        if uuid:
            (node / 'dm').mkdir(exist_ok=True)
            (node / 'dm' / 'uuid').write_text(uuid + '\n')
            (node / 'dm' / 'name').write_text(name.replace('dm-', 'vg-') + '\n')
        for slave in slaves:
            (node / 'slaves' / slave).symlink_to(self.sys / 'devices' / 'virtual' / 'block' / slave)
        return node

    def register(self, number, node):
        (self.sys / 'dev' / 'block').mkdir(parents=True, exist_ok=True)
        (self.sys / 'dev' / 'block' / number).symlink_to(node)

    def test_linux_luks_under_lvm_is_found(self):
        self.block('nvme0n1p3')
        self.block('dm-0', 'CRYPT-LUKS2-0123-luks', ('nvme0n1p3',))
        self.register('253:1', self.block('dm-1', 'LVM-abc', ('dm-0',)))
        result = keys.disk_encryption('/data', system='linux', sysfs=str(self.sys), device=(253, 1))
        self.assertEqual(result['status'], 'on')
        self.assertIn('vg-0', result['detail'])

    def test_linux_plain_disk_virtual_filesystem_and_missing_device(self):
        self.register('259:2', self.block('nvme0n1p2'))
        self.assertEqual(keys.disk_encryption('/d', system='linux', sysfs=str(self.sys), device=(259, 2))['status'], 'not_detected')
        self.assertEqual(keys.disk_encryption('/d', system='linux', sysfs=str(self.sys), device=(0, 41))['status'], 'unknown')
        self.assertEqual(keys.disk_encryption('/d', system='linux', sysfs=str(self.sys), device=(8, 9))['status'], 'unknown')

    def test_macos_filevault(self):
        for output, status in (('FileVault is On.\n', 'on'), ('FileVault is Off.\n', 'off'), ('?', 'unknown')):
            self.assertEqual(keys.disk_encryption('/Users/x', system='darwin', run=lambda a, o=output: o)['status'], status)

        def failing(arguments):
            raise Fault('command_failed')
        self.assertEqual(keys.disk_encryption('/Users/x', system='darwin', run=failing)['status'], 'unknown')

    def test_other_systems_are_unknown(self):
        self.assertEqual(keys.disk_encryption('C:/x', system='win32')['status'], 'unknown')


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; init_demo(self.home)

    def test_doctor_reports_disk_encryption_and_reads_the_keyring_without_opening_it(self):
        with mock.patch.dict(keys.SCRYPT, FAST):
            opened, _ = keys.Keyring.create(self.home / keys.KEYRING_FILE, keys.Passphrase(PASSPHRASE))
        opened.add_area('personal', 'personal'); opened.close()
        with mock.patch.object(keys, 'disk_encryption', return_value={'status': 'on', 'detail': 'FileVault is on.'}):
            results = {r['check']: r for r in recovery.doctor(self.home)}
        self.assertEqual(results['disk_encryption']['status'], 'ok')
        self.assertEqual(results['keyring']['status'], 'ok')
        self.assertIn('1 area', results['keyring']['detail'])
        os.chmod(self.home / keys.KEYRING_FILE, 0o644)
        with mock.patch.object(keys, 'disk_encryption', return_value={'status': 'off', 'detail': 'FileVault is off.'}):
            results = {r['check']: r for r in recovery.doctor(self.home)}
        self.assertEqual(results['disk_encryption']['status'], 'warn')
        self.assertEqual(results['permissions']['status'], 'fail')
        self.assertIn(keys.KEYRING_FILE, results['permissions']['detail'])
        (self.home / keys.KEYRING_FILE).write_text('{}')
        self.assertEqual({r['check']: r for r in recovery.doctor(self.home)}['keyring']['status'], 'fail')


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.data = self.root / 'data'

    def run_keys(self, *arguments, stdin=''):
        return subprocess.run([sys.executable, '-m', 'alfred.keys', '--data-dir', str(self.data), *arguments],
                              cwd=REPOSITORY, input=stdin, capture_output=True, text=True, timeout=120)

    def test_server_style_setup_from_the_command_line(self):
        secret = self.root / 'alfred-secret'
        made = self.run_keys('server-secret', '--output', str(secret))
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(secret).st_mode), 0o600)
        self.assertEqual(self.run_keys('server-secret', '--output', str(secret)).returncode, 1, 'never overwrites')
        init = self.run_keys('init', '--unlock', 'secret-file', '--secret-file', str(secret), '--label', 'server')
        self.assertEqual(init.returncode, 0, init.stderr)
        key = next(line.strip() for line in init.stdout.splitlines() if line.startswith('    '))
        self.assertEqual(len(keys.parse_recovery(key)), keys.RECOVERY_RANDOM)
        self.assertIn('Disk encryption:', init.stdout)
        for arguments in (('area-add', 'personal', '--kind', 'personal'), ('area-add', 'acme', '--kind', 'client'),
                          ('check',), ('area-destroy', 'acme', '--confirm', 'acme')):
            done = self.run_keys(*arguments)
            self.assertEqual(done.returncode, 0, done.stderr)
        refused = self.run_keys('area-destroy', 'personal', '--confirm', 'persona')
        self.assertEqual(refused.returncode, 1)
        self.assertIn('confirmation_mismatch', refused.stderr)
        status = self.run_keys('status', '--json')
        self.assertEqual(status.returncode, 0, status.stderr)
        view = json.loads(status.stdout)
        self.assertEqual(([a['id'] for a in view['areas']], [d['id'] for d in view['destroyed']]), (['personal'], ['acme']))
        self.assertNotIn(secret.read_text().strip(), status.stdout)
        self.assertNotIn(key, (self.data / keys.KEYRING_FILE).read_text())
        # Recovery from standard input, as a server operator would pipe it.
        kit = self.root / 'kit'; kit.mkdir()
        backup = self.run_keys('backup', '--to', str(kit), '--with', 'recovery', stdin=key + '\n')
        self.assertEqual(backup.returncode, 0, backup.stderr)
        wrong = self.run_keys('check', '--with', 'recovery', stdin='0' * 40 + '\n')
        self.assertEqual(wrong.returncode, 1)
        self.assertIn('recovery_key_mistyped', wrong.stderr)

    def test_missing_keyring_and_unavailable_methods_are_explained(self):
        missing = self.run_keys('status')
        self.assertEqual(missing.returncode, 1)
        self.assertIn('keyring_not_found', missing.stderr)
        self.assertIn('init --unlock keychain', missing.stderr)


if __name__ == '__main__':
    unittest.main()
