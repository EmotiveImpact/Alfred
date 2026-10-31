"""Run the whole test suite with every workspace sealed (encryption step 2).

    python tests/sealed_suite.py            # every test module
    python tests/sealed_suite.py test_knowledge.py

Every database a test opens is sealed with one keyring made here from synthetic keys, so
each read and write goes through alfred.sealing. A test that passes both here and in the
ordinary run shows that its code opens what it reads and seals what it writes. The
ordinary run (``python -m unittest discover -s tests``) stays plain.

Tests that start ALFRED in a child process (the host, the command line) need the same
keyring there. The harness names it in ``ALFRED_SEALED_SUITE`` and puts a small
``sitecustomize`` on ``PYTHONPATH``, so each child Python installs it before running.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]

from alfred import keys, sealing  # noqa: E402


class SyntheticUnlock(keys.UnlockMethod):
    """A fixed, synthetic secret: test keys only, never a real workspace."""
    name = 'synthetic-test'
    title = 'synthetic test key'

    def enrol(self, keyring_id, slot_id):
        return {}, bytes(range(32))

    def secret(self, keyring_id, slot_id, settings):
        return bytes(range(32))


ENVIRONMENT = 'ALFRED_SEALED_SUITE'
CHILD_HOOK = f"""import os, sys
if os.environ.get({ENVIRONMENT!r}):
    sys.path[:0] = [{str(HERE.parent)!r}, {str(HERE)!r}]
    import sealed_suite
    sealed_suite.install()
"""


def install() -> sealing.Sealed:
    """Seal every database from here on with one synthetic keyring, made here or, in a child
    process, the one its parent named."""
    named = os.environ.get(ENVIRONMENT)
    if named:
        opened = keys.Keyring.read(named).unlock(SyntheticUnlock())
    else:
        holding = Path(tempfile.mkdtemp(prefix='alfred-sealed-suite-'))
        opened, _ = keys.Keyring.create(holding / keys.KEYRING_FILE, SyntheticUnlock())
        opened.add_area(sealing.DEFAULT_AREA, 'personal')
        (holding / 'sitecustomize.py').write_text(CHILD_HOOK, encoding='utf-8')
        os.environ[ENVIRONMENT] = str(holding / keys.KEYRING_FILE)
        os.environ['PYTHONPATH'] = os.pathsep.join(filter(None, (str(holding), os.environ.get('PYTHONPATH'))))
    sealer = sealing.Sealed(opened)
    real_seal = opened.seal

    def seal(area, plaintext, where):
        sealer.sealed_count += 1
        return real_seal(area, plaintext, where)
    # Counted, so the run can show that sealing took effect rather than passing plain.
    sealer.sealed_count, opened.seal = 0, seal

    def for_path(path):
        # A test that attaches its own sealer (plain included) keeps it.
        return sealing._attached.get(sealing._key(path), sealer)

    sealing.for_path = for_path
    return sealer


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sealer = install()
    from alfred.knowledge import KnowledgeStore
    with tempfile.TemporaryDirectory() as directory:
        # A store made the ordinary way must come out sealed, or the run below would be plain.
        if KnowledgeStore(Path(directory) / 'db.sqlite').sealer is not sealer:
            print('sealed suite: stores are not sealed; nothing below would test sealing', file=sys.stderr)
            return 1
    pattern = argv[0] if argv else 'test*.py'
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern=pattern, top_level_dir=str(HERE))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(f'sealed suite: {sealer.sealed_count} values sealed in this process', file=sys.stderr)
    if not argv and not sealer.sealed_count:
        # The whole suite indexes notes, so a full run that sealed nothing tested nothing sealed.
        print('sealed suite: no value was sealed, so the run tested nothing sealed', file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
