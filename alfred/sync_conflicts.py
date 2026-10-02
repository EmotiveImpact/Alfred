"""Recognise file-sync conflict copies by their documented names (MEM-014).

When a sync tool cannot reconcile edits made on two devices it keeps both: one
under the original name and one under a conflict name. The copy is neither an
independent note nor a newer revision, and nothing here decides which version is
right. The vault scanner records each copy as a sync conflict linked to its
original, keeps it out of the index, retrieval and grounding, and reports it
until the person resolves it in their own editor. Contents are never compared,
merged or rewritten.

Only these exact forms, immediately before the `.md` extension, are recognised:

  Syncthing               name.sync-conflict-YYYYMMDD-HHMMSS-XXXXXXX.md
                          (XXXXXXX: the first seven characters, A-Z or 2-7, of the
                          ID of the device that last edited it; may be empty)
  Dropbox                 name (Someone's conflicted copy YYYY-MM-DD).md
                          name (Someone's conflicted copy YYYY-MM-DD (2)).md
  Nextcloud and ownCloud  name (conflicted copy YYYY-MM-DD hhmmss).md
                          name (conflicted copy username YYYY-MM-DD hhmmss).md
  older ownCloud clients  name_conflict-YYYYMMDD-HHMMSS.md

The date and time must be a real calendar date and clock time. A conflict copy
of a conflict copy is traced back to the first original. OneDrive, iCloud Drive,
Google Drive, Obsidian Sync and Git conflicts are deliberately not recognised by
name; docs/SYNC.md explains why.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import posixpath
import re
from .local import Fault

MAX_CONFLICTS = 64
_EXTENSION = r'(?P<ext>\.[Mm][Dd])'
PATTERNS = (
    ('syncthing', re.compile(r'(?P<base>.+)\.sync-conflict-(?P<date>[0-9]{8})-(?P<time>[0-9]{6})-(?:[A-Z2-7]{7})?' + _EXTENSION)),
    ('dropbox', re.compile(r"(?P<base>.+) \([^()/]+?['\u2019]s conflicted copy (?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})(?: \([1-9][0-9]{0,3}\))?\)" + _EXTENSION)),
    ('nextcloud_owncloud', re.compile(r'(?P<base>.+) \(conflicted copy (?:[^()/]+ )?(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}) (?P<time>[0-9]{6})\)' + _EXTENSION)),
    ('owncloud_legacy', re.compile(r'(?P<base>.+)_conflict-(?P<date>[0-9]{8})-(?P<time>[0-9]{6})' + _EXTENSION)),
)


def _real_time(match):
    """Fixed-width digits, read by position: a real calendar date and clock time."""
    digits = (match['date'] + (match.groupdict().get('time') or '000000')).replace('-', '')
    try:
        datetime(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]), int(digits[8:10]), int(digits[10:12]), int(digits[12:14]))
    except ValueError:
        return False
    return True


def _outermost(name):
    for tool, pattern in PATTERNS:
        match = pattern.fullmatch(name)
        if match and match['base'].strip() and _real_time(match):
            return tool, match['base'] + match['ext']
    return None


def conflict_copy(path):
    """Describe a conflict copy, or return None for any other name.

    `path` is a vault-relative POSIX path. The result names the tool whose
    marker is outermost, the path of the first original in the same folder, and
    how many conflict markers were removed to reach it.
    """
    if not isinstance(path, str):
        return None
    folder, name = posixpath.split(path)
    tool, markers = None, 0
    while markers < 8:
        found = _outermost(name)
        if not found:
            break
        tool = tool or found[0]
        name = found[1]
        markers += 1
    if not markers:
        return None
    return {'tool': tool, 'original_path': posixpath.join(folder, name) if folder else name, 'markers': markers}


def conflict_id(source, path):
    """Stable reference for audit entries, so the audit log never holds note paths."""
    return hashlib.sha256((source + '\0' + path).encode()).hexdigest()[:24]


def scanned(copies, notes, errors):
    """After a complete walk: note whether each original exists and bound what is kept.

    An original that exists but could not be indexed (unreadable, excluded link or
    parse failure) appears in `errors` with its path.
    """
    present = {n['path'] for n in notes} | {e['path'] for e in errors if e.get('path')}
    # Stored and displayed errors are bounded, so other problems stay ahead of the
    # per-copy entries, and a capacity problem comes first.
    errors.sort(key=lambda e: e.get('code') == 'sync_conflict_copy')
    if len(copies) > MAX_CONFLICTS:
        errors.insert(0, {'code': 'sync_conflict_capacity'})
    return [{**c, 'original_present': c['original_path'] in present} for c in copies[:MAX_CONFLICTS]]


def checked(conflicts, note_paths):
    """Validate what a scanner reports before it is stored next to the notes."""
    if not isinstance(conflicts, (list, tuple)) or len(conflicts) > MAX_CONFLICTS:
        raise Fault('knowledge_capacity')
    from .knowledge import safe_path
    result, seen = [], set()
    for item in conflicts:
        if type(item) is not dict or set(item) != {'path', 'original_path', 'tool', 'markers', 'original_present'}:
            raise Fault('invalid_sync_conflict')
        path = safe_path(item['path'])
        expected = conflict_copy(path)
        if (not expected or {k: item[k] for k in expected} != expected
                or type(item['original_present']) is not bool):
            raise Fault('invalid_sync_conflict')
        if path.casefold() in note_paths or path.casefold() in seen:
            raise Fault('duplicate_note_path')
        seen.add(path.casefold())
        result.append({**expected, 'path': path, 'original_present': item['original_present']})
    return result


def record(store, db, scope, source, conflicts, located):
    """Replace one source's recorded conflicts inside the scan's own transaction.

    `located` maps note paths indexed in that transaction to their catalogue IDs.
    A copy stays recorded until a complete scan no longer finds it.
    """
    prior = {r['path']: dict(r) for r in db.execute('SELECT * FROM knowledge_conflicts WHERE scope=? AND source=?', (scope, source))}
    db.execute('DELETE FROM knowledge_conflicts WHERE scope=? AND source=?', (scope, source))
    for c in conflicts:
        original = located.get(c['original_path'])
        state = 'linked' if original else 'original_unavailable' if c['original_present'] else 'orphaned'
        first = prior[c['path']]['detected'] if c['path'] in prior else store.now()
        db.execute('INSERT INTO knowledge_conflicts VALUES (?,?,?,?,?,?,?,?,?)',
                   (scope, source, c['path'], c['original_path'], original, c['tool'], state, first, store.now()))
        if c['path'] not in prior:
            store.log(db, scope, source, 'knowledge.sync_conflict_detected', conflict_id(source, c['path']))
    for path in sorted(set(prior) - {c['path'] for c in conflicts}):
        store.log(db, scope, source, 'knowledge.sync_conflict_cleared', conflict_id(source, path))


def view(rows, visible_notes):
    """Conflicts for sources the caller may read, linked only to notes it can see."""
    return [{'source': r['source'], 'path': r['path'], 'original_path': r['original_path'],
             'original': r['original_id'] if r['original_id'] in visible_notes else None,
             'state': r['state'], 'tool': r['tool'], 'detected': r['detected'], 'checked': r['checked'],
             'basis': 'sync_conflict_copy_not_indexed'} for r in rows]
