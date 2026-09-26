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
INSERT INTO knowledge_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM knowledge_meta);
CREATE TABLE IF NOT EXISTS knowledge_sources(
 scope TEXT NOT NULL, source TEXT NOT NULL, label TEXT NOT NULL, checked INTEGER NOT NULL,
 status TEXT NOT NULL, errors TEXT NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(scope,source));
CREATE TABLE IF NOT EXISTS knowledge_notes(
 scope TEXT NOT NULL, source TEXT NOT NULL, id TEXT NOT NULL, path TEXT NOT NULL,
 title TEXT NOT NULL, kind TEXT NOT NULL, tags TEXT NOT NULL, aliases TEXT NOT NULL,
 body TEXT NOT NULL, sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
 modified INTEGER NOT NULL, indexed INTEGER NOT NULL, status TEXT NOT NULL,
 PRIMARY KEY(scope,source,id), UNIQUE(scope,source,path));
CREATE INDEX IF NOT EXISTS knowledge_scope ON knowledge_notes(scope,source,status);
CREATE TABLE IF NOT EXISTS knowledge_refs(
 scope TEXT NOT NULL, source TEXT NOT NULL, origin TEXT NOT NULL, target TEXT NOT NULL,
 line INTEGER NOT NULL, syntax TEXT NOT NULL, relation TEXT NOT NULL);
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


def parse_note(path, raw):
    """Deliberately bounded Markdown subset; not Obsidian's complete parser.

    Flat title/type/kind/tags/aliases frontmatter, ordinary wikilinks and Markdown
    links are recognised. Fenced/inline code and frontmatter are not link evidence.
    Heading/block fragments resolve to the file, not a validated anchor.
    """
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
            if key not in {'title', 'type', 'kind', 'tags', 'aliases'}:
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
    links, fence = [], None
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
        visible = re.sub(r'(`+).*?\1', '', visible)
        for regex, syntax in ((WIKI, 'wiki'), (MARKDOWN, 'markdown')):
            for match in regex.finditer(visible):
                target = match[2].split('|', 1)[0].strip() if syntax == 'wiki' else match[2].strip().strip('<>')
                if len(links) >= 128:
                    raise Fault('note_link_capacity')
                links.append({'target': target, 'line': number, 'syntax': syntax,
                              'relation': 'embeds' if match[1] else 'links_to'})
    return {'path': path, 'title': title, 'kind': kind, 'tags': meta.get('tags', []),
            'aliases': meta.get('aliases', []), 'body': body, 'sha256': hashlib.sha256(raw).hexdigest(),
            'refs': links, 'warnings': sorted(set(warnings))}


def note_id(source, path):
    return hashlib.sha256((source + '\0' + path).encode()).hexdigest()[:24]


def resolve_target(origin, target, syntax, notes):
    """Resolve only within one source. Never dereference a URL or filesystem path."""
    target = unquote(target)
    if any(ord(c) < 32 for c in target) or '\\' in target or target.startswith('/'):
        return None, 'blocked_path'
    try: parsed = urlsplit(target)
    except ValueError: return None, 'malformed_link'
    if parsed.scheme or parsed.netloc:
        return None, 'external' if parsed.scheme in {'http', 'https', 'mailto'} else 'blocked_scheme'
    path = target.split('#', 1)[0]
    if '?' in path:
        return None, 'unsupported_query'
    if not path:
        return origin, 'resolved'
    suffix = PurePosixPath(path).suffix.lower()
    if suffix and suffix != '.md':
        return None, 'attachment_not_indexed'
    if not suffix: path += '.md'
    keys = {}
    for n in notes:
        keys.setdefault(n['path'].casefold(), []).append(n['id'])
    if syntax == 'markdown':
        paths = [posixpath.normpath(posixpath.join(posixpath.dirname(next(n['path'] for n in notes if n['id'] == origin)), path))]
    else:
        paths = [posixpath.normpath(path)]
    if any(p == '..' or p.startswith('../') for p in paths):
        return None, 'blocked_path'
    found = set(v for p in paths for v in keys.get(p.casefold(), []))
    if not found and syntax == 'wiki' and '/' not in path:
        stem = PurePosixPath(path).stem.casefold()
        for n in notes:
            if PurePosixPath(n['path']).stem.casefold() == stem or stem in {a.casefold() for a in n['aliases']}:
                found.add(n['id'])
    return (next(iter(found)), 'resolved') if len(found) == 1 else (None, 'ambiguous' if found else 'missing')


