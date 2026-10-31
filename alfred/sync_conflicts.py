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

A copy from a tool not recognised by name is detected by content instead
(`content_copies`): a note with exactly the same bytes as another note in the same
folder, whose name is the other note's name plus a short suffix (`Atlas 2.md`,
`Atlas (1).md`, `Atlas-laptop.md`). It is recorded the same way, with the tool
`unrecognised_same_content`. Empty notes are never matched this way.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import posixpath
import re
from .local import Fault

MAX_CONFLICTS = 64
CONTENT_TOOL = 'unrecognised_same_content'
_COPY_SUFFIX = re.compile(r'[ ._~(-].{0,63}')
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


def _stem(path):
    name = posixpath.basename(path)
    return name[:-3] if name.lower().endswith('.md') else name


def _copy_of(copy, original):
    """True when `copy` is `original`'s name plus a short suffix, in the same folder."""
    if copy == original or posixpath.dirname(copy) != posixpath.dirname(original):
        return False
    stem, base = _stem(copy), _stem(original)
    return (len(stem) > len(base) and stem[:len(base)].casefold() == base.casefold()
            and bool(_COPY_SUFFIX.fullmatch(stem[len(base):])))


def content_copies(notes):
    """Conflict copies from tools not recognised by name, found by identical content.

    `notes` are parsed notes with `path`, `sha256` and `body`. Returns one entry per
    copy naming the note it duplicates. Identical content alone is not enough:
    the name must also extend the original's name, so two unrelated notes that
    happen to match are left alone. Nothing is compared beyond the hash.
    """
    groups = {}
    for n in notes:
        if n['body'].strip() and not conflict_copy(n['path']):
            groups.setdefault((posixpath.dirname(n['path']), n['sha256']), []).append(n['path'])
    found = []
    for (_, digest), paths in sorted(groups.items()):
        if len(paths) < 2:
            continue
        for path in sorted(paths):
            originals = sorted((o for o in paths if _copy_of(path, o)), key=lambda o: (len(_stem(o)), o))
            if originals:
                found.append({'path': path, 'original_path': originals[0], 'tool': CONTENT_TOOL, 'markers': 0, 'sha256': digest})
    return found


def conflict_id(source, path, sealer=None, area=None):
    """Stable reference for audit entries, so the audit log never holds note paths.

    In a sealed workspace it is keyed, so a guessed path cannot be checked against it.
    """
    digest = hashlib.sha256((source + '\0' + path).encode()).hexdigest()
    return (sealer.fingerprint(area, digest) if sealer is not None else digest)[:24]


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


def checked(conflicts, note_paths, hashes=None):
    """Validate what a scanner reports before it is stored next to the notes.

    `hashes` maps casefolded indexed note paths to their SHA-256; a copy detected by
    content must match its original's hash exactly.
    """
    if not isinstance(conflicts, (list, tuple)) or len(conflicts) > MAX_CONFLICTS:
        raise Fault('knowledge_capacity')
    from .knowledge import safe_path
    result, seen = [], set()
    for item in conflicts:
        keys = {'path', 'original_path', 'tool', 'markers', 'original_present'}
        if type(item) is dict and item.get('tool') == CONTENT_TOOL and set(item) == keys | {'sha256'}:
            path, original = safe_path(item['path']), safe_path(item['original_path'])
            if (conflict_copy(path) or item['markers'] != 0 or item['original_present'] is not True
                    or not _copy_of(path, original) or (hashes or {}).get(original.casefold()) != item['sha256']):
                raise Fault('invalid_sync_conflict')
            if path.casefold() in note_paths or path.casefold() in seen:
                raise Fault('duplicate_note_path')
            seen.add(path.casefold())
            result.append({'path': path, 'original_path': original, 'tool': CONTENT_TOOL, 'markers': 0, 'original_present': True})
            continue
        if type(item) is not dict or set(item) != keys:
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
    # Raw rows are kept beside the opened ones, so an unchanged conflict keeps its sealed paths.
    prior = {}
    for raw in db.execute('SELECT * FROM knowledge_conflicts WHERE scope=? AND source=?', (scope, source)):
        opened = store.opened('knowledge_conflicts', raw)
        prior[opened['path']] = (opened, dict(raw))
    db.execute('DELETE FROM knowledge_conflicts WHERE scope=? AND source=?', (scope, source))
    for c in conflicts:
        original = located.get(c['original_path'])
        state = 'linked' if original else 'original_unavailable' if c['original_present'] else 'orphaned'
        first = prior[c['path']][0]['detected'] if c['path'] in prior else store.now()
        area = store.note_area(db, scope, source, c['path'])
        row = store.sealed('knowledge_conflicts', area, {'scope': scope, 'source': source, 'path': c['path'],
                                                         'original_path': c['original_path']},
                           prior[c['path']][1] if c['path'] in prior else None)
        db.execute('INSERT INTO knowledge_conflicts VALUES (?,?,?,?,?,?,?,?,?)',
                   (scope, source, row['path'], row['original_path'], original, c['tool'], state, first, store.now()))
        if c['path'] not in prior:
            store.log(db, scope, source, 'knowledge.sync_conflict_detected', conflict_id(source, c['path'], store.sealer, area))
    for path in sorted(set(prior) - {c['path'] for c in conflicts}):
        store.log(db, scope, source, 'knowledge.sync_conflict_cleared',
                  conflict_id(source, path, store.sealer, store.note_area(db, scope, source, path)))


def view(rows, visible_notes):
    """Conflicts for sources the caller may read, linked only to notes it can see."""
    return [{'source': r['source'], 'path': r['path'], 'original_path': r['original_path'],
             'original': r['original_id'] if r['original_id'] in visible_notes else None,
             'state': r['state'], 'tool': r['tool'], 'detected': r['detected'], 'checked': r['checked'],
             'detected_by': 'content_hash' if r['tool'] == CONTENT_TOOL else 'name',
             'basis': 'sync_conflict_copy_not_indexed'} for r in rows]
