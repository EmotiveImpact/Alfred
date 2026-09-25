import io
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
import unittest
from tools.import_sources import blob_sha, safe_path, select, extract


class ImportTests(unittest.TestCase):
    def test_known_git_blob_digest(self):
        self.assertEqual(blob_sha(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')
    def test_safe_relative_path(self):
        self.assertEqual(str(safe_path('root/a/b.py')), 'a/b.py')
    def test_unsafe_paths(self):
        for p in ('/root/x', 'root/../x', 'root/.git/config', 'root/a\\b', 'single', 'root/x\0'):
            with self.subTest(path=p), self.assertRaises(ValueError): safe_path(p)
    def test_actual_environment_excluded(self):
        for p in ('.env', '.env.production', 'secret.pem', 'user.db'):
            with self.subTest(path=p): self.assertFalse(select(PurePosixPath(p)))
    def test_template_environment_allowed(self):
        self.assertTrue(select(PurePosixPath('.env.example')))
    def test_legal_notices_preserved(self):
        self.assertTrue(select(PurePosixPath('nested/COPYING')))
        self.assertTrue(select(PurePosixPath('THIRD_PARTY_NOTICES.md')))
    def test_binary_assets_excluded(self):
        for p in ('model.bin', 'logo.png', 'voice.wav'):
            with self.subTest(path=p): self.assertFalse(select(PurePosixPath(p)))
    def test_build_outputs_excluded(self):
        self.assertFalse(select(PurePosixPath('node_modules/pkg/main.js')))
    def archive(self, licence=b'test licence', duplicate=False, symlink=False):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as tar:
            for name, data in [('root/LICENSE', licence), ('root/main.py', b'raise RuntimeError("MUST NOT RUN")')]:
                info = tarfile.TarInfo(name); info.size = len(data); tar.addfile(info, io.BytesIO(data))
            if duplicate:
                info = tarfile.TarInfo('root/main.py'); tar.addfile(info, io.BytesIO(b''))
            if symlink:
                info = tarfile.TarInfo('root/link.py'); info.type = tarfile.SYMTYPE; info.linkname = '/etc/passwd'; tar.addfile(info)
        return output.getvalue()
    def source(self):
        return {'repository':'test/repo', 'commit':'a'*40, 'licence':'test-fixture-only', 'licence_path':'LICENSE', 'licence_blob_sha1':blob_sha(b'test licence')}
    def test_copies_exact_bytes_without_execution(self):
        with tempfile.TemporaryDirectory() as d:
            result = extract(self.archive(), Path(d), self.source())
            self.assertEqual(result['file_count'], 2)
            self.assertEqual((Path(d)/'main.py').read_bytes(), b'raise RuntimeError("MUST NOT RUN")')
            self.assertFalse(result['runtime_enabled'])
    def test_licence_change_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            extract(self.archive(licence=b'changed'), Path(d), self.source())
    def test_duplicate_archive_path_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            extract(self.archive(duplicate=True), Path(d), self.source())
    def test_symlink_never_followed(self):
        with tempfile.TemporaryDirectory() as d:
            result = extract(self.archive(symlink=True), Path(d), self.source())
            self.assertFalse((Path(d)/'link.py').exists())
            self.assertEqual(len(result['excluded']), 1)


if __name__ == '__main__': unittest.main()