class KnowledgeStore(DeskStore):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        with self.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM knowledge_meta')] != [1]:
                raise Fault('unsupported_knowledge_version')

    def replace_notes(self, bearer, label, notes, errors):
        if len(notes) > MAX_NOTES or sum(len(n['refs']) for n in notes) > MAX_LINKS:
            raise Fault('knowledge_capacity')
        snapshot = hashlib.sha256(json.dumps([(n['path'], n['sha256']) for n in notes], sort_keys=True).encode()).hexdigest()
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'source'}); scope, source = p['scope'], p['id']
            if db.execute('SELECT count(*) FROM knowledge_notes WHERE scope=?', (scope,)).fetchone()[0] + len(notes) > 10000:
                raise Fault('knowledge_history_capacity')
            old = db.execute('SELECT snapshot FROM knowledge_sources WHERE scope=? AND source=?', (scope, source)).fetchone()
            db.execute('UPDATE knowledge_notes SET status=\'missing\',body=\'\',tags=\'[]\',aliases=\'[]\' WHERE scope=? AND source=?', (scope, source))
            db.execute('DELETE FROM knowledge_refs WHERE scope=? AND source=?', (scope, source))
            for n in notes:
                identity = note_id(source, n['path'])
                prior = db.execute('SELECT sha256,revision FROM knowledge_notes WHERE scope=? AND source=? AND id=?', (scope, source, identity)).fetchone()
                revision = prior['revision'] + int(prior['sha256'] != n['sha256']) if prior else 1
                db.execute('INSERT INTO knowledge_notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(scope,source,id) DO UPDATE SET title=excluded.title,kind=excluded.kind,tags=excluded.tags,aliases=excluded.aliases,body=excluded.body,sha256=excluded.sha256,revision=excluded.revision,modified=excluded.modified,indexed=excluded.indexed,status=excluded.status',
                           (scope,source,identity,n['path'],n['title'],n['kind'],json.dumps(n['tags']),json.dumps(n['aliases']),n['body'],n['sha256'],revision,n['modified'],self.now(),'ready'))
                db.executemany('INSERT INTO knowledge_refs VALUES (?,?,?,?,?,?,?)', [(scope,source,identity,r['target'],r['line'],r['syntax'],r['relation']) for r in n['refs']])
            db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope,source) DO UPDATE SET label=excluded.label,checked=excluded.checked,status=excluded.status,errors=excluded.errors,snapshot=excluded.snapshot',
                       (scope,source,label,self.now(),'attention' if errors else 'ready',json.dumps(errors[:32]),snapshot))
            if not old or old['snapshot'] != snapshot:
                self.log(db,scope,source,'knowledge.indexed',snapshot[:16])

    def knowledge_unavailable(self, bearer, code):
        with self.transaction() as db:
            # A revoked source cannot refresh its index. Readers also recheck its grant.
            p = self.authenticate(db, bearer, {'source'})
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
            for n in notes:
                n['tags'], n['aliases'] = json.loads(n['tags']), json.loads(n['aliases'])
            refs = [dict(r) for r in db.execute('SELECT * FROM knowledge_refs WHERE scope=? ORDER BY source,origin,line,target', (scope,)) if r['source'] in permitted]
            if len(refs)>MAX_LINKS:
                raise Fault('knowledge_link_view_capacity',409)
            links, issues = [], []
            groups = {s: [n for n in notes if n['source'] == s] for s in permitted}
            by_id = {n['id']: n for n in notes}
            for r in refs:
                target, state = resolve_target(r['origin'],r['target'],r['syntax'],groups[r['source']])
                original = by_id[r['origin']]
                evidence = {'source':r['origin'],'line':r['line'],'source_sha256':original['sha256'],
                            'source_revision':original['revision'],'relation':r['relation'],'basis':'explicit_note_reference'}
                if state == 'resolved': links.append({**evidence,'target':target})
                elif state not in {'external','attachment_not_indexed'}:
                    issues.append({'note':r['origin'],'path':original['path'],'line':r['line'],'target':r['target'],'status':state})
            terms = query.casefold().split()
            selected = [n for n in notes if (not kind or n['kind']==kind) and all(t in (n['title']+' '+n['path']+' '+n['body']+' '+' '.join(n['tags'])).casefold() for t in terms)]
            def public(n):
                snippet = n['body'].splitlines()
                line = next((i for i,l in enumerate(snippet,1) if terms and any(t in l.casefold() for t in terms)),1)
                excerpt = snippet[line-1][:260] if snippet else ''
                return {k:n[k] for k in ('id','source','path','title','kind','tags','sha256','revision','modified','indexed')} | {'snippet':excerpt,'line':line,'basis':'authored_note_not_verified_fact'}
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
                    'issues':issues, 'sources':[{'source':s['source'],'label':s['label'],'checked':s['checked'],'status':s['status'],'errors':json.loads(s['errors'])} for s in sources],
                    'map_health':{'roots':map_roots,'missing_map_sources':missing_map,'outside_two_hops':[n['id'] for n in notes if distances.get(n['id'],3)>2]},
                    'counts':{'notes':len(notes),'matches':len(selected),'links':len(links),'issues':len(issues)},
                    'live_ai':False,'read_only':True,'content_egress':False,'anchor_validation':False}

    def knowledge_note(self,bearer,identity):
        if not re.fullmatch(r'[0-9a-f]{24}',identity): raise Fault('invalid_note_id')
        with self.connection() as db:
            p=self.authenticate(db,bearer,{'owner','reader'})
            row=db.execute('SELECT n.* FROM knowledge_notes n JOIN credentials c ON c.id=n.source AND c.scope=n.scope JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source WHERE n.scope=? AND n.id=? AND n.status=\'ready\' AND c.revoked=0 AND c.expires>? AND s.status IN (\'ready\',\'attention\')', (p['scope'],identity,self.now())).fetchone()
            if not row: raise Fault('note_not_available',404)
            return {k:row[k] for k in ('id','path','title','kind','body','sha256','revision','modified','indexed')} | {'basis':'authored_note_not_verified_fact'}


