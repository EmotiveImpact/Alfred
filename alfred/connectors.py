"""Read-only connectors over owner-selected local export files (CON-001, first slice).

A connector reads one file that the owner selected and nothing else: no account,
token, network connection, background polling or device. It can never write, send
or delete anything at the origin; the file is opened read-only and never changed.

Each connector instance is its own source credential and label. A complete export
becomes a complete snapshot of that source through the existing source and
document identity pipeline (KnowledgeStore.replace_notes), so grants, retrieval,
the console projection, revision history and M05 invalidation apply unchanged: a
changed item gets a new revision; an item missing from a later complete export is
marked missing, which invalidates reviewed statements that cite it; an item the
export did not let ALFRED identify is withheld, never treated as deleted.

Importing needs an explicit 'connector.read' grant, which legacy scope policy never
implies; reading what was imported needs the usual 'read' grant, and sending it to
a model needs 'model'. Instances are created and imported only while the host is
stopped (offline administration, like key rotation and restore). Their source keys
live beside the desk keys in the private data directory, outside every vault. No
account token exists; a future one would live there too, never in a vault.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from .local import Fault, exact, ident
from .knowledge import MAX_NOTES, safe_text
from .policy import permitted
from . import ics_export, vcf_export

MAX_INSTANCES, MAX_ITEMS, MAX_RECEIPTS = 8, 200, 50
KEY_TTL, RENEW_BELOW = 2592000, 15 * 86400
KEY_FILE = 'connector-access.json'
KNOWN_SCOPES = frozenset({'calendar.events.read', 'calendar.tasks.read', 'calendar.participants.read',
                          'contacts.read', 'contacts.email.read', 'contacts.telephone.read'})
MANIFEST_KEYS = {'id', 'title', 'scopes', 'default_scopes', 'read_only', 'origin_effects', 'input',
                 'identity', 'revisions', 'freshness', 'credentials', 'capability'}
INPUT_KEYS = {'kind', 'suffixes', 'media_type', 'max_bytes', 'max_items', 'network', 'polling'}
MANIFESTS = (
    {'id': 'ics-export', 'title': 'Calendar export file (iCalendar, RFC 5545)',
     'scopes': ('calendar.events.read', 'calendar.tasks.read', 'calendar.participants.read'),
     'default_scopes': ('calendar.events.read',), 'read_only': True, 'origin_effects': (),
     'input': {'kind': 'owner_selected_local_file', 'suffixes': ('.ics',), 'media_type': 'text/calendar',
               'max_bytes': ics_export.MAX_BYTES, 'max_items': MAX_ITEMS, 'network': False, 'polling': False},
     'identity': 'UID plus RECURRENCE-ID within VEVENT or VTODO; a content hash when the export gives no UID',
     'revisions': 'A new ALFRED revision whenever the imported text changes; SEQUENCE and LAST-MODIFIED must not go backwards',
     'freshness': {'basis': 'snapshot_when_imported', 'stale_after_seconds': 7 * 86400},
     'credentials': 'none', 'capability': 'connector.read'},
    {'id': 'vcf-export', 'title': 'Contacts export file (vCard 4.0, tolerating 3.0)',
     'scopes': ('contacts.read', 'contacts.email.read', 'contacts.telephone.read'),
     'default_scopes': ('contacts.read',), 'read_only': True, 'origin_effects': (),
     'input': {'kind': 'owner_selected_local_file', 'suffixes': ('.vcf', '.vcard'), 'media_type': 'text/vcard',
               'max_bytes': vcf_export.MAX_BYTES, 'max_items': MAX_ITEMS, 'network': False, 'polling': False},
     'identity': 'UID; a content hash when the export gives no UID, so an edited card without a UID reads as removed and added',
     'revisions': 'A new ALFRED revision whenever the imported text changes; REV must not go backwards',
     'freshness': {'basis': 'snapshot_when_imported', 'stale_after_seconds': 7 * 86400},
     'credentials': 'none', 'capability': 'connector.read'},
)
ADAPTERS = {'ics-export': ics_export, 'vcf-export': vcf_export}
PREFIX = {'ics-export': 'ics', 'vcf-export': 'vcf'}
ITEM_SCOPES = {'ics-export': set(ics_export.SCOPES.values()), 'vcf-export': {vcf_export.SCOPE}}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS connector_meta(version INTEGER NOT NULL);
INSERT INTO connector_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM connector_meta);
CREATE TABLE IF NOT EXISTS connector_instances(
 scope TEXT NOT NULL, source TEXT NOT NULL, connector TEXT NOT NULL, label TEXT NOT NULL,
 scopes TEXT NOT NULL, created INTEGER NOT NULL, created_by TEXT NOT NULL,
 imported INTEGER, export_modified INTEGER, PRIMARY KEY(scope,source));
CREATE TABLE IF NOT EXISTS connector_item_revisions(
 scope TEXT NOT NULL, source TEXT NOT NULL, item TEXT NOT NULL, sequence INTEGER, modified INTEGER,
 PRIMARY KEY(scope,source,item));
CREATE TABLE IF NOT EXISTS connector_receipts(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, source TEXT NOT NULL, actor TEXT NOT NULL,
 at INTEGER NOT NULL, outcome TEXT NOT NULL, receipt TEXT NOT NULL);
'''


def validate_manifest(value):
    """The contract: read scopes only, no effect at the origin, a local file the owner chose."""
    exact(value, MANIFEST_KEYS)
    ident(value['id'])
    scopes = value['scopes']
    if (type(scopes) is not tuple or not scopes or len(set(scopes)) != len(scopes)
            or any(type(s) is not str or not s.endswith('.read') or s not in KNOWN_SCOPES for s in scopes)):
        raise Fault('connector_scope_not_read_only')
    if type(value['default_scopes']) is not tuple or not value['default_scopes'] or not set(value['default_scopes']) <= set(scopes):
        raise Fault('invalid_connector_defaults')
    if value['read_only'] is not True or value['origin_effects'] != ():
        raise Fault('connector_must_be_read_only')
    if value['capability'] != 'connector.read' or value['credentials'] != 'none':
        raise Fault('invalid_connector_authority')
    source = value['input']
    exact(source, INPUT_KEYS)
    if source['kind'] != 'owner_selected_local_file' or source['network'] is not False or source['polling'] is not False:
        raise Fault('connector_input_not_local')
    if type(source['max_bytes']) is not int or not 0 < source['max_bytes'] <= 1048576 or source['max_items'] != MAX_ITEMS:
        raise Fault('connector_input_unbounded')
    freshness = value['freshness']
    if type(freshness) is not dict or set(freshness) != {'basis', 'stale_after_seconds'} or not (
            type(freshness['stale_after_seconds']) is int and 3600 <= freshness['stale_after_seconds'] <= KEY_TTL):
        raise Fault('invalid_connector_freshness')
    return value


CONNECTORS = {m['id']: validate_manifest(m) for m in MANIFESTS}


def manifest(connector):
    if connector not in CONNECTORS:
        raise Fault('unknown_connector')
    return CONNECTORS[connector]


def initialise(store):
    with store.connection() as db:
        db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
        if [r[0] for r in db.execute('SELECT version FROM connector_meta')] != [1]:
            raise Fault('unsupported_connector_version')


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_export(path, spec):
    """Open the selected file read-only and bounded. A final symlink, a non-regular
    file and a change during the read all refuse the import."""
    if not isinstance(path, (str, os.PathLike)):
        raise Fault('export_file_required')
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() not in spec['input']['suffixes']:
        raise Fault('export_type_mismatch')
    limit = spec['input']['max_bytes']
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):
            raise Fault('export_symlink_refused')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise Fault('export_unavailable') from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise Fault('regular_export_file_required')
        if before.st_size > limit:
            raise Fault('export_too_large')
        chunks, size = [], 0
        while size <= limit:
            part = os.read(fd, min(65536, limit + 1 - size))
            if not part:
                break
            chunks.append(part)
            size += len(part)
        raw, after = b''.join(chunks), os.fstat(fd)
        if len(raw) > limit:
            raise Fault('export_too_large')
        if _signature(before) != _signature(after) or len(raw) != after.st_size:
            raise Fault('export_changed_during_read')
        try:
            if _signature(os.stat(path, follow_symlinks=False)) != _signature(after):
                raise Fault('export_changed_during_read')
        except OSError:
            raise Fault('export_changed_during_read') from None
    finally:
        os.close(fd)
    return raw, {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'modified': max(0, int(after.st_mtime))}


def _external(source, prefix, identity):
    # Salted by the source ID, so the same UID in two instances never shares an identity.
    digest = hashlib.sha256(json.dumps([source, *identity], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return f'{prefix}-{digest[:32]}'


def _count(table, code):
    table[code] = table.get(code, 0) + 1


def documents(source, connector, parsed, scopes, file_modified):
    """In-scope items as documents for replace_notes. Duplicates are withheld, never chosen between."""
    adapter, prefix = ADAPTERS[connector], PREFIX[connector]
    candidates, withheld, issues = {}, {}, {}
    out_of_scope = unidentified = 0
    for item in parsed['items']:
        if item['scope'] not in scopes:
            out_of_scope += 1
            continue
        found = adapter.key(item)
        if item.get('skip'):
            _count(issues, item['skip'])
            if found is None:
                unidentified += 1
                continue
            document = None
        else:
            document = adapter.render(item, scopes)
        identity = found or ('content', item['component'], hashlib.sha256(document['body'].encode()).hexdigest())
        candidates.setdefault(f"{item['folder']}/{_external(source, prefix, identity)}", []).append((item, document))
    notes, informational = [], []
    for path, group in sorted(candidates.items()):
        if len(group) > 1:
            # Two items claim one identity, readable or not: neither is chosen.
            withheld[path] = 'duplicate_item_identity'
            _count(issues, 'duplicate_item_identity')
            continue
        item, document = group[0]
        if document is None:
            withheld[path] = item['skip']
            continue
        modified = item.get('modified')
        notes.append({'path': path, 'external_id': path.split('/', 1)[1], 'title': document['title'],
                      'kind': document['kind'], 'tags': document['tags'], 'aliases': [], 'body': document['body'],
                      'sha256': hashlib.sha256(document['body'].encode()).hexdigest(), 'refs': [], 'anchors': [],
                      'modified': modified if modified is not None and 0 <= modified <= 2**53 else file_modified,
                      'origin_revision': adapter.origin_revision(item)})
        for code in item['issues']:
            _count(issues, code)
            informational.append({'path': path, 'code': code})
    errors = [{'path': path, 'code': code} for path, code in sorted(withheld.items())] + informational
    if out_of_scope:
        issues['outside_connector_scopes'] = out_of_scope
    return {'notes': notes, 'errors': errors, 'withheld': set(withheld), 'unidentified': unidentified,
            'issues': dict(sorted(issues.items()))}


def _instance(db, scope, source):
    row = db.execute('SELECT * FROM connector_instances WHERE scope=? AND source=?', (scope, source)).fetchone()
    if not row:
        raise Fault('connector_not_found', 404)
    return dict(row)


def _receipt(store, actor, instance, outcome, code, info, counts, issues):
    rid = 'import-' + secrets.token_hex(10)
    value = {'id': rid, 'source': instance['source'], 'connector': instance['connector'], 'outcome': outcome,
             'code': code, 'at': store.now(), 'file': info, 'counts': counts, 'issues': issues,
             'origin_changed': False, 'network': False, 'authority_granted': False}
    with store.transaction() as db:
        scope, source = instance['scope'], instance['source']
        db.execute('INSERT INTO connector_receipts VALUES (?,?,?,?,?,?,?)',
                   (rid, scope, source, actor, store.now(), outcome, json.dumps(value, sort_keys=True)))
        if outcome == 'imported':
            db.execute('UPDATE connector_instances SET imported=?,export_modified=max(coalesce(export_modified,0),?) WHERE scope=? AND source=?',
                       (store.now(), info['modified'], scope, source))
        db.execute('''DELETE FROM connector_receipts WHERE scope=? AND source=? AND id NOT IN
                      (SELECT id FROM connector_receipts WHERE scope=? AND source=? ORDER BY at DESC,rowid DESC LIMIT ?)''',
                   (scope, source, scope, source, MAX_RECEIPTS))
        store.log(db, scope, actor, 'connector.' + outcome, source)
    return value


def run_import(store, owner_bearer, source_bearer, export_path, *, dry_run=False, allow_remove_all=False):
    """Import one complete export as a complete snapshot of its connector source.

    Everything that could refuse is decided before the snapshot is written. A dry run
    reads and compares but changes nothing. Refusals leave a receipt and change nothing else.
    """
    initialise(store)
    owner = store.principal(owner_bearer, {'owner'})
    source = store.principal(source_bearer, {'source'})
    with store.connection() as db:
        if owner['scope'] != source['scope']:
            raise Fault('connector_not_found', 404)
        instance = _instance(db, owner['scope'], source['id'])
    try:
        return _import(store, owner_bearer, source_bearer, instance, export_path, dry_run, allow_remove_all)
    except Fault as exc:
        if not dry_run and exc.status not in (401,):
            _receipt(store, owner['id'], instance, 'refused', exc.code, None, {}, {})
        raise


def _import(store, owner_bearer, source_bearer, instance, export_path, dry_run, allow_remove_all):
    spec, scope, source = manifest(instance['connector']), instance['scope'], instance['source']
    if store.paused(scope):
        raise Fault('workspace_paused', 409)
    with store.connection() as db:
        if not permitted(db, store.authenticate(db, owner_bearer, {'owner'}), source, store.now(), 'connector.read'):
            raise Fault('connector_read_not_granted', 403)
    raw, info = read_export(export_path, spec)
    parsed = ADAPTERS[instance['connector']].parse(raw)
    built = documents(source, instance['connector'], parsed, set(json.loads(instance['scopes'])), info['modified'])
    if len(built['notes']) > MAX_ITEMS:
        raise Fault('connector_item_capacity', 409)
    with store.transaction() as db:
        p = store.authenticate(db, owner_bearer, {'owner'})
        now = store.now()
        if not permitted(db, p, source, now, 'connector.read'):
            raise Fault('connector_read_not_granted', 403)
        current = _instance(db, scope, source)
        # Current means ready or temporarily withheld: either becomes 'missing' if absent now.
        known = {r['external_id']: dict(r) for r in db.execute(
            '''SELECT i.external_id,n.path,n.sha256,n.status FROM knowledge_notes n JOIN knowledge_identity i USING(scope,source,id)
               WHERE n.scope=? AND n.source=? AND n.status IN ('ready','unavailable')''', (scope, source))}
        incoming = {n['external_id']: n for n in built['notes']}
        errors = list(built['errors'])
        if built['unidentified']:
            # An item the export did not let ALFRED identify could be any absent item,
            # so absent items are withheld (unavailable), never treated as deleted.
            held = {path.split('/', 1)[1] for path in built['withheld']}
            errors = [{'path': r['path'], 'code': 'absent_from_incomplete_export'} for key, r in sorted(known.items())
                      if key not in incoming and key not in held] + errors
        held_paths = {e['path'] for e in errors if 'path' in e and e['path'].split('/', 1)[1] not in incoming}
        absent = {k: r['path'] not in held_paths for k, r in known.items() if k not in incoming}
        counts = {'items': len(incoming),
                  'new': sum(k not in known for k in incoming),
                  'changed': sum(k in known and (known[k]['sha256'] != n['sha256'] or known[k]['status'] != 'ready') for k, n in incoming.items()),
                  'unchanged': sum(k in known and known[k]['sha256'] == n['sha256'] and known[k]['status'] == 'ready' for k, n in incoming.items()),
                  'withheld': sum(not removed for removed in absent.values()),
                  'removed': sum(absent.values()),
                  'not_identified': built['unidentified']}
        ready = [k for k, r in known.items() if r['status'] == 'ready']
        if current['export_modified'] is not None and info['modified'] < current['export_modified']:
            raise Fault('export_older_than_last_import', 409)
        for key, note in incoming.items():
            sequence, modified = note['origin_revision']
            old = db.execute('SELECT sequence,modified FROM connector_item_revisions WHERE scope=? AND source=? AND item=?',
                             (scope, source, key)).fetchone()
            if old and ((None not in (sequence, old['sequence']) and sequence < old['sequence'])
                        or (None not in (modified, old['modified']) and modified < old['modified'])):
                raise Fault('export_older_than_last_import', 409)
        if ready and all(absent.get(k) for k in ready) and not allow_remove_all:
            # Every readable item disappearing at once is more often the wrong file than a real deletion.
            raise Fault('export_would_remove_every_current_item', 409)
        others = db.execute("SELECT count(*) FROM knowledge_notes WHERE scope=? AND source!=? AND status='ready'", (scope, source)).fetchone()[0]
        if others + len(incoming) > MAX_NOTES:
            raise Fault('knowledge_view_capacity', 409)
        if not dry_run:
            # Highest origin revision seen per current item, recorded before the snapshot is
            # written, so even an interrupted import still guards against an older export.
            for key, note in incoming.items():
                sequence, modified = note['origin_revision']
                db.execute('''INSERT INTO connector_item_revisions VALUES (?,?,?,?,?) ON CONFLICT(scope,source,item) DO UPDATE SET
                              sequence=max(coalesce(sequence,excluded.sequence),coalesce(excluded.sequence,sequence)),
                              modified=max(coalesce(modified,excluded.modified),coalesce(excluded.modified,modified))''',
                           (scope, source, key, sequence, modified))
            keep = set(incoming) | {k for k, removed in absent.items() if not removed}
            for (item,) in db.execute('SELECT item FROM connector_item_revisions WHERE scope=? AND source=?', (scope, source)).fetchall():
                if item not in keep:
                    db.execute('DELETE FROM connector_item_revisions WHERE scope=? AND source=? AND item=?', (scope, source, item))
    if dry_run:
        return {'outcome': 'dry_run', 'source': source, 'connector': instance['connector'], 'counts': counts,
                'issues': built['issues'], 'file': info, 'changed_anything': False}
    for note in built['notes']:
        note.pop('origin_revision', None)
    store.replace_notes(source_bearer, instance['label'], built['notes'], errors)
    return _receipt(store, p['id'], instance, 'imported', None, info, counts, built['issues'])


def create_instance(store, owner_bearer, connector, label, scopes=None, *, keep=None):
    """A new connector source. Needs explicit grants; grants its creator connector.read and read only.

    keep(source, bearer) stores the new source key; if anything after provisioning
    fails, the key is revoked so a half-made source can never be used.
    """
    spec = manifest(connector)
    try:
        label = safe_text(label.strip(), 80) if isinstance(label, str) and label.strip() else None
    except Fault:
        label = None
    if label is None:
        raise Fault('invalid_connector_label')
    scopes = list(spec['default_scopes'] if scopes is None else scopes)
    if not scopes or any(type(s) is not str or s not in spec['scopes'] for s in scopes) or not set(scopes) & ITEM_SCOPES[connector]:
        raise Fault('invalid_connector_scopes')
    scopes = sorted(set(scopes))
    initialise(store)
    with store.transaction() as db:
        p = store.authenticate(db, owner_bearer, {'owner'})
        policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
        if not policy or not policy['strict']:
            raise Fault('explicit_grants_required', 409)
        labels = [r['label'].casefold() for r in db.execute('SELECT label FROM connector_instances WHERE scope=?', (p['scope'],))]
        if len(labels) >= MAX_INSTANCES:
            raise Fault('connector_capacity', 409)
        if label.casefold() in labels:
            raise Fault('connector_label_in_use', 409)
        simulation = bool(db.execute('SELECT simulation FROM workspaces WHERE id=?', (p['scope'],)).fetchone()[0])
    source = 'connector-' + secrets.token_hex(6)
    bearer = store.provision(p['scope'], source, 'source', ttl=KEY_TTL, simulation=simulation)
    try:
        if keep is not None:
            keep(source, bearer)
        with store.transaction() as db:
            q = store.authenticate(db, owner_bearer, {'owner'})
            db.execute('INSERT INTO connector_instances VALUES (?,?,?,?,?,?,?,NULL,NULL)',
                       (q['scope'], source, connector, label, json.dumps(scopes), store.now(), q['id']))
            # Honest until the first import: the source exists, holds nothing and is not current.
            db.execute('INSERT INTO knowledge_sources VALUES (?,?,?,?,?,?,?)',
                       (q['scope'], source, label, store.now(), 'unavailable', json.dumps([{'code': 'awaiting_first_import'}]), ''))
            store.log(db, q['scope'], q['id'], 'connector.instance_created', source)
        from .policy import IdentityPolicy
        identity = IdentityPolicy(store)
        expires = store.principal(bearer, {'source'})['expires']
        for capability in ('connector.read', 'read'):
            identity.grant(owner_bearer, source, capability, expires, identity.view(owner_bearer)['epoch'])
    except BaseException:
        try:
            store.revoke(source)
            with store.transaction() as db:
                db.execute('DELETE FROM connector_instances WHERE source=?', (source,))
                db.execute('DELETE FROM knowledge_sources WHERE source=?', (source,))
        except Exception:
            pass
        raise
    return {'source': source, 'bearer': bearer, 'connector': connector, 'label': label, 'scopes': scopes,
            'granted_to_you': ['connector.read', 'read'], 'not_granted': ['model', 'inbox.write'], 'key_expires': expires}


def status(store, bearer):
    """Instances, their freshness and last attempt. Readers see only sources they may read."""
    initialise(store)
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        now, listed = store.now(), []
        for row in db.execute('SELECT * FROM connector_instances WHERE scope=? ORDER BY created,source', (p['scope'],)).fetchall():
            credential = db.execute('SELECT revoked,expires FROM credentials WHERE id=?', (row['source'],)).fetchone()
            active = bool(credential and not credential['revoked'] and credential['expires'] > now)
            readable = active and permitted(db, p, row['source'], now, 'read')
            if p['role'] != 'owner' and not readable:
                # Unknown and unauthorised instances look the same to a reader.
                continue
            spec = CONNECTORS[row['connector']]
            last = db.execute('SELECT receipt FROM connector_receipts WHERE scope=? AND source=? ORDER BY at DESC,rowid DESC LIMIT 1',
                              (p['scope'], row['source'])).fetchone()
            last = json.loads(last['receipt']) if last else None
            age = now - row['imported'] if row['imported'] is not None else None
            state = ('source_unavailable' if not active else 'never_imported' if age is None
                     else 'stale_snapshot' if age > spec['freshness']['stale_after_seconds'] else 'current_snapshot')
            listed.append({
                'source': row['source'], 'label': row['label'], 'connector': row['connector'], 'title': spec['title'],
                'scopes': json.loads(row['scopes']), 'read_only': True, 'credential_active': active,
                'key_expires': credential['expires'] if credential else None,
                'freshness': {'state': state, 'imported_at': row['imported'], 'export_file_modified_at': row['export_modified'],
                              'age_seconds': age, 'stale_after_seconds': spec['freshness']['stale_after_seconds'],
                              'basis': 'snapshot_of_an_owner_selected_export', 'origin_may_have_changed_since': True},
                'items': db.execute("SELECT count(*) FROM knowledge_notes WHERE scope=? AND source=? AND status='ready'",
                                    (p['scope'], row['source'])).fetchone()[0] if readable else None,
                'last_attempt': ({k: last[k] for k in ('at', 'outcome', 'code')} | ({'counts': last['counts'], 'issues': last['issues']} if readable else {}))
                                if last else None,
                'permitted': {cap: active and permitted(db, p, row['source'], now, cap) for cap in ('read', 'model', 'connector.read')}})
    return {'connectors': listed, 'available': [dict(m) for m in MANIFESTS], 'read_only': True, 'network': False,
            'background_polling': False, 'origin_effects': [], 'authority_granted': False}


@contextmanager
def offline(path, *, blocked_code='stop_alfred_before_connector_changes'):
    """Offline administration runs only while the desk host is stopped."""
    import fcntl
    fd = os.open(path / 'desk.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Fault(blocked_code, 409) from None
        yield
    finally:
        os.close(fd)


def load_connector_keys(path):
    """{source: [current key, previous key...]} from a private file beside the desk keys."""
    try:
        fd = os.open(path / KEY_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536 or stat.S_IMODE(info.st_mode) & 0o077:
            raise Fault('private_connector_access_file_required')
        raw = os.read(fd, 65537)
    finally:
        os.close(fd)
    try:
        value = json.loads(raw)
    except ValueError:
        raise Fault('invalid_connector_access_file') from None
    if (type(value) is not dict or set(value) != {'version', 'keys'} or value['version'] != 1 or type(value['keys']) is not dict
            or any(type(k) is not list or not 1 <= len(k) <= 3 or any(type(b) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}', b) for b in k)
                   for k in value['keys'].values())):
        raise Fault('invalid_connector_access_file')
    for source in value['keys']:
        ident(source)
    return value['keys']


def save_connector_keys(path, keys):
    """Stage, fsync, then atomically replace, so a failure never loses a working key."""
    staging = path / (KEY_FILE + '.staging')
    staging.unlink(missing_ok=True)
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'version': 1, 'keys': keys}, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staging, path / KEY_FILE)


def import_with_keys(path, store, owner_bearer, source, export_file, **options):
    ident(source)
    stored = load_connector_keys(path)
    bearer = None
    for candidate in stored.get(source, []):
        try:
            if store.principal(candidate, {'source'})['id'] == source:
                bearer = candidate
                break
        except Fault:
            continue
    if bearer is None:
        raise Fault('connector_not_found' if source not in stored else 'connector_key_not_valid', 404 if source not in stored else 401)
    result = run_import(store, owner_bearer, bearer, export_file, **options)
    if result['outcome'] == 'imported':
        result['key_renewed'] = renew_key(path, store, stored, source, bearer)
    return result


def renew_key(path, store, stored, source, bearer):
    """Keep a used instance alive. The new key is on disk before the database changes, and
    the previous key is kept so a backup restored from before this renewal still works."""
    from .policy import IdentityPolicy
    p = store.principal(bearer, {'source'})
    if p['expires'] - store.now() > RENEW_BELOW:
        return False
    replacement = secrets.token_urlsafe(32)
    save_connector_keys(path, stored | {source: [replacement, bearer] + [k for k in stored[source] if k != bearer][:1]})
    IdentityPolicy(store).rotate(bearer, p['generation'], ttl=KEY_TTL, replacement=replacement)
    return True


def _when(seconds):
    import datetime as dt
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if seconds is not None else 'never'


def command(path, args):
    """Terminal output for: python3 -m alfred.desk connector-add | connector-import | connectors."""
    from .desk import load_keys
    from .knowledge import KnowledgeStore
    if args.command == 'connectors':
        view = status(KnowledgeStore(path / 'desk.sqlite'), load_keys(path)['owner'])
        lines = [f"{c['source']}  {c['label']}  [{c['connector']}]  {c['freshness']['state'].replace('_', ' ')}; "
                 f"imported {_when(c['freshness']['imported_at'])}; items {c['items'] if c['items'] is not None else 'not readable by you'}"
                 for c in view['connectors']]
        return lines or ['No connector sources. Create one with connector-add.']
    with offline(path):
        keys, store = load_keys(path), KnowledgeStore(path / 'desk.sqlite')
        if args.command == 'connector-add':
            if not args.connector or not args.connector_label:
                raise Fault('connector_and_label_required')
            stored = load_connector_keys(path)
            made = create_instance(store, keys['owner'], args.connector, args.connector_label, args.connector_scope or None,
                                   keep=lambda source, bearer: save_connector_keys(path, stored | {source: [bearer]}))
            return [f"Created read-only connector source {made['source']} ({made['label']}), scopes: {', '.join(made['scopes'])}.",
                    'Granted to you: connector.read and read. Not granted: model and inbox.write.',
                    f"Next: python3 -m alfred.desk connector-import --connector-source {made['source']} --export-file <your export>"]
        if not args.connector_source or not args.export_file:
            raise Fault('connector_source_and_export_file_required')
        result = import_with_keys(path, store, keys['owner'], args.connector_source, args.export_file,
                                  dry_run=args.dry_run, allow_remove_all=args.allow_remove_all)
        counts = ', '.join(f'{k.replace("_", " ")} {v}' for k, v in result['counts'].items())
        issues = ', '.join(f'{k} {v}' for k, v in result['issues'].items()) or 'none'
        head = 'Dry run, nothing changed' if result['outcome'] == 'dry_run' else 'Imported'
        return [f'{head}: {counts}.', f'Issues: {issues}.',
                'The export file was only read. Nothing was written, sent or deleted at its origin.']
