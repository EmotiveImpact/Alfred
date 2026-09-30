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
from .local import Fault
from .desk_store import DeskStore
from .desk_runtime import Supervisor

KINDS = ('map', 'project', 'person', 'decision', 'procedure', 'note')
MAX_NOTES, MAX_BYTES, MAX_TOTAL, MAX_LINKS = 256, 65536, 4194304, 8192
WIKI = re.compile(r'(!?)\[\[([^\]\n]{1,400})\]\]')
MARKDOWN = re.compile(r'(!?)\[[^\]\n]{0,160}\]\(([^\)\n]{1,400})\)')
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
    """Deliberately bounded Markdown subset; not Obsidian's complete parser.

    Flat title/type/kind/tags/aliases frontmatter, ordinary wikilinks and Markdown
    links are recognised. Fenced/inline code and frontmatter are not link evidence.
    ATX headings and single-line trailing block IDs have validated line spans.
    Other anchor forms are explicitly unsupported. No Markdown rendering occurs.
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
    links, anchors, fence = [], [], None
    comment = False
    for number, line in enumerate(lines[start:], start + 1):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match[1]
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence or line.startswith('    ') or line.startswith('\t'):
            continue
        # Strip HTML comments, including multi-line comments, without rendering HTML.
        visible = ''; rest = line
        while rest:
            delimiter = '-->' if comment else '<!--'
            at = rest.find(delimiter)
            if at < 0:
                if not comment: visible += rest
                break
            if not comment: visible += rest[:at]
            rest = rest[at + len(delimiter):]; comment = not comment
        heading = re.fullmatch(r'\s{0,3}(#{1,6})\s+(.+?)\s*', visible)
        if heading:
            name = re.sub(r'\s+#+\s*$', '', heading[2]).strip()
            # Rich inline markup and nested-heading subpaths are outside M01.
            if not any(c in name for c in '`*[]<>#'):
                anchors.append({'kind':'heading','name':name,'start_line':number,
                                'end_line':number,'level':len(heading[1])})
        block = re.fullmatch(r'(.+\S)\s+\^([A-Za-z0-9-]+)\s*', visible)
        if block and not heading:
            anchors.append({'kind':'block','name':block[2],'start_line':number,'end_line':number})
        visible = re.sub(r'(`+).*?\1', '', visible)
        for regex, syntax in ((WIKI, 'wiki'), (MARKDOWN, 'markdown')):
            for match in regex.finditer(visible):
                target = match[2].split('|', 1)[0].strip() if syntax == 'wiki' else match[2].strip().strip('<>')
                if len(links) >= 128:
                    raise Fault('note_link_capacity')
                links.append({'target': target, 'line': number, 'syntax': syntax,
                              'relation': 'embeds' if match[1] else 'links_to'})
    if fence is not None: raise Fault('unclosed_code_fence')
    if comment: raise Fault('unclosed_html_comment')
    if len(anchors) > 1024: raise Fault('note_anchor_capacity')
    headings = [a for a in anchors if a['kind'] == 'heading']
    for i, anchor in enumerate(headings):
        anchor['end_line'] = next((a['start_line'] - 1 for a in headings[i+1:]
                                   if a['level'] <= anchor['level']), len(lines))
    return {'path': path, 'title': title, 'kind': kind, 'tags': meta.get('tags', []),
            'aliases': meta.get('aliases', []), 'body': body, 'sha256': hashlib.sha256(raw).hexdigest(),
            'refs': links, 'anchors':anchors, 'external_id':external_id,
            'warnings': sorted(set(warnings))}


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
        return None, 'attachment_not_indexed', None
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
    if len(found) != 1: return None, 'ambiguous' if found else 'missing', None
    identity = next(iter(found))
    if fragment is None: return identity, 'resolved', None
    if not fragment or '#' in fragment or any(c in fragment for c in '[]<>`*'):
        return None, 'unsupported_anchor', None
    kind, name = ('block', fragment[1:]) if fragment.startswith('^') else ('heading', fragment)
    if kind == 'block' and not re.fullmatch(r'[A-Za-z0-9-]+', name):
        return None, 'unsupported_anchor', None
    note = next((n for n in notes if n['id'] == identity), None)
    anchors = [a for a in (note or {}).get('anchors', []) if a['kind'] == kind and
               (a['name'] == name if kind == 'block' else a['name'].casefold() == name.casefold())]
    if len(anchors) != 1: return None, 'ambiguous_anchor' if anchors else 'missing_anchor', None
    return identity, 'resolved', {k:anchors[0][k] for k in ('kind','name','start_line','end_line')}


def resolve_target(origin, target, syntax, notes):
    identity, state, _ = resolve_reference(origin, target, syntax, notes)
    return identity, state


class KnowledgeStore(DeskStore):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
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
            old = db.execute('SELECT * FROM knowledge_vaults WHERE scope=? AND source=?', key).fetchone()
            config = json.dumps(configuration, sort_keys=True)
            if old:
                if old['configuration'] != config: raise Fault('vault_selection_changed')
                if root_identity and old['device'] is not None and root_identity != (old['device'], old['inode']):
                    raise Fault('vault_root_replaced')
                vault_id = old['vault_id']
                if root_identity and old['device'] is None:
                    db.execute('UPDATE knowledge_vaults SET device=?,inode=? WHERE scope=? AND source=?', (*root_identity,*key))
            else:
                vault_id = secrets.token_hex(12)
                db.execute('INSERT INTO knowledge_vaults VALUES (?,?,?,?,?,?,?)',
                           (*key,vault_id,*(root_identity or (None,None)),config,0))
            db.execute("INSERT OR IGNORE INTO knowledge_sources VALUES (?,?,?,?,?,?,?)",
                       (*key,label,self.now(),'unavailable','[]',''))
            return vault_id

    def evidence_valid(self, db, row):
        if super().evidence_valid(db, row):
            return True
        from .conversation import knowledge_action_current
        return knowledge_action_current(self, db, row)

    def replace_notes(self, bearer, label, notes, errors, vault_id=None):
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
        notes = sorted(notes, key=lambda n:n['path'])
        snapshot = hashlib.sha256(json.dumps([(n['path'],n['sha256']) for n in notes], sort_keys=True).encode()).hexdigest()
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'source'}); scope, source = p['scope'], p['id']
            selection = db.execute('SELECT vault_id FROM knowledge_vaults WHERE scope=? AND source=?', (scope,source)).fetchone()
            if selection and vault_id != selection['vault_id']: raise Fault('vault_selection_required')
            old_source = db.execute('SELECT * FROM knowledge_sources WHERE scope=? AND source=?', (scope,source)).fetchone()
            prior = [dict(r) for r in db.execute('SELECT n.*,i.external_id,i.device,i.inode FROM knowledge_notes n LEFT JOIN knowledge_identity i USING(scope,source,id) WHERE n.scope=? AND n.source=?', (scope,source))]
            # Rebuild removed projections from the durable catalogue, not filenames.
            present = {r['id'] for r in prior}
            for h in db.execute('SELECT h.*,i.external_id,i.device,i.inode FROM knowledge_history h LEFT JOIN knowledge_identity i USING(scope,source,id) WHERE h.scope=? AND h.source=? AND h.revision=(SELECT max(x.revision) FROM knowledge_history x WHERE x.scope=h.scope AND x.source=h.source AND x.id=h.id)', (scope,source)):
                if h['id'] not in present: prior.append(dict(h) | {'indexed':h['recorded']})
            # Seed the migration journal without altering old evidence IDs or revisions.
            for row in prior:
                db.execute('INSERT OR IGNORE INTO knowledge_history VALUES (?,?,?,?,?,?,?,?)',
                           (scope,source,row['id'],row['revision'],row['path'],row['sha256'],row['status'],row['indexed']))
            assigned, used = [], set()
            for n in notes:
                external, file_key = n.get('external_id'), n.get('file_identity')
                at_path = [r for r in prior if r['path']==n['path'] and r['status'] in {'ready','unavailable'}]
                by_external = [r for r in prior if external is not None and r['external_id']==external]
                if by_external:
                    row = by_external[0]
                    if row['path'] != n['path'] and row['path'].casefold() in paths:
                        raise Fault('stable_note_id_rebound')
                    if at_path and at_path[0]['id'] != row['id']: raise Fault('stable_note_id_rebound')
                elif at_path:
                    row = at_path[0]
                    if row['external_id'] != external and row['external_id'] is not None:
                        raise Fault('stable_note_id_changed')
                else:
                    candidates = [r for r in prior if file_key and (r['device'],r['inode'])==tuple(file_key)
                                  and r['status']=='ready' and r['path'].casefold() not in paths
                                  and r['sha256']==n['sha256'] and r['external_id']==external]
                    row = candidates[0] if len(candidates)==1 else None
                    # Content/name equality without filesystem or adopted-ID proof is insufficient.
                    if row is None and any((r['sha256']==n['sha256'] or (file_key and (r['device'],r['inode'])==tuple(file_key)))
                                           and r['path'].casefold() not in paths and r['status']=='ready' for r in prior):
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
            db.execute('DELETE FROM knowledge_refs WHERE scope=? AND source=?', (scope,source))
            db.execute('DELETE FROM knowledge_anchors WHERE scope=? AND source=?', (scope,source))
            for row in prior:
                if row['id'] in used: continue
                failed = any(e.get('path')==row['path'] or row['path'].startswith(e.get('path','')+'/') for e in errors if e.get('path'))
                state = 'unavailable' if failed else 'missing'
                revision = row['revision'] + int(row['status']!=state)
                db.execute("UPDATE knowledge_notes SET status=?,revision=?,body='',tags='[]',aliases='[]' WHERE scope=? AND source=? AND id=?",
                           (state,revision,scope,source,row['id']))
                db.execute('INSERT OR IGNORE INTO knowledge_history VALUES (?,?,?,?,?,?,?,?)',
                           (scope,source,row['id'],revision,row['path'],row['sha256'],state,self.now()))
            for n,identity,revision in assigned:
                db.execute('INSERT INTO knowledge_notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(scope,source,id) DO UPDATE SET path=excluded.path,title=excluded.title,kind=excluded.kind,tags=excluded.tags,aliases=excluded.aliases,body=excluded.body,sha256=excluded.sha256,revision=excluded.revision,modified=excluded.modified,indexed=excluded.indexed,status=excluded.status',
                           (scope,source,identity,n['path'],n['title'],n['kind'],json.dumps(n['tags']),json.dumps(n['aliases']),n['body'],n['sha256'],revision,n['modified'],self.now(),'ready'))
                db.execute('INSERT INTO knowledge_identity VALUES (?,?,?,?,?,?) ON CONFLICT(scope,source,id) DO UPDATE SET external_id=excluded.external_id,device=excluded.device,inode=excluded.inode',
                           (scope,source,identity,n.get('external_id'),*n.get('file_identity',(None,None))))
                db.execute('INSERT OR IGNORE INTO knowledge_history VALUES (?,?,?,?,?,?,?,?)',
                           (scope,source,identity,revision,n['path'],n['sha256'],'ready',self.now()))
                db.execute('INSERT INTO knowledge_anchors VALUES (?,?,?,?)', (scope,source,identity,json.dumps(n.get('anchors',[]))))
                db.executemany('INSERT INTO knowledge_refs VALUES (?,?,?,?,?,?,?)', [(scope,source,identity,r['target'],r['line'],r['syntax'],r['relation']) for r in n['refs']])
            db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope,source) DO UPDATE SET label=excluded.label,checked=excluded.checked,status=excluded.status,errors=excluded.errors,snapshot=excluded.snapshot',
                       (scope,source,label,self.now(),'attention' if errors else 'ready',json.dumps(errors[:32]),snapshot))
            if db.execute('SELECT count(*) FROM knowledge_notes WHERE scope=?', (scope,)).fetchone()[0] > 10000 or db.execute('SELECT count(*) FROM knowledge_history WHERE scope=?', (scope,)).fetchone()[0] > 10000:
                raise Fault('knowledge_history_capacity')
            if selection:
                db.execute('UPDATE knowledge_vaults SET confirmed=? WHERE scope=? AND source=?', (self.now(),scope,source))
            if not old_source or old_source['snapshot'] != snapshot:
                self.log(db,scope,source,'knowledge.indexed',snapshot[:16])

    def knowledge_unavailable(self, bearer, code):
        with self.transaction() as db:
            # A revoked source cannot refresh its index. Readers also recheck its grant.
            p = self.authenticate(db, bearer, {'source'})
            db.execute('INSERT OR IGNORE INTO knowledge_sources VALUES (?,?,?,?,?,?,?)', (p['scope'],p['id'],'Selected Markdown vault',self.now(),'unavailable','[]',''))
            db.execute('UPDATE knowledge_sources SET status=\'unavailable\',errors=?,checked=? WHERE scope=? AND source=?',
                       (json.dumps([{'code':code}]),self.now(),p['scope'],p['id']))

    def knowledge(self, bearer, query='', kind=''):
        safe_text(query, 160)
        if kind and kind not in KINDS: raise Fault('invalid_note_kind')
        with self.transaction() as db:
            p = self.authenticate(db,bearer,{'owner','reader'}); scope = p['scope']
            sources = [dict(r) for r in db.execute('SELECT s.* FROM knowledge_sources s JOIN credentials c ON c.id=s.source AND c.scope=s.scope WHERE s.scope=? AND c.revoked=0 AND c.expires>?', (scope,self.now()))]
            permitted = {s['source'] for s in sources if s['status'] in {'ready','attention'}}
            notes = [dict(r) for r in db.execute('SELECT * FROM knowledge_notes WHERE scope=? AND status=\'ready\' ORDER BY path COLLATE NOCASE,id', (scope,)) if r['source'] in permitted]
            if len(notes)>MAX_NOTES:
                raise Fault('knowledge_view_capacity',409)
            anchors = {(r['source'],r['id']):json.loads(r['anchors']) for r in db.execute('SELECT * FROM knowledge_anchors WHERE scope=?', (scope,)) if r['source'] in permitted}
            selections = {r['source']:dict(r) for r in db.execute('SELECT source,vault_id,confirmed FROM knowledge_vaults WHERE scope=?', (scope,))}
            vaults = {source:r['vault_id'] for source,r in selections.items()}
            for n in notes:
                n['anchors'] = anchors.get((n['source'],n['id']),[])
                n['tags'], n['aliases'] = json.loads(n['tags']), json.loads(n['aliases'])
            refs = [dict(r) for r in db.execute('SELECT * FROM knowledge_refs WHERE scope=? ORDER BY source,origin,line,target', (scope,)) if r['source'] in permitted]
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
            missing_map = sorted(s for s in permitted if not any(n['source']==s and n['path'].casefold()=='map.md' for n in notes))
            return {'scope':scope,'query':query,'kind':kind,'now':self.now(),'paused':self.paused(scope),
                    'nodes':[public(n) for n in notes], 'results':[public(n) for n in selected], 'links':links,
                    'issues':issues, 'sources':[{'source':s['source'],'vault_id':vaults.get(s['source']),'label':s['label'],'last_complete_scan':selections.get(s['source'],{}).get('confirmed'),'last_confirmed_snapshot':s['snapshot'],'checked':s['checked'],'status':s['status'],'errors':json.loads(s['errors'])} for s in sources],
                    'map_health':{'roots':map_roots,'missing_map_sources':missing_map,'outside_two_hops':[n['id'] for n in notes if distances.get(n['id'],3)>2]},
                    'counts':{'notes':len(notes),'matches':len(selected),'links':len(links),'issues':len(issues)},
                    'live_ai':False,'read_only':True,'content_egress':False,'anchor_validation':True,'anchor_support':'ATX plain-text headings and single-line trailing block IDs'}

    def knowledge_note(self,bearer,identity):
        if not re.fullmatch(r'[0-9a-f]{24}',identity): raise Fault('invalid_note_id')
        with self.connection() as db:
            p=self.authenticate(db,bearer,{'owner','reader'})
            row=db.execute('SELECT n.* FROM knowledge_notes n JOIN credentials c ON c.id=n.source AND c.scope=n.scope JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source WHERE n.scope=? AND n.id=? AND n.status=\'ready\' AND c.revoked=0 AND c.expires>? AND s.status IN (\'ready\',\'attention\')', (p['scope'],identity,self.now())).fetchone()
            if not row: raise Fault('note_not_available',404)
            return {k:row[k] for k in ('id','path','title','kind','body','sha256','revision','modified','indexed')} | {'basis':'authored_note_not_verified_fact'}


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

    def scan(self):
        if self.store.paused(self.principal['scope']): return self.health
        notes,errors=[],[];total=[0,0];observed={}
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
            self.store.replace_notes(self.bearer,self.label,notes,errors,self.vault_id)
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
            if getattr(self, 'pulse', None) is not None and not self.store.paused(self.scope):
                try:
                    self.pulse.cycle()
                except Fault as exc:
                    self.error = exc.code

    def view(self,scope):
        result=super().view(scope)
        if scope==self.scope: result['knowledge']=dict(self.vault.health) if self.vault else {'configured':False}
        return result