class MarkdownVault:
    def __init__(self,store,bearer,root,label='Local Markdown vault'):
        self.store,self.bearer,self.root,self.label=store,bearer,Path(root).absolute(),safe_text(label)
        self.principal=store.principal(bearer,{'source'})
        fd=self.open_root()
        try:
            info=os.fstat(fd);self.identity=(info.st_dev,info.st_ino)
        finally: os.close(fd)
        self.health={'configured':True,'status':'starting','last_scan':None,'errors':[]}

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
        notes,errors=[],[];total=[0,0]
        def walk(fd,prefix='',depth=0):
            entries=os.listdir(fd);total[0]+=len(entries)
            if depth>6 or len(entries)>512 or total[0]>4096: raise Fault('vault_directory_capacity')
            for name in sorted(entries):
                if name.startswith('.') or name in {'node_modules','__pycache__'}: continue
                path=prefix+name
                try:
                    safe_text(path,240)
                    before=os.stat(name,dir_fd=fd,follow_symlinks=False)
                    if stat.S_ISLNK(before.st_mode):
                        errors.append({'path':path,'code':'symlink_excluded'});continue
                    if stat.S_ISDIR(before.st_mode):
                        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                        try: walk(child,path+'/',depth+1)
                        finally: os.close(child)
                        continue
                    if not name.lower().endswith('.md'): continue
                    if len(notes)>=MAX_NOTES: raise Fault('vault_note_capacity')
                    file=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
                    try:
                        before=os.fstat(file)
                        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1: raise Fault('regular_single_link_note_required')
                        if before.st_size>MAX_BYTES: raise Fault('note_too_large')
                        raw=b''
                        while len(raw)<=MAX_BYTES:
                            part=os.read(file,min(8192,MAX_BYTES+1-len(raw)))
                            if not part: break
                            raw+=part
                        after=os.fstat(file)
                        if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns): raise Fault('note_changed_during_read')
                    finally: os.close(file)
                    total[1]+=len(raw)
                    if total[1]>MAX_TOTAL: raise Fault('vault_byte_capacity')
                    note=parse_note(path,raw);note['modified']=max(0,int(before.st_mtime))
                    notes.append(note)
                    errors.extend({'path':path,'code':w} for w in note['warnings'])
                except Fault as exc:
                    if exc.code in {'vault_directory_capacity','vault_note_capacity','vault_byte_capacity'}: raise
                    errors.append({'path':path,'code':exc.code})
                except OSError: errors.append({'path':path,'code':'note_read_failed'})
        try:
            self.store.principal(self.bearer,{'source'})
            fd=self.open_root()
            try:
                info=os.fstat(fd)
                if (info.st_dev,info.st_ino)!=self.identity: raise Fault('vault_root_replaced')
                walk(fd)
            finally: os.close(fd)
            self.store.replace_notes(self.bearer,self.label,notes,errors)
            status='attention' if errors else 'ready'
        except (Fault,OSError) as exc:
            code=exc.code if isinstance(exc,Fault) else 'vault_unavailable'
            errors=[{'code':code}];status='unavailable'
            try: self.store.knowledge_unavailable(self.bearer,code)
            except Fault: pass
        self.health={'configured':True,'status':status,'last_scan':self.store.now(),'errors':errors[:32],'notes':len(notes)}
        return self.health


class KnowledgeSupervisor(Supervisor):
    def __init__(self,store,owner_bearer,source_bearer,root,interval=2.0,vault=None):
        super().__init__(store,owner_bearer,source_bearer,root,interval)
        self.vault=MarkdownVault(store,source_bearer,vault) if vault is not None else None

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
