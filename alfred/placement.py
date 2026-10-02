"""Where ALFRED's live files may be kept (MEM-014).

The live SQLite database, its write-ahead log and shared-memory index, the
lifecycle journal, the access keys, the host lock and the job cache must stay on
a local disk that no file-sync tool watches, outside every vault. Sync tools copy
files one at a time while they change, which can tear a live database or pair it
with the wrong write-ahead log on another device; SQLite documents that WAL does
not work over a network filesystem. `init`, `serve` and `restore` refuse such a
placement and there is deliberately no override. The consistent alternative is
`backup`: its snapshot is safe to copy into a synced folder. `export` writes a
readable, filtered record that is also safe to sync.

Detected by looking in the data directory and in every ancestor:

  Syncthing               .stfolder, .stignore or .stversions
  Dropbox                 .dropbox or .dropbox.cache
  Nextcloud and ownCloud  .owncloudsync.log, .csync_journal.db, .sync_<hex>.db, ._sync_<hex>.db
  Git                     .git (anything in a working tree can be committed and pushed)
  An Obsidian vault       .obsidian
  macOS paths             Library/Mobile Documents (iCloud Drive) and
                          Library/CloudStorage/<provider> (OneDrive, Dropbox, Google Drive, Box)

Both the path as given and its resolved real path are checked. What cannot be
detected this way is listed in docs/SYNC.md.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
from .local import Fault

IN_SYNC_FOLDER = 'data_directory_in_sync_folder'
IN_GIT_WORKING_TREE = 'data_directory_in_git_working_tree'
INSIDE_VAULT = 'data_directory_inside_vault'
SYNCED = 'File sync copies these files one at a time while ALFRED writes them, which can tear a live SQLite database or pair it with the wrong write-ahead log on another device.'
MARKERS = (
    ('.stfolder', IN_SYNC_FOLDER, 'a Syncthing folder', SYNCED),
    ('.stignore', IN_SYNC_FOLDER, 'a Syncthing folder', SYNCED),
    ('.stversions', IN_SYNC_FOLDER, 'a Syncthing folder', SYNCED),
    ('.dropbox', IN_SYNC_FOLDER, 'a Dropbox folder', SYNCED),
    ('.dropbox.cache', IN_SYNC_FOLDER, 'a Dropbox folder', SYNCED),
    ('.owncloudsync.log', IN_SYNC_FOLDER, 'a Nextcloud or ownCloud folder', SYNCED),
    ('.csync_journal.db', IN_SYNC_FOLDER, 'a Nextcloud or ownCloud folder', SYNCED),
    ('.git', IN_GIT_WORKING_TREE, 'a Git working tree',
     'Anything in a working tree can be committed and pushed, including a torn copy of the live database and private data.'),
    ('.obsidian', INSIDE_VAULT, 'an Obsidian vault',
     'A vault holds your own Markdown notes and is often synced; ALFRED only reads it.'),
)
CLIENT_JOURNAL = re.compile(r'\._?sync_[0-9a-f]+\.db')
ALTERNATIVE = ('Keep --data-dir on a local disk that no sync tool watches, outside every vault. '
               'There is no override. To keep a copy in a synced folder, run "python3 -m alfred.desk backup" '
               'and copy the backup file and its manifest: a backup is a consistent snapshot that is safe to sync, '
               'but it is not encrypted, so the sync service can read it. '
               '"python3 -m alfred.desk export --export-dir PATH" writes a readable, filtered record that is also safe to sync.')


class PlacementFault(Fault):
    """A refusal with a plain-language explanation for the command line."""

    def __init__(self, code, detail):
        super().__init__(code, 409)
        self.detail = detail


def artefacts(data_dir):
    """Every live file ALFRED keeps for one data directory, with a readable label."""
    from .lifecycle import JOURNAL_SUFFIX
    data_dir = Path(data_dir)
    return [('database', data_dir / 'desk.sqlite'), ('write-ahead log', data_dir / 'desk.sqlite-wal'),
            ('shared-memory index', data_dir / 'desk.sqlite-shm'),
            ('lifecycle journal', data_dir / ('desk.sqlite' + JOURNAL_SUFFIX)),
            ('access keys', data_dir / 'desk-access.json'), ('host lock', data_dir / 'desk.lock'),
            ('job cache', data_dir / 'job-cache')]


def _views(path):
    """The path as given, normalised, and its real location after symlinks."""
    given = Path(os.path.normpath(Path(path).expanduser().absolute()))
    try:
        real = given.resolve()
    except (OSError, RuntimeError):
        # A symlink loop cannot hold live files; the path as given is still checked.
        return [given]
    return [given] if real == given else [given, real]


def _marker(directory):
    for name, code, kind, reason in MARKERS:
        try:
            os.lstat(directory / name)
        except OSError:
            continue
        return {'code': code, 'kind': kind, 'evidence': f'its {name} entry', 'reason': reason}
    try:
        names = os.listdir(directory)
    except OSError:
        names = []
    journal = sorted(n for n in names if CLIENT_JOURNAL.fullmatch(n))
    if journal:
        return {'code': IN_SYNC_FOLDER, 'kind': 'a Nextcloud or ownCloud folder', 'evidence': f'its {journal[0]} entry', 'reason': SYNCED}
    parts = directory.parts
    if parts[-2:] == ('Library', 'Mobile Documents'):
        return {'code': IN_SYNC_FOLDER, 'kind': 'iCloud Drive', 'evidence': 'its macOS path, Library/Mobile Documents', 'reason': SYNCED}
    if len(parts) >= 3 and parts[-3:-1] == ('Library', 'CloudStorage'):
        return {'code': IN_SYNC_FOLDER, 'kind': 'a macOS cloud storage folder', 'evidence': 'its macOS path, Library/CloudStorage', 'reason': SYNCED}
    return None


def locate(path):
    """The nearest synced folder, Git working tree or vault that holds `path`, if any."""
    for view in _views(path):
        for directory in (view, *view.parents):
            found = _marker(directory)
            if found:
                return {**found, 'root': str(directory)}
    return None


def contains(root, path):
    """True when `path` is `root` or lies beneath it, as given or after symlinks."""
    return any(view == base or base in view.parents for view in _views(path) for base in _views(root))


def check_data_directory(data_dir, vaults=()):
    """Refuse a data directory whose live files a sync tool, Git or a vault could hold."""
    data_dir = Path(os.path.normpath(Path(data_dir).expanduser().absolute()))
    files = artefacts(data_dir)
    labels = ', '.join(label for label, _ in files[:-1]) + ' and ' + files[-1][0]
    for vault in vaults:
        if vault is not None and contains(vault, data_dir):
            raise PlacementFault(INSIDE_VAULT, (
                f'ALFRED keeps its {labels} in {data_dir}, which is inside the vault {Path(vault).expanduser().absolute()}. '
                'A vault holds your own Markdown notes and is often synced; ALFRED only reads it. ' + ALTERNATIVE))
    # Each artefact is checked on its own, so a sync root inside the data directory is caught too.
    for location in sorted({path for _, path in files} | {data_dir}):
        found = locate(location)
        if found:
            raise PlacementFault(found['code'], (
                f"ALFRED keeps its {labels} in {data_dir}, and {found['root']} is {found['kind']} "
                f"(recognised by {found['evidence']}). {found['reason']} "
                'ALFRED will not keep live files there. ' + ALTERNATIVE))
    return {'data_dir': str(data_dir), 'artefacts': [label for label, _ in files], 'refused': False}
