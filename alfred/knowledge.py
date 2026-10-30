"""Read-only Markdown knowledge index. No LLM, embeddings, plugins or network.

Notes remain canonical in the explicitly selected folder. SQLite is a rebuildable
index, not permission to execute text found in a note. POSIX development target.
"""
from __future__ import annotations
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import secrets
from urllib.parse import unquote, urlsplit
from .local import Fault, canonical
from .desk_store import DeskStore
from .desk_runtime import Supervisor
from . import sealing, sync_conflicts

KINDS = ('map', 'project', 'person', 'decision', 'procedure', 'note')
MAX_NOTES, MAX_BYTES, MAX_TOTAL, MAX_LINKS = 256, 65536, 4194304, 8192
WIKI = re.compile(r'(!?)\[\[([^\]\n]{1,400})\]\]')
MARKDOWN = re.compile(r'(!?)\[[^\]\n]{0,160}\]\(([^\)\n]{1,400})\)')
# Obsidian tags: preceded by whitespace or line start; letters, digits, '_', '-' and '/'.
TAG = re.compile(r'(?<!\S)#([\w-][\w/-]{0,99})')
MAX_TAGS = 64
DEPRECATED_PROPERTIES = {'tag', 'alias', 'cssclass'}
# Callout types and the aliases Obsidian renders with the same style; others render as note.
CALLOUTS = {'note': 'note', 'abstract': 'abstract', 'summary': 'abstract', 'tldr': 'abstract', 'info': 'info',
            'todo': 'todo', 'tip': 'tip', 'hint': 'tip', 'important': 'tip', 'success': 'success', 'check': 'success',
            'done': 'success', 'question': 'question', 'help': 'question', 'faq': 'question', 'warning': 'warning',
            'caution': 'warning', 'attention': 'warning', 'failure': 'failure', 'fail': 'failure', 'missing': 'failure',
            'danger': 'danger', 'error': 'danger', 'bug': 'bug', 'example': 'example', 'quote': 'quote', 'cite': 'quote'}
# Extensions Obsidian opens as attachments; another dotted wikilink name is a note name.
ATTACHMENTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.avif', '.mp3', '.webm', '.wav', '.m4a',
               '.ogg', '.3gp', '.flac', '.mp4', '.ogv', '.mov', '.mkv', '.pdf', '.canvas', '.base'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS knowledge_meta(version INTEGER NOT NULL);
INSERT INTO knowledge_meta SELECT 2 WHERE NOT EXISTS(SELECT 1 FROM knowledge_meta);
CREATE TABLE IF NOT EXISTS knowledge_sources(
 scope TEXT NOT NULL, source TEXT NOT NULL, label TEXT NOT NULL, checked INTEGER NOT NULL,
 status TEXT NOT NULL, errors TEXT NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(scope,source));
CREATE TABLE IF NOT EXISTS knowledge_notes(
 scope TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, path TEXT NOT NULL,
 title TEXT NOT NULL, kind TEXT NOT NULL, tags TEXT NOT NULL, aliases TEXT NOT NULL,
 body TEXT NOT NULL, sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
 modified INTEGER NOT NULL, indexed INTEGER NOT NULL, status TEXT NOT NULL,
 PRIMARY KEY(scope,source,id));
CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge_notes(scope,source,status);
CREATE TABLE IF NOT EXISTS knowledge_refs(
 scope TEXT NOT NULL, source TEXT NOT NULL, origin TEXT NOT NULL, target TEXT NOT NULL,
 line INTEGER NOT NULL, syntax TEXT NOT NULL, relation TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge_vaults(
 scope TEXT NOT NULL, source TEXT NOT NULL, vault_id TEXT NOT NULL,
 device INTEGER, inode INTEGER, configuration TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(scope,source), UNIQUE(vault_id));
CREATE TABLE IF NOT EXISTS knowledge_identity(
 scope TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, external_id TEXT,
 device INTEGER, inode INTEGER, PRIMARY KEY(scope,source,id),
 UNIQUE(scope,source,external_id));
CREATE TABLE IF NOT EXISTS knowledge_history(
 scope TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
 path TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL, recorded INTEGER NOT NULL,
 PRIMARY KEY(scope,source,id,revision));
CREATE TABLE IF NOT EXISTS knowledge_anchors(
 scope TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, anchors TEXT NOT NULL,
 PRIMARY KEY(scope,source,id));
CREATE TABLE IF NOT EXISTS knowledge_conflicts(
 scope TEXT NOT NULL, source TEXT NOT NULL, path TEXT NOT NULL, original_path TEXT NOT NULL,
 original_id TEXT, tool TEXT NOT NULL, state TEXT NOT NULL, detected INTEGER NOT NULL,
 checked INTEGER NOT NULL, PRIMARY KEY(scope,source,path));
'''


def safe_text(value, limit=160):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value):
        raise Fault('invalid_note_metadata')
    try: value.encode('utf-8')
    except UnicodeError: raise Fault('invalid_note_unicode') from None
    return value


def list_value(value):
    value = value.strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
    values = [v.strip().strip('\"\'') for v in value.split(',') if v.strip()]
    if len(values) > 24:
        raise Fault('note_metadata_capacity')
    return [safe_text(v, 100) for v in values]


def safe_path(path):
    safe_text(path, 240)
    if not path or '\\' in path or ':' in path or path.startswith('/') or any(
            part in {'', '.', '..'} for part in path.split('/')):
        raise Fault('unsafe_note_path')
    return path


def parse_note(path, raw, id_key=None):
    """Deliberately bounded Markdown subset, read the way Obsidian reads it.

    Not Obsidian's complete parser, and no Markdown rendering occurs. Recognised:
    flat title/type/kind/tags/aliases frontmatter (lists or strings), wikilinks with
    display text (`[[a|b]]`, and `[[a\\|b]]` inside tables), embeds (`![[...]]`),
    Markdown links, inline and nested tags (`#a/b`), callouts (`> [!type]`), ATX
    headings and block IDs (a trailing `^id` on a paragraph, list item or line, or a
    standalone `^id` line after a structured block). Fenced and inline code, HTML and
    `%%` comments and frontmatter are not link, tag or anchor evidence. Other anchor
    forms are explicitly unsupported.
    """
    safe_path(path)
    if id_key not in {None, 'alfred_id'}: raise Fault('unsupported_note_id_key')
    if len(raw) > MAX_BYTES:
        raise Fault('note_too_large')
    try:
        body = raw.decode('utf-8-sig')
    except UnicodeError:
        raise Fault('note_not_utf8') from None
    if any((ord(c) < 32 and c not in '\n\r\t') or 127 <= ord(c) < 160 for c in body):
        raise Fault('note_control_character')
    lines, meta, start, warnings = body.splitlines(), {}, 0, []
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, min(len(lines), 81)) if lines[i].strip() == '---'), None)
        if end is None:
            raise Fault('unclosed_or_oversized_frontmatter')
        active = None
        for line in lines[1:end]:
            item = re.fullmatch(r'\s*-\s+(.+)', line)
            if item and active in {'tags', 'aliases'}:
                meta[active].extend(list_value(item[1]))
                if len(meta[active]) > 24:
                    raise Fault('note_metadata_capacity')
                continue
            pair = re.fullmatch(r'([A-Za-z_]+):\s*(.*)', line)
            if not pair:
                if line.strip() and not line.lstrip().startswith('#'):
                    warnings.append('unsupported_frontmatter_line')
                continue
            key, value = pair.groups(); active = None
            if key == 'alfred_id' and id_key is None:
                warnings.append('stable_id_not_adopted')
                continue
            if key in DEPRECATED_PROPERTIES:
                # Obsidian 1.4 and later no longer read the singular forms either.
                warnings.append('deprecated_obsidian_property_ignored')
                continue
            if key not in {'title', 'type', 'kind', 'tags', 'aliases', id_key}:
                continue
            if key in meta:
                raise Fault('duplicate_note_metadata')
            if key in {'tags', 'aliases'}:
                meta[key] = list_value(value); active = key
            else:
                meta[key] = safe_text(value.strip().strip('\"\''))
        start = end + 1
    title = meta.get('title') or next((l[2:].strip() for l in lines[start:] if l.startswith('# ')), PurePosixPath(path).stem)
    title = safe_text(title, 160)
    kind = meta.get('kind', meta.get('type', 'note')).casefold()
    if kind not in KINDS:
        warnings.append('unknown_kind_treated_as_note'); kind = 'note'
    external_id = meta.get(id_key) if id_key else None
    if external_id is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', external_id):
        raise Fault('invalid_stable_note_id')
    # A frontmatter tag may be written with or without its leading '#'.
    tags = [t[1:] if t.startswith('#') else t for t in meta.get('tags', [])]
    links, link_text, anchors, callouts, fence = [], [], [], [], None
    comment = obsidian_comment = False
    run_start = paragraph_start = previous_run = None
    blanks, open_callouts = 0, []
    for number, line in enumerate(lines[start:], start + 1):
        # Contiguous non-blank runs give standalone block IDs their spans.
        before_run, before_previous, before_blanks = run_start, previous_run, blanks
        if fence is None and not line.strip():
            if run_start is not None: previous_run = (run_start, number - 1)
            run_start = paragraph_start = None; blanks += 1
        elif run_start is None:
            run_start, blanks = number, 0
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match[1]
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            paragraph_start = None
            continue
        if fence or line.startswith('    ') or line.startswith('\t'):
            continue
        # Strip HTML and Obsidian %% comments, including multi-line ones, without rendering.
        visible = ''; rest = line
        while rest:
            if comment or obsidian_comment:
                delimiter = '-->' if comment else '%%'
                at = rest.find(delimiter)
                if at < 0: break
                rest = rest[at + len(delimiter):]; comment = obsidian_comment = False
                continue
            found = [p for p in (rest.find('<!--'), rest.find('%%')) if p >= 0]
            if not found:
                visible += rest; break
            at = min(found); visible += rest[:at]
            if rest.startswith('<!--', at):
                rest = rest[at + 4:]; comment = True
            else:
                rest = rest[at + 2:]; obsidian_comment = True
        heading = re.fullmatch(r'\s{0,3}(#{1,6})\s+(.+?)\s*', visible)
        if heading:
            name = re.sub(r'\s+#+\s*$', '', heading[2]).strip()
            # Rich inline markup in heading text remains outside this slice.
            if not any(c in name for c in '`*[]<>#'):
                anchors.append({'kind':'heading','name':name,'start_line':number,
                                'end_line':number,'level':len(heading[1])})
            # A heading is its own block: it ends the run above and is never a block span.
            run_start = paragraph_start = None; previous_run = (number, number)
        quote, depth = visible, 0
        while depth < 16:
            prefix = re.match(r'\s{0,3}>\s?', quote)
            if not prefix: break
            quote, depth = quote[prefix.end():], depth + 1
        while open_callouts and open_callouts[-1]['depth'] > depth:
            open_callouts.pop()
        for callout in open_callouts:
            callout['end_line'] = number
        marker = re.fullmatch(r'\[!([A-Za-z][A-Za-z0-9_-]{0,39})\]([+-]?)(?:\s+(.*?))?\s*', quote) if depth else None
        if marker:
            if len(callouts) >= 256: raise Fault('note_callout_capacity')
            while open_callouts and open_callouts[-1]['depth'] >= depth:
                open_callouts.pop()
            name = marker[1].casefold()
            callout = {'type': name, 'rendered_as': CALLOUTS.get(name, 'note'),
                       'title': (marker[3] or '')[:400] or name[:1].upper() + name[1:],
                       'fold': {'+': 'expanded', '-': 'collapsed'}.get(marker[2], 'none'),
                       'depth': depth, 'start_line': number, 'end_line': number}
            callouts.append(callout); open_callouts.append(callout)
        standalone = re.fullmatch(r'\s*\^([A-Za-z0-9-]+)\s*', visible)
        block = None if standalone else re.fullmatch(r'(.+\S)\s+\^([A-Za-z0-9-]+)\s*', visible)
        structured = bool(depth or re.match(r'\s*([-*+]|[0-9]{1,9}[.)])\s', visible) or visible.lstrip().startswith('|'))
        if standalone and not heading:
            # A standalone ID names the block just above it, with at most one blank line between.
            target = (before_run, number - 1) if before_run is not None else (before_previous if before_blanks <= 1 else None)
            if target and target[0] <= target[1] and not any(
                    a['kind'] == 'heading' and target[0] <= a['start_line'] <= target[1] for a in anchors):
                anchors.append({'kind':'block','name':standalone[1],'start_line':target[0],'end_line':target[1]})
        elif block and not heading:
            # A trailing ID on a paragraph names the whole paragraph; on a list item,
            # quote or table row it names that line only.
            first = paragraph_start if paragraph_start is not None and not structured else number
            anchors.append({'kind':'block','name':block[2],'start_line':first,'end_line':number})
        if not heading:
            paragraph_start = None if structured or not visible.strip() else (paragraph_start or number)
        visible = re.sub(r'(`+).*?\1', '', visible)
        for regex, syntax in ((WIKI, 'wiki'), (MARKDOWN, 'markdown')):
            for match in regex.finditer(visible):
                if syntax == 'wiki':
                    # In a table the alias separator is written as '\|'.
                    parts = re.split(r'\\?\|', match[2], maxsplit=1)
                    target, display = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')
                else:
                    target = match[2].strip().strip('<>')
                    display = match[0][match[0].index('[') + 1:match[0].index('](')].strip()
                if len(links) >= 128:
                    raise Fault('note_link_capacity')
                links.append({'target': target, 'line': number, 'syntax': syntax,
                              'relation': 'embeds' if match[1] else 'links_to'})
                link_text.append(display or None)
        # Tags are read outside links, URLs and code, as Obsidian reads them.
        plain = re.sub(r'[A-Za-z][A-Za-z0-9+.-]*://\S+', ' ', MARKDOWN.sub(' ', WIKI.sub(' ', visible)))
        for match in TAG.finditer(plain):
            name = match[1].rstrip('/')
            if name and not name.replace('/', '').isdigit() and all(t.casefold() != name.casefold() for t in tags):
                tags.append(name)
    if fence is not None: raise Fault('unclosed_code_fence')
    if comment: raise Fault('unclosed_html_comment')
    if obsidian_comment: raise Fault('unclosed_obsidian_comment')
    if len(anchors) > 1024: raise Fault('note_anchor_capacity')
    if len(tags) > MAX_TAGS:
        tags = tags[:MAX_TAGS]; warnings.append('note_tag_capacity_truncated')
    headings = [a for a in anchors if a['kind'] == 'heading']
    for i, anchor in enumerate(headings):
        anchor['end_line'] = next((a['start_line'] - 1 for a in headings[i+1:]
                                   if a['level'] <= anchor['level']), len(lines))
    return {'path': path, 'title': title, 'kind': kind, 'tags': tags,
            'aliases': meta.get('aliases', []), 'body': body, 'sha256': hashlib.sha256(raw).hexdigest(),
            'refs': links, 'link_text': link_text, 'anchors':anchors, 'callouts':callouts, 'external_id':external_id,
            'warnings': sorted(set(warnings))}


def note_structure(path, body):
    """What Obsidian would show of an indexed note's structure, re-read from its stored text.

    Elements carry line numbers into the stored body. This describes authored syntax;
    it is not a rendering and says nothing about whether the text is true.
    """
    try:
        parsed = parse_note(path, body.encode('utf-8'))
    except Fault as exc:
        return {'available': False, 'reason': exc.code}
    anchors = parsed['anchors']
    return {'available': True, 'tags': parsed['tags'], 'aliases': parsed['aliases'],
            'headings': [{k: a[k] for k in ('name', 'level', 'start_line', 'end_line')} for a in anchors if a['kind'] == 'heading'],
            'blocks': [{k: a[k] for k in ('name', 'start_line', 'end_line')} for a in anchors if a['kind'] == 'block'],
            'callouts': parsed['callouts'],
            'references': [{k: r[k] for k in ('target', 'line', 'syntax', 'relation')} | {'display': text}
                           for r, text in zip(parsed['refs'], parsed['link_text'])]}


def nocase(value):
    """Sort key matching SQLite's NOCASE collation, which folds only ASCII letters."""
    return value.translate(NOCASE)


NOCASE = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def note_id(source, path):
    """Legacy ID retained only when migrating an already indexed path."""
    return hashlib.sha256((source + '\0' + path).encode()).hexdigest()[:24]


def resolve_reference(origin, target, syntax, notes):
    """Resolve only within one source. Never dereference a URL or filesystem path."""
    raw_path, delimiter, raw_fragment = target.partition('#')
    try:
        target = unquote(raw_path, errors='strict')
        fragment = unquote(raw_fragment, errors='strict') if delimiter else None
    except UnicodeError: return None, 'malformed_link', None
    if any(ord(c) < 32 or 127 <= ord(c) < 160 for c in target + (fragment or '')) or '\\' in target or target.startswith('/'):
        return None, 'blocked_path', None
    try: parsed = urlsplit(target)
    except ValueError: return None, 'malformed_link', None
    if parsed.scheme or parsed.netloc:
        return None, ('external' if parsed.scheme in {'http', 'https', 'mailto'} else 'blocked_scheme'), None
    path = target
    if '?' in path:
        return None, 'unsupported_query', None
    suffix = PurePosixPath(path).suffix.lower()
    if suffix and suffix != '.md':
        # Obsidian reads `[[v1.2 notes]]` as a note name, not an attachment.
        # A short alphanumeric suffix is still read as a file extension.
        if syntax != 'wiki' or suffix in ATTACHMENTS or re.fullmatch(r'\.(?=[a-z0-9]*[a-z])[a-z0-9]{1,5}', suffix):
            return None, 'attachment_not_indexed', None
        suffix = ''
    if path and not suffix: path += '.md'
    keys = {}
    for n in notes:
        keys.setdefault(n['path'].casefold(), []).append(n['id'])
    if not path:
        found = {origin}
        paths = []
    elif syntax == 'markdown':
        paths = [posixpath.normpath(posixpath.join(posixpath.dirname(next(n['path'] for n in notes if n['id'] == origin)), path))]
    else:
        paths = [posixpath.normpath(path)]
    if any(p == '..' or p.startswith('../') for p in paths):
        return None, 'blocked_path', None
    if path: found = set(v for p in paths for v in keys.get(p.casefold(), []))
    if not found and syntax == 'wiki' and '/' not in path:
        stem = PurePosixPath(path).stem.casefold()
        for n in notes:
            if PurePosixPath(n['path']).stem.casefold() == stem or stem in {a.casefold() for a in n['aliases']}:
                found.add(n['id'])
    elif not found and syntax == 'wiki':
        # Obsidian also resolves a trailing partial path such as [[sub/Note]] to a/sub/Note.md.
        tail = '/' + paths[0].casefold()
        found = {n['id'] for n in notes if n['path'].casefold().endswith(tail)}
    if len(found) != 1: return None, 'ambiguous' if found else 'missing', None
    identity = next(iter(found))
    if fragment is None: return identity, 'resolved', None
    parts = fragment.split('#')
    if not all(parts) or any(c in fragment for c in '[]<>`*') or (fragment.startswith('^') and len(parts) > 1):
        return None, 'unsupported_anchor', None
    kind, name = ('block', fragment[1:]) if fragment.startswith('^') else ('heading', parts[-1])
    if kind == 'block' and not re.fullmatch(r'[A-Za-z0-9-]+', name):
        return None, 'unsupported_anchor', None
    note = next((n for n in notes if n['id'] == identity), None)
    available = (note or {}).get('anchors', [])
    anchors = [a for a in available if a['kind'] == kind and
               (a['name'] == name if kind == 'block' else a['name'].casefold() == name.casefold())]
    if kind == 'heading' and len(parts) > 1:
        # A nested subpath [[Note#Parent#Child]] names the enclosing headings in order.
        def enclosing(anchor):
            outer = [a['name'].casefold() for a in available if a['kind'] == 'heading' and a['level'] < anchor['level']
                     and a['start_line'] < anchor['start_line'] <= a['end_line']]
            wanted = iter(outer)
            return all(any(p.casefold() == o for o in wanted) for p in parts[:-1])
        anchors = [a for a in anchors if enclosing(a)]
    if len(anchors) != 1: return None, 'ambiguous_anchor' if anchors else 'missing_anchor', None
    return identity, 'resolved', {k:anchors[0][k] for k in ('kind','name','start_line','end_line')}


def resolve_target(origin, target, syntax, notes):
    identity, state, _ = resolve_reference(origin, target, syntax, notes)
    return identity, state


class KnowledgeStore(DeskStore):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        # In-process handles for approved vault writes; the database never stores vault roots.
        self.vault_writers = {}
        with self.connection() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_meta'").fetchone()
            versions = [r[0] for r in db.execute('SELECT version FROM knowledge_meta')] if exists else [2]
            if versions not in ([1], [2]): raise Fault('unsupported_knowledge_version')
            migration = ''
            if versions == [1]:
                # Remove path uniqueness: historical identities may share a reused path.
                definition = SCHEMA[SCHEMA.index('CREATE TABLE IF NOT EXISTS knowledge_notes('):
                                    SCHEMA.index('CREATE INDEX IF NOT EXISTS knowledge_scope')]
                migration = (definition.replace('knowledge_notes(', 'knowledge_notes_v2(') +
                             'INSERT INTO knowledge_notes_v2 SELECT * FROM knowledge_notes;'
                             'DROP TABLE knowledge_notes;'
                             'ALTER TABLE knowledge_notes_v2 RENAME TO knowledge_notes;'
                             'UPDATE knowledge_meta SET version=2;')
            db.executescript('BEGIN IMMEDIATE;\n' + migration + SCHEMA + '\nCOMMIT;')

    def select_vault(self, bearer, label, root_identity, configuration):
        """Persist selection outside the vault; a restart cannot adopt a replacement root."""
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'source'}); key = (p['scope'], p['id'])
            old = self.opened('knowledge_vaults', db.execute('SELECT * FROM knowledge_vaults WHERE scope=? AND source=?', key).fetchone())
            config = json.dumps(configuration, sort_keys=True)
            area = self.source_area(db, *key)
            if old:
                if old['configuration'] != config: raise Fault('vault_selection_changed')
                if root_identity and old['device'] is not None and root_identity != (old['device'], old['inode']):
                    raise Fault('vault_root_replaced')
                vault_id = old['vault_id']
                if root_identity and old['device'] is None:
                    db.execute('UPDATE knowledge_vaults SET device=?,inode=? WHERE scope=? AND source=?', (*root_identity,*key))
            else:
                vault_id = secrets.token_hex(12)
                row = self.sealed('knowledge_vaults', area, {'scope':key[0],'source':key[1],'configuration':config})
                db.execute('INSERT INTO knowledge_vaults VALUES (?,?,?,?,?,?,?)',
                           (*key,vault_id,*(root_identity or (None,None)),row['configuration'],0))
            if not db.execute('SELECT 1 FROM knowledge_sources WHERE scope=? AND source=?', key).fetchone():
                row = self.sealed('knowledge_sources', area, {'scope':key[0],'source':key[1],'label':label,'errors':'[]'})
                db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?)',
                           (*key,row['label'],self.now(),'unavailable',row['errors'],''))
            return vault_id

    def source_area(self, db, scope, source):
        """The area a source's own records (label, settings, errors) are sealed under. Until
        source rules arrive (step 2, part 5), every source is in the workspace's default area."""
        return sealing.default_area(db)

    def note_area(self, db, scope, source, path):
        """The area a note is sealed and fingerprinted under. Every caller asks here, so folder
        rules (step 2, part 5) change one place. Until then a note is in its source's area."""
        return self.source_area(db, scope, source)

    def note_fingerprint(self, db, scope, source, path, digest):
        """A plain SHA-256 of a note's text (or of its path) in the form the index keeps:
        keyed for the note's area in a sealed workspace."""
        return self.sealer.fingerprint(self.note_area(db, scope, source, path), digest)

    @staticmethod
    def vault_write(capability):
        """The module behind an approved vault write capability, or None for any other action."""
        from . import inbox, vault_append
        return {inbox.CAPABILITY: inbox, vault_append.CAPABILITY: vault_append}.get(capability)

    def evidence_valid(self, db, row):
        write = self.vault_write(row['capability'])
        if write:
            return write.current(self, db, row)
        if super().evidence_valid(db, row):
            return True
        from .conversation import knowledge_action_current
        if knowledge_action_current(self, db, row):
            return True
        # A draft the person accepted from a routine nomination (M10).
        from .routines import action_current
        if action_current(self, db, row):
            return True
        # A lapsed or archived draft the owner re-proposed after its conversation ended.
        from .drafts import reproposal_current
        if reproposal_current(self, db, row):
            return True
        # A draft a brain proposed at autonomy 2, while its accepted result and every
        # excerpt it was given are still current (AGENT_HUB.md, H1).
        from .brain import action_current as brain_action_current
        return brain_action_current(self, db, row)

    def valid_origin(self, db, row):
        write = self.vault_write(row['capability'])
        if not write:
            return super().valid_origin(db, row)
        paused = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (row['scope'],)).fetchone()
        return not (paused and paused[0]) and row['expires'] > self.now() and write.current(self, db, row)

    def action_view(self, row):
        view = super().action_view(row)
        write = self.vault_write(row['capability'])
        if write:
            view['effect'] = write.EFFECT
            if 'diff' in view['parameters']:
                # The exact change the person approves, bound by the fingerprint.
                view['diff'] = view['parameters']['diff']
        return view

    def execute_local(self, bearer, job):
        with self.connection() as db:
            kind = db.execute('SELECT capability FROM actions WHERE scope=? AND id=?', (job['scope'], job['id'])).fetchone()
        write = self.vault_write(kind['capability']) if kind else None
        if not write:
            return super().execute_local(bearer, job)
        with self.transaction() as db:
            p, row = self.leased(db, bearer, job)
            row = dict(row)
        outcome = write.execute(self, row)
        with self.transaction() as db:
            if outcome in write.SUCCESS:
                self.log(db, row['scope'], p['id'], write.RECEIPT, row['id'])
                return
            # Nothing was written by this action. Record why, and never retry over a human file.
            proof = canonical({'type': write.REFUSED[0], 'reason': outcome, 'sent': False})
            db.execute("UPDATE actions SET state='failed',proof=? WHERE scope=? AND id=? AND state='executing'", (proof, row['scope'], row['id']))
            db.execute("UPDATE outbox SET state='done' WHERE scope=? AND action_id=?", (row['scope'], row['id']))
            self.log(db, row['scope'], p['id'], write.REFUSED[1], row['id'])

    def verify_draft(self, db, row):
        write = self.vault_write(row['capability'])
        if not write:
            return super().verify_draft(db, row)
        proof = write.verify(self, row)
        if proof is None:
            return None
        db.execute('UPDATE actions SET state=?,proof=? WHERE scope=? AND id=?', ('verified', canonical(proof), row['scope'], row['id']))
        db.execute('UPDATE outbox SET state=? WHERE scope=? AND action_id=?', ('done', row['scope'], row['id']))
        self.log(db, row['scope'], row['actor'], write.VERIFIED, row['id'])
        return proof

    def finish(self, bearer, job):
        with self.connection() as db:
            row = db.execute('SELECT state,proof FROM actions WHERE scope=? AND id=?', (job['scope'], job['id'])).fetchone()
        if row and row['state'] == 'failed':
            return {'id': job['id'], 'state': 'failed', 'proof': json.loads(row['proof'])}
        return super().finish(bearer, job)

    def replace_notes(self, bearer, label, notes, errors, vault_id=None, conflicts=(), *, rebuild=False):
        if len(notes) > MAX_NOTES or sum(len(n['refs']) for n in notes) > MAX_LINKS:
            raise Fault('knowledge_capacity')
        paths, external_ids = set(), set()
        for note in notes:
            path = safe_path(note['path'])
            if path.casefold() in paths: raise Fault('duplicate_note_path')
            paths.add(path.casefold())
            external = note.get('external_id')
            if external is not None:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', external): raise Fault('invalid_stable_note_id')
                if external in external_ids: raise Fault('duplicate_stable_note_id')
                external_ids.add(external)
        conflicts = sync_conflicts.checked(conflicts, paths, {n['path'].casefold(): n['sha256'] for n in notes})
        notes = sorted(notes, key=lambda n:n['path'])
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'source'}); scope, source = p['scope'], p['id']
            # In a sealed workspace the stored digests are keyed (sealing.py); key the scanner's
            # once, so every comparison below is between values of the same form.
            area = self.source_area(db, scope, source)
            areas = {n['path']: self.note_area(db, scope, source, n['path']) for n in notes}
            notes = [n | {'sha256': self.sealer.fingerprint(areas[n['path']], n['sha256']),
                          'external_id': self.external_key(areas[n['path']], n.get('external_id'))} for n in notes]
            snapshot = self.sealer.fingerprint(area, hashlib.sha256(json.dumps([(n['path'],n['sha256']) for n in notes], sort_keys=True).encode()).hexdigest())
            selection = db.execute('SELECT vault_id FROM knowledge_vaults WHERE scope=? AND source=?', (scope,source)).fetchone()
            if selection and vault_id != selection['vault_id']: raise Fault('vault_selection_required')
            # Raw rows are kept beside the opened ones: a value whose text has not changed is
            # written back as it was, so an unchanged rescan seals nothing new.
            old_raw = db.execute('SELECT * FROM knowledge_sources WHERE scope=? AND source=?', (scope,source)).fetchone()
            old_raw = dict(old_raw) if old_raw else None
            old_source = self.opened('knowledge_sources', old_raw)
            if rebuild:
                # MEM-012: drop only the projections, in this same transaction. The durable catalogue
                # (history, identities, vault binding) then restores every identity and revision below.
                for table in ('knowledge_notes','knowledge_refs','knowledge_anchors'):
                    db.execute(f'DELETE FROM {table} WHERE scope=? AND source=?', (scope,source))
            stored = {r['id']: dict(r) for r in db.execute('SELECT n.*,i.external_id,i.device,i.inode FROM knowledge_notes n LEFT JOIN knowledge_identity i USING(scope,source,id) WHERE n.scope=? AND n.source=?', (scope,source))}
            prior = [self.opened('knowledge_notes', r) for r in stored.values()]
            # Rebuild removed projections from the durable catalogue, not filenames.
            present = {r['id'] for r in prior}
            for h in db.execute('SELECT h.*,i.external_id,i.device,i.inode FROM knowledge_history h LEFT JOIN knowledge_identity i USING(scope,source,id) WHERE h.scope=? AND h.source=? AND h.revision=(SELECT max(x.revision) FROM knowledge_history x WHERE x.scope=h.scope AND x.source=h.source AND x.id=h.id)', (scope,source)):
                if h['id'] not in present: prior.append(self.opened('knowledge_history', h) | {'indexed':h['recorded']})
            # Seed the migration journal without altering old evidence IDs or revisions.
            for row in prior:
                if not db.execute('SELECT 1 FROM knowledge_history WHERE scope=? AND source=? AND id=? AND revision=?', (scope,source,row['id'],row['revision'])).fetchone():
                    self._history(db, scope, source, row['id'], row['revision'], row['path'], row['sha256'], row['status'], row['indexed'])
            assigned, used = [], set()
            current_files = {tuple(n['file_identity']):n['path'] for n in notes if n.get('file_identity')}
            for n in notes:
                external, file_key = n.get('external_id'), n.get('file_identity')
                at_path = [r for r in prior if r['path']==n['path'] and r['status'] in {'ready','unavailable'}]
                by_external = [r for r in prior if external is not None and r['external_id']==external]
                if file_key and any((r['device'],r['inode'])==tuple(file_key) and r['external_id'] is not None
                                    and r['external_id']!=external and r['status'] in {'ready','unavailable'} for r in prior):
                    raise Fault('stable_note_id_changed')
                if by_external:
                    row = by_external[0]
                    if row['path'] != n['path'] and row['path'].casefold() in paths:
                        raise Fault('stable_note_id_rebound')
                    if at_path and at_path[0]['id'] != row['id']: raise Fault('stable_note_id_rebound')
                elif file_key and any((r['device'],r['inode'])==tuple(file_key) and r['status']=='ready'
                                      and r['sha256']==n['sha256'] and r['external_id']==external for r in prior):
                    # Filesystem continuity takes precedence when an old path is reused.
                    candidates = [r for r in prior if (r['device'],r['inode'])==tuple(file_key)
                                  and r['status']=='ready' and r['sha256']==n['sha256'] and r['external_id']==external]
                    if len(candidates)!=1: raise Fault('duplicate_stable_note_id')
                    row = candidates[0]
                elif at_path and current_files.get((at_path[0]['device'],at_path[0]['inode']),n['path'])==n['path']:
                    row = at_path[0]
                    if row['external_id'] != external and row['external_id'] is not None:
                        raise Fault('stable_note_id_changed')
                else:
                    row = None
                    # Content/name equality without filesystem or adopted-ID proof is insufficient.
                    if row is None and any(r['status']=='ready' and ((r['sha256']==n['sha256'] and r['path'].casefold() not in paths)
                                           or (file_key and (r['device'],r['inode'])==tuple(file_key) and r['path']!=n['path'])) for r in prior):
                        errors.append({'path':n['path'],'code':'rename_identity_unproven'})
                identity = row['id'] if row else secrets.token_hex(12)
                if not row and db.execute('SELECT 1 FROM knowledge_notes WHERE scope=? AND id=?', (scope,identity)).fetchone():
                    raise Fault('duplicate_stable_note_id')
                if identity in used: raise Fault('duplicate_stable_note_id')
                used.add(identity)
                changed = row and (row['sha256']!=n['sha256'] or row['path']!=n['path'] or row['status']!='ready'
                                   or (old_source and old_source['status']=='unavailable'))
                revision = row['revision'] + int(bool(changed)) if row else 1
                assigned.append((n,identity,revision))
            stored_anchors = {r['id']: dict(r) for r in db.execute('SELECT * FROM knowledge_anchors WHERE scope=? AND source=?', (scope,source))}
            stored_refs = {}
            for r in db.execute('SELECT * FROM knowledge_refs WHERE scope=? AND source=?', (scope,source)):
                stored_refs.setdefault((r['origin'],r['line'],r['syntax'],r['relation']), []).append(dict(r))
            db.execute('DELETE FROM knowledge_refs WHERE scope=? AND source=?', (scope,source))
            db.execute('DELETE FROM knowledge_anchors WHERE scope=? AND source=?', (scope,source))
            for row in prior:
                if row['id'] in used: continue
                failed = any(e.get('path')==row['path'] or row['path'].startswith(e.get('path','')+'/') for e in errors if e.get('path'))
                state = 'unavailable' if failed else 'missing'
                revision = row['revision'] + int(row['status']!=state)
                empty = self.sealed('knowledge_notes', self.note_area(db,scope,source,row['path']),
                                    {'scope':scope,'source':source,'id':row['id'],'body':'','tags':'[]','aliases':'[]'}, stored.get(row['id']))
                db.execute("UPDATE knowledge_notes SET status=?,revision=?,body=?,tags=?,aliases=? WHERE scope=? AND source=? AND id=?",
                           (state,revision,empty['body'],empty['tags'],empty['aliases'],scope,source,row['id']))
                if not db.execute('SELECT 1 FROM knowledge_history WHERE scope=? AND source=? AND id=? AND revision=?', (scope,source,row['id'],revision)).fetchone():
                    self._history(db, scope, source, row['id'], revision, row['path'], row['sha256'], state, self.now())
            for n,identity,revision in assigned:
                note = self.sealed('knowledge_notes', areas[n['path']], {'scope':scope,'source':source,'id':identity,'path':n['path'],'title':n['title'],
                                   'tags':json.dumps(n['tags']),'aliases':json.dumps(n['aliases']),'body':n['body']}, stored.get(identity))
                db.execute('INSERT INTO knowledge_notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(scope,source,id) DO UPDATE SET path=excluded.path,title=excluded.title,kind=excluded.kind,tags=excluded.tags,aliases=excluded.aliases,body=excluded.body,sha256=excluded.sha256,revision=excluded.revision,modified=excluded.modified,indexed=excluded.indexed,status=excluded.status',
                           (scope,source,identity,note['path'],note['title'],n['kind'],note['tags'],note['aliases'],note['body'],n['sha256'],revision,n['modified'],self.now(),'ready'))
                db.execute('INSERT INTO knowledge_identity VALUES (?,?,?,?,?,?) ON CONFLICT(scope,source,id) DO UPDATE SET external_id=excluded.external_id,device=excluded.device,inode=excluded.inode',
                           (scope,source,identity,n.get('external_id'),*n.get('file_identity',(None,None))))
                if not db.execute('SELECT 1 FROM knowledge_history WHERE scope=? AND source=? AND id=? AND revision=?', (scope,source,identity,revision)).fetchone():
                    self._history(db, scope, source, identity, revision, n['path'], n['sha256'], 'ready', self.now())
                anchors = self.sealed('knowledge_anchors', areas[n['path']], {'scope':scope,'source':source,'id':identity,'anchors':json.dumps(n.get('anchors',[]))},
                                      stored_anchors.get(identity))
                db.execute('INSERT INTO knowledge_anchors VALUES (?,?,?,?)', (scope,source,identity,anchors['anchors']))
                db.executemany('INSERT INTO knowledge_refs VALUES (?,?,?,?,?,?,?)', [(scope,source,identity,self._ref_target(areas[n['path']],scope,source,identity,r,stored_refs),r['line'],r['syntax'],r['relation']) for r in n['refs']])
            # Conflict copies are recorded with their originals' IDs, never indexed as notes (MEM-014).
            sync_conflicts.record(self,db,scope,source,conflicts,{n['path']:identity for n,identity,_ in assigned})
            row = self.sealed('knowledge_sources', area, {'scope':scope,'source':source,'label':label,'errors':json.dumps(errors[:32])}, old_raw)
            db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope,source) DO UPDATE SET label=excluded.label,checked=excluded.checked,status=excluded.status,errors=excluded.errors,snapshot=excluded.snapshot',
                       (scope,source,row['label'],self.now(),'attention' if errors else 'ready',row['errors'],snapshot))
            if db.execute('SELECT count(*) FROM knowledge_notes WHERE scope=?', (scope,)).fetchone()[0] > 10000 or db.execute('SELECT count(*) FROM knowledge_history WHERE scope=?', (scope,)).fetchone()[0] > 10000:
                raise Fault('knowledge_history_capacity')
            if selection:
                db.execute('UPDATE knowledge_vaults SET confirmed=? WHERE scope=? AND source=?', (self.now(),scope,source))
            if not old_source or old_source['snapshot'] != snapshot:
                self.log(db,scope,source,'knowledge.indexed',snapshot[:16])

    def _ref_target(self, area, scope, source, origin, ref, stored_refs):
        """A link target as stored: the sealed value already kept for the same link if its
        text is unchanged, otherwise newly sealed."""
        row = {'scope':scope,'source':source,'origin':origin,'line':ref['line'],'syntax':ref['syntax'],'relation':ref['relation'],'target':ref['target']}
        if self.sealer.sealed:
            for kept in stored_refs.get((origin,ref['line'],ref['syntax'],ref['relation']), ()):
                if sealing.area_of(kept['target']) == area and self.opened('knowledge_refs', kept)['target'] == ref['target']:
                    return kept['target']
        return self.sealed('knowledge_refs', area, row)['target']

    def _history(self, db, scope, source, identity, revision, path, digest, status, recorded):
        row = self.sealed('knowledge_history', self.note_area(db, scope, source, path),
                          {'scope':scope,'source':source,'id':identity,'revision':revision,'path':path})
        db.execute('INSERT INTO knowledge_history VALUES (?,?,?,?,?,?,?,?)',
                   (scope,source,identity,revision,row['path'],digest,status,recorded))

    def file_digest(self, scope, source, path, data: bytes, db=None) -> str:
        """A vault file's digest in the form the index keeps: keyed in a sealed workspace."""
        plain = hashlib.sha256(data).hexdigest()
        if not self.sealer.sealed:
            return plain
        if db is None:
            with self.connection() as db:
                return self.note_fingerprint(db, scope, source, path, plain)
        return self.note_fingerprint(db, scope, source, path, plain)

    def note_at(self, db, scope, source, path):
        """The ready note indexed at ``path``, opened, or None. Paths are sealed, so they are
        compared here rather than in SQL."""
        if not self.sealer.sealed:
            return self.opened('knowledge_notes', db.execute(
                "SELECT * FROM knowledge_notes WHERE scope=? AND source=? AND path=? AND status='ready'", (scope, source, path)).fetchone())
        for row in db.execute("SELECT * FROM knowledge_notes WHERE scope=? AND source=? AND status='ready'", (scope, source)):
            note = self.opened('knowledge_notes', row)
            if note['path'] == path:
                return note
        return None

    def external_key(self, area, external):
        """A note's stable id from its frontmatter, keyed in a sealed workspace like a digest."""
        if external is None or not self.sealer.sealed:
            return external
        return self.sealer.fingerprint(area, sealing.text_digest(external))

    def knowledge_unavailable(self, bearer, code):
        with self.transaction() as db:
            # A revoked source cannot refresh its index. Readers also recheck its grant.
            p = self.authenticate(db, bearer, {'source'})
            kept = db.execute('SELECT * FROM knowledge_sources WHERE scope=? AND source=?', (p['scope'],p['id'])).fetchone()
            row = self.sealed('knowledge_sources', self.source_area(db, p['scope'], p['id']), {'scope':p['scope'],'source':p['id'],
                              'label':'Selected Markdown vault','errors':json.dumps([{'code':code}])}, dict(kept) if kept else None)
            if not kept:
                db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?)', (p['scope'],p['id'],row['label'],self.now(),'unavailable',row['errors'],''))
            db.execute('UPDATE knowledge_sources SET status=\'unavailable\',errors=?,checked=? WHERE scope=? AND source=?',
                       (row['errors'],self.now(),p['scope'],p['id']))

    def knowledge(self, bearer, query='', kind='', *, purpose='read'):
        safe_text(query, 160)
        if kind and kind not in KINDS: raise Fault('invalid_note_kind')
        with self.transaction() as db:
            p = self.authenticate(db,bearer,{'owner','reader'}); scope = p['scope']
            from .policy import permitted
            # Grants are checked before anything is opened, so nothing is opened that the reader may not see.
            sources = [self.opened('knowledge_sources', r) for r in db.execute('SELECT s.* FROM knowledge_sources s JOIN credentials c ON c.id=s.source AND c.scope=s.scope WHERE s.scope=? AND c.revoked=0 AND c.expires>?', (scope,self.now()))
                       if permitted(db,p,r['source'],self.now(),purpose)]
            permitted = {s['source'] for s in sources if s['status'] in {'ready','attention'}}
            notes = sorted((self.opened('knowledge_notes', r) for r in db.execute('SELECT * FROM knowledge_notes WHERE scope=? AND status=\'ready\'', (scope,)) if r['source'] in permitted),
                           key=lambda n: (nocase(n['path']), n['id']))
            if len(notes)>MAX_NOTES:
                raise Fault('knowledge_view_capacity',409)
            anchors = {(r['source'],r['id']):json.loads(self.opened('knowledge_anchors', r)['anchors']) for r in db.execute('SELECT * FROM knowledge_anchors WHERE scope=?', (scope,)) if r['source'] in permitted}
            selections = {r['source']:dict(r) for r in db.execute('SELECT source,vault_id,confirmed FROM knowledge_vaults WHERE scope=?', (scope,))}
            vaults = {source:r['vault_id'] for source,r in selections.items()}
            for n in notes:
                n['anchors'] = anchors.get((n['source'],n['id']),[])
                n['tags'], n['aliases'] = json.loads(n['tags']), json.loads(n['aliases'])
            refs = sorted((self.opened('knowledge_refs', r) for r in db.execute('SELECT * FROM knowledge_refs WHERE scope=?', (scope,)) if r['source'] in permitted),
                          key=lambda r: (r['source'], r['origin'], r['line'], r['target']))
            if len(refs)>MAX_LINKS:
                raise Fault('knowledge_link_view_capacity',409)
            links, issues = [], []
            groups = {s: [n for n in notes if n['source'] == s] for s in permitted}
            by_id = {n['id']: n for n in notes}
            for r in refs:
                target, state, anchor = resolve_reference(r['origin'],r['target'],r['syntax'],groups[r['source']])
                original = by_id[r['origin']]
                evidence = {'source':r['origin'],'line':r['line'],'source_sha256':original['sha256'],
                            'source_revision':original['revision'],'relation':r['relation'],'basis':'explicit_note_reference'}
                if state == 'resolved':
                    destination = by_id[target]
                    links.append({**evidence,'target':target,'target_sha256':destination['sha256'],
                                  'target_revision':destination['revision'],'anchor':anchor})
                elif state not in {'external','attachment_not_indexed'}:
                    issues.append({'note':r['origin'],'path':original['path'],'line':r['line'],'target':r['target'],'status':state})
            conflicts = sync_conflicts.view(sorted((self.opened('knowledge_conflicts', r) for r in db.execute('SELECT * FROM knowledge_conflicts WHERE scope=?', (scope,)) if r['source'] in permitted),
                                                   key=lambda r: (r['source'], r['path'])), by_id)
            terms = query.casefold().split()
            selected = [n for n in notes if (not kind or n['kind']==kind) and all(t in (n['title']+' '+n['path']+' '+n['body']+' '+' '.join(n['tags']+n['aliases'])).casefold() for t in terms)]
            def public(n):
                snippet = n['body'].splitlines()
                line = next((i for i,l in enumerate(snippet,1) if terms and any(t in l.casefold() for t in terms)),1)
                excerpt = snippet[line-1][:260] if snippet else ''
                return {k:n[k] for k in ('id','source','path','title','kind','tags','sha256','revision','modified','indexed')} | {'aliases':n['aliases'],'vault_id':vaults.get(n['source']),'snippet':excerpt,'line':line,'basis':'authored_note_not_verified_fact'}
            map_roots = [n['id'] for n in notes if n['path'].casefold()=='map.md']
            distances = {i:0 for i in map_roots}; queue = deque(map_roots)
            adjacency = {}
            for link in links: adjacency.setdefault(link['source'],set()).add(link['target'])
            while queue:
                item=queue.popleft()
                for target in adjacency.get(item,()):
                    if target not in distances:
                        distances[target]=distances[item]+1;queue.append(target)
            # Map health describes curated vaults; an imported export snapshot has no MAP.md.
            imported = {r[0] for r in db.execute('SELECT source FROM connector_instances WHERE scope=?', (scope,))} if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connector_instances'").fetchone() else set()
            missing_map = sorted(s for s in permitted if s not in imported and not any(n['source']==s and n['path'].casefold()=='map.md' for n in notes))
            return {'scope':scope,'query':query,'kind':kind,'now':self.now(),'paused':self.paused(scope),
                    'nodes':[public(n) for n in notes], 'results':[public(n) for n in selected], 'links':links,
                    'issues':issues, 'sources':[{'source':s['source'],'vault_id':vaults.get(s['source']),'label':s['label'],'last_complete_scan':selections.get(s['source'],{}).get('confirmed'),'last_confirmed_snapshot':s['snapshot'],'checked':s['checked'],'status':s['status'],'errors':json.loads(s['errors'])} for s in sources],
                    'map_health':{'roots':map_roots,'missing_map_sources':missing_map,'outside_two_hops':[n['id'] for n in notes if n['source'] not in imported and distances.get(n['id'],3)>2]},
                    'sync_conflicts':conflicts,
                    'counts':{'notes':len(notes),'matches':len(selected),'links':len(links),'issues':len(issues),'sync_conflicts':len(conflicts)},
                    'live_ai':False,'read_only':True,'content_egress':False,'anchor_validation':True,'anchor_support':'ATX plain-text headings, nested heading subpaths, trailing and standalone block IDs'}

    def knowledge_note(self,bearer,identity, *, purpose='read'):
        if not re.fullmatch(r'[0-9a-f]{24}',identity): raise Fault('invalid_note_id')
        with self.connection() as db:
            p=self.authenticate(db,bearer,{'owner','reader'})
            row=self.opened('knowledge_notes', db.execute('SELECT n.* FROM knowledge_notes n JOIN credentials c ON c.id=n.source AND c.scope=n.scope JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source WHERE n.scope=? AND n.id=? AND n.status=\'ready\' AND c.revoked=0 AND c.expires>? AND s.status IN (\'ready\',\'attention\')', (p['scope'],identity,self.now())).fetchone())
            from .policy import permitted
            if not row or not permitted(db,p,row['source'],self.now(),purpose): raise Fault('note_not_available',404)
            return {k:row[k] for k in ('id','path','title','kind','body','sha256','revision','modified','indexed')} | {'basis':'authored_note_not_verified_fact','structure':note_structure(row['path'],row['body'])}


class MarkdownVault:
    def __init__(self,store,bearer,root,label='Local Markdown vault',*,exclude_folders=(),id_key=None):
        self.store,self.bearer,self.root,self.label=store,bearer,Path(root).absolute(),safe_text(label)
        if '..' in self.root.parts: raise Fault('unsafe_vault_path')
        if id_key not in {None,'alfred_id'}: raise Fault('unsupported_note_id_key')
        if not isinstance(exclude_folders,(tuple,list)) or len(exclude_folders)>32:
            raise Fault('invalid_vault_exclusions')
        self.exclusions = tuple(sorted({safe_path(p) for p in exclude_folders}))
        self.id_key = id_key
        if store.path.resolve().is_relative_to(self.root.resolve()):
            raise Fault('database_must_be_outside_vault')
        self.principal=store.principal(bearer,{'source'})
        self.configuration={'excluded_folders':self.exclusions,'id_key':id_key}
        self.identity,self.vault_id=None,None
        self.health={'configured':True,'status':'starting','last_scan':None,'errors':[]}
        # Missing selections still start the host with honest source health.
        try:
            fd=self.open_root()
            try:
                info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)
            finally: os.close(fd)
            self.vault_id=store.select_vault(bearer,self.label,self.identity,self.configuration)
        except (OSError,Fault) as exc:
            code=exc.code if isinstance(exc,Fault) else 'vault_unavailable'
            if isinstance(exc,OSError):
                self.vault_id=store.select_vault(bearer,self.label,None,self.configuration)
            store.knowledge_unavailable(bearer,code)
            self.health.update(status='unavailable',errors=[{'code':code}])
        if hasattr(store,'vault_writers') and self.vault_id:
            store.vault_writers[self.principal['id']]=self

    def digest(self,path,data):
        """A file's digest as the index keeps it, so approved digests compare like with like."""
        return self.store.file_digest(self.principal['scope'],self.principal['id'],path,data)

    def _inbox_directory(self,create):
        from .inbox import FOLDER
        fd=self.open_root()
        try:
            info=os.fstat(fd)
            if self.identity is None or (info.st_dev,info.st_ino)!=self.identity:
                raise Fault('vault_root_replaced')
            for part in FOLDER:
                if create:
                    try: os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError: pass
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                os.close(fd);fd=nxt
            return fd
        except BaseException:
            os.close(fd);raise

    @staticmethod
    def _read_regular(fd,name):
        try: handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
        except OSError: return None
        try:
            info=os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_BYTES: return None
            chunks=[]
            while True:
                chunk=os.read(handle,65536)
                if not chunk: break
                chunks.append(chunk)
            return b''.join(chunks)
        finally: os.close(handle)

    def create_inbox_note(self,filename,data,digest):
        """Create-only write. Never replaces an existing file, never follows a link."""
        try: fd=self._inbox_directory(True)
        except (OSError,Fault): return 'vault_unavailable'
        try:
            existing=self._read_regular(fd,filename)
            if existing is not None:
                from .inbox import FOLDER
                return 'exists_same' if self.digest('/'.join((*FOLDER,filename)),existing)==digest else 'destination_exists'
            temporary='.alfred-'+secrets.token_hex(8)+'.tmp'
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd)
            try:
                view=memoryview(data)
                while view: view=view[os.write(out,view):]
                os.fsync(out)
            finally: os.close(out)
            try:
                # link() creates the destination atomically and fails if anything is already there.
                os.link(temporary,filename,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
            except FileExistsError:
                return 'destination_exists'
            finally:
                os.unlink(temporary,dir_fd=fd)
            os.fsync(fd)
            return 'created'
        except OSError:
            return 'write_failed'
        finally: os.close(fd)

    def read_inbox_note(self,filename):
        try: fd=self._inbox_directory(False)
        except (OSError,Fault): return None
        try: return self._read_regular(fd,filename)
        finally: os.close(fd)

    def _note_directory(self,path):
        """Open an indexed note's folder below the verified root without following links."""
        parts=safe_path(path).split('/')
        if self.excluded(path) or not path.lower().endswith('.md') or sync_conflicts.conflict_copy(path):
            raise Fault('note_path_not_writable')
        fd=self.open_root()
        try:
            info=os.fstat(fd)
            if self.identity is None or (info.st_dev,info.st_ino)!=self.identity:
                raise Fault('vault_root_replaced')
            for part in parts[:-1]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                os.close(fd);fd=nxt
            return fd,parts[-1]
        except BaseException:
            os.close(fd);raise

    def _read_note_at(self,fd,name):
        """A regular, single-link note read in one stable observation, or (None, None)."""
        try: handle=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
        except OSError: return None,None
        try:
            before=os.fstat(handle)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_BYTES: return None,None
            chunks=[]
            while True:
                chunk=os.read(handle,65536)
                if not chunk: break
                chunks.append(chunk)
            data=b''.join(chunks)
            if self.signature(os.fstat(handle))!=self.signature(before) or len(data)!=before.st_size: return None,None
            return data,before
        finally: os.close(handle)

    def read_note(self,path):
        try: fd,name=self._note_directory(path)
        except (OSError,Fault): return None
        try: return self._read_note_at(fd,name)[0]
        finally: os.close(fd)

    def append_to_note(self,path,base_sha256,offset,inserted,result_sha256):
        """Insert approved bytes at one offset of an unchanged note. Never clobbers.

        The note must still hash to the approved base. A note that already hashes to
        the approved result is the same append done before, so it is not repeated.
        The new content is written beside the note and renamed over it only if the
        note is still the same untouched file at that moment.
        """
        try: fd,name=self._note_directory(path)
        except (OSError,Fault): return 'vault_unavailable'
        try:
            data,info=self._read_note_at(fd,name)
            if data is None: return 'note_unavailable'
            digest=self.digest(path,data)
            if digest==result_sha256: return 'exists_same'
            if digest!=base_sha256: return 'note_changed_since_proposal'
            result=data[:offset]+inserted+data[offset:]
            if not 0<=offset<=len(data) or self.digest(path,result)!=result_sha256: return 'write_failed'
            temporary='.alfred-'+secrets.token_hex(8)+'.tmp'
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,stat.S_IMODE(info.st_mode),dir_fd=fd)
            try:
                view=memoryview(result)
                while view: view=view[os.write(out,view):]
                os.fsync(out)
            finally: os.close(out)
            try:
                # Last check immediately before the rename: the same file, untouched since it was read.
                if self.signature(os.stat(name,dir_fd=fd,follow_symlinks=False))!=self.signature(info):
                    return 'note_changed_since_proposal'
                os.rename(temporary,name,src_dir_fd=fd,dst_dir_fd=fd)
                temporary=None
            finally:
                if temporary: os.unlink(temporary,dir_fd=fd)
            os.fsync(fd)
            return 'appended'
        except OSError:
            return 'write_failed'
        finally: os.close(fd)

    @staticmethod
    def signature(info):
        return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_size,
                info.st_mtime_ns,info.st_ctime_ns)

    def excluded(self,path):
        return any(part.startswith('.') or part in {'node_modules','__pycache__'} for part in path.split('/')) or any(
            path==p or path.startswith(p+'/') for p in self.exclusions)

    def open_root(self):
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
        try:
            for part in self.root.parts[1:]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                os.close(fd);fd=nxt
            return fd
        except BaseException:
            os.close(fd);raise

    def scan(self, *, rebuild=False):
        if self.store.paused(self.principal['scope']): return self.health
        notes,errors=[],[];total=[0,0];observed={};copies=[]
        def walk(fd,prefix='',depth=0):
            directory_before=self.signature(os.fstat(fd))
            entries=os.listdir(fd);total[0]+=len(entries)
            observed[prefix] = directory_before
            if depth>6 or len(entries)>512 or total[0]>4096: raise Fault('vault_directory_capacity')
            for name in sorted(entries):
                path=prefix+name
                if self.excluded(path): continue
                try:
                    safe_path(path)
                    before=os.stat(name,dir_fd=fd,follow_symlinks=False)
                    if stat.S_ISLNK(before.st_mode):
                        errors.append({'path':path,'code':'symlink_excluded'});continue
                    if stat.S_ISDIR(before.st_mode):
                        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                        try:
                            if self.signature(os.fstat(child)) != self.signature(before): raise Fault('vault_changed_during_scan')
                            walk(child,path+'/',depth+1)
                        finally: os.close(child)
                        continue
                    if not name.lower().endswith('.md'): continue
                    copy=sync_conflicts.conflict_copy(path)
                    if copy:
                        # A sync conflict copy is recorded beside its original and never read as a note.
                        if not stat.S_ISREG(before.st_mode): raise Fault('regular_single_link_note_required')
                        observed[path]=self.signature(before);copies.append({'path':path,**copy})
                        errors.append({'path':path,'code':'sync_conflict_copy','original_path':copy['original_path']})
                        continue
                    if len(notes)>=MAX_NOTES: raise Fault('vault_note_capacity')
                    file=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
                    try:
                        opened=os.fstat(file)
                        if self.signature(before)!=self.signature(opened): raise Fault('note_changed_during_read')
                        before=opened
                        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1: raise Fault('regular_single_link_note_required')
                        if before.st_size>MAX_BYTES: raise Fault('note_too_large')
                        raw=b''
                        while len(raw)<=MAX_BYTES:
                            part=os.read(file,min(8192,MAX_BYTES+1-len(raw)))
                            if not part: break
                            raw+=part
                        after=os.fstat(file)
                        if self.signature(before)!=self.signature(after) or len(raw)!=before.st_size:
                            raise Fault('note_changed_during_read')
                        if self.signature(after)!=self.signature(os.stat(name,dir_fd=fd,follow_symlinks=False)):
                            raise Fault('note_changed_during_read')
                        observed[path]=self.signature(after)
                    finally: os.close(file)
                    total[1]+=len(raw)
                    if total[1]>MAX_TOTAL: raise Fault('vault_byte_capacity')
                    note=parse_note(path,raw,self.id_key);note['modified']=max(0,int(before.st_mtime))
                    note['file_identity']=(before.st_dev,before.st_ino)
                    notes.append(note)
                    errors.extend({'path':path,'code':w} for w in note['warnings'])
                except Fault as exc:
                    if exc.code in {'vault_directory_capacity','vault_note_capacity','vault_byte_capacity','vault_changed_during_scan'}: raise
                    errors.append({'path':path,'code':exc.code})
                except OSError: errors.append({'path':path,'code':'note_read_failed'})
            if directory_before!=self.signature(os.fstat(fd)): raise Fault('vault_changed_during_scan')

        def verify(fd,prefix=''):
            if observed.get(prefix)!=self.signature(os.fstat(fd)): raise Fault('vault_changed_during_scan')
            for path,signature in observed.items():
                if path.endswith('/') or '/' in path[len(prefix):] or not path.startswith(prefix): continue
                if path==prefix: continue
                if signature!=self.signature(os.stat(path[len(prefix):],dir_fd=fd,follow_symlinks=False)):
                    raise Fault('vault_changed_during_scan')
            for path in [p for p in observed if p.endswith('/') and p!=prefix and p.startswith(prefix) and '/' not in p[len(prefix):-1]]:
                child=os.open(path[len(prefix):-1],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                try: verify(child,path)
                finally: os.close(child)

        try:
            self.store.principal(self.bearer,{'source'})
            fd=self.open_root()
            try:
                info=os.fstat(fd)
                root_identity=(info.st_dev,info.st_ino)
                self.vault_id=self.store.select_vault(self.bearer,self.label,root_identity,self.configuration)
                self.identity=root_identity
                walk(fd)
                verify(fd)
                check=self.open_root()
                try:
                    current=os.fstat(check)
                    if (current.st_dev,current.st_ino)!=self.identity: raise Fault('vault_root_replaced')
                finally: os.close(check)
            finally: os.close(fd)
            # Copies from tools not recognised by name: identical bytes under an extended name.
            for copy in sync_conflicts.content_copies(notes):
                notes=[n for n in notes if n['path']!=copy['path']]
                errors[:]=[e for e in errors if e.get('path')!=copy['path']]
                copies.append(copy)
                errors.append({'path':copy['path'],'code':'sync_conflict_copy','original_path':copy['original_path'],'detected_by':'content_hash'})
            self.store.replace_notes(self.bearer,self.label,notes,errors,self.vault_id,conflicts=sync_conflicts.scanned(copies,notes,errors),rebuild=rebuild)
            status='attention' if errors else 'ready'
        except (Fault,OSError) as exc:
            code=exc.code if isinstance(exc,Fault) else 'vault_unavailable'
            errors=[{'code':code}];status='unavailable'
            try: self.store.knowledge_unavailable(self.bearer,code)
            except Fault: pass
        self.health={'configured':True,'status':status,'last_scan':self.store.now(),'errors':errors[:32],'notes':len(notes) if status!='unavailable' else 0,'vault_id':self.vault_id}
        return self.health


class KnowledgeSupervisor(Supervisor):
    def __init__(self,store,owner_bearer,source_bearer,root,interval=2.0,vault=None,*,vault_exclusions=(),vault_id_key=None):
        super().__init__(store,owner_bearer,source_bearer,root,interval)
        self.vault=MarkdownVault(store,source_bearer,vault,exclude_folders=vault_exclusions,id_key=vault_id_key) if vault is not None else None

    def cycle(self):
        with self.lock:
            if self.vault and not self.store.paused(self.scope):
                try:
                    self.store.principal(self.owner,{'owner'});self.vault.scan()
                except Exception:
                    self.vault.health={'configured':True,'status':'unavailable','last_scan':self.store.now(),'errors':[{'code':'knowledge_scan_failed'}]}
            super().cycle()
            if not self.store.paused(self.scope):
                try:
                    # Retention the owner chose at capture time; each expiry is a receipted forget.
                    from .reviewed_memory import ReviewedMemory
                    if getattr(self, 'memory', None) is None: self.memory = ReviewedMemory(self.store)
                    self.memory.apply_retention(self.owner)
                    # Ordinary forgets leave the bin once their 30 days pass.
                    self.memory.empty_bin(self.owner)
                except Fault as exc:
                    self.error = exc.code
            if getattr(self, 'capture', None) is not None and not self.store.paused(self.scope):
                try:
                    # Owner-authored capture policies: proposals for review only, never accepted here.
                    self.capture.cycle()
                except Fault as exc:
                    self.error = exc.code
            if getattr(self, 'pulse', None) is not None and not self.store.paused(self.scope):
                try:
                    self.pulse.cycle()
                except Fault as exc:
                    self.error = exc.code
            # Routines record a due slot as skipped while paused, so they are called either way.
            if getattr(self, 'routines', None) is not None:
                try:
                    self.routines.cycle()
                except Exception as exc:
                    # A routine failure is recorded on its run; it never stops the supervisor.
                    self.error = exc.code if isinstance(exc, Fault) else 'routines_failed'
            # Goal heartbeats and budget accounting (AGENT_HUB.md H2): only ALFRED wakes a brain.
            # Called while paused too, so due heartbeats are recorded as skipped.
            if getattr(self, 'goals', None) is not None:
                try:
                    self.goals.cycle()
                except Exception as exc:
                    self.error = exc.code if isinstance(exc, Fault) else 'goals_failed'

    def view(self,scope):
        result=super().view(scope)
        if scope==self.scope: result['knowledge']=dict(self.vault.health) if self.vault else {'configured':False}
        return result
