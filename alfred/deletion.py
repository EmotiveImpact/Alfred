"""Deletion accounting (MEM-010, M05): what ALFRED still holds about a subject, and where.

One scan, used three ways, so that they cannot disagree:

  forget receipts  scan before and after the forget; the receipt counts every dependent
                   found, what the forget removed or cleared, and what remains
  restore          the same accounting for each removal the journal applies again
  deletion report  a read-only scan at any time, for a source, an entity (a statement
                   subject) or one reviewed statement

A subject's dependents are found through current links (a statement cites a note, an
answer cites a statement, a draft was proposed from an answer, a job read a note) and
through the identifiers earlier receipts recorded, because forgetting deliberately
breaks some of those links: a withdrawn answer keeps its question but loses the packet
that named the statement. Receipts record identifiers, never values.

Each category reports `count` (rows or files that still name the subject) and
`holding_value` (how many of those still hold content, a name or text, rather than only
identifiers, states, times and hashes). Value-free rows are kept on forget by default
(decision 0.3) and can be purged explicitly. Nothing here is secure erasure: SQLite free
pages, the WAL, older backups and filesystem snapshots are outside any count.

Read-only. Exports and backups on disk are counted and listed, never deleted: ALFRED
does not delete folders the person chose.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from . import sealing
from .local import Fault, ident

KINDS = ('source', 'entity', 'statement')
EXPORTS_SUFFIX = '.exports.jsonl'
TRACE = ('claims', 'notes', 'events', 'turns', 'actions', 'artefacts', 'jobs')
REMOVED = 'Removed when its source was forgotten.'
SHA256 = re.compile(r'[0-9a-f]{64}')
INDEX_TABLES = ('knowledge_notes', 'knowledge_history', 'knowledge_refs', 'knowledge_identity',
                'knowledge_anchors', 'knowledge_vaults', 'knowledge_sources', 'knowledge_conflicts')
CONNECTOR_TABLES = ('connector_instances', 'connector_item_revisions', 'connector_receipts')
CATEGORIES = {
    'statements': 'Reviewed statements (memory_claims). A value is held until the statement is forgotten or invalidated.',
    'entity_name': 'The entity record and its name (memory_entities).',
    'captures': 'Capture settings for those statements (memory_capture): memory type and retention, no value.',
    'bin_copies': 'Copies an ordinary forget keeps in the bin for 30 days so it can be undone, with the value. '
                  'An absolute forget removes them.',
    'source_index': 'Index rows built from the source: note text, paths, links, anchors, identities and the vault binding.',
    'tombstones': 'Tombstones that stop a removed note coming back: note identifier and a hash of its path.',
    'evidence_events': 'Desk events, documents and links from the source; text is replaced when the source is removed.',
    'connector_records': 'Connector settings, item revisions and import receipts for the source.',
    'answers': 'Saved conversation answers that cited the subject. A withdrawn answer keeps the question you typed.',
    'voice_playbacks': 'Spoken playback records for those answers: a text hash and character count only.',
    'drafts': 'Approval-ledger actions bound to the subject, in any state, and how many still hold draft text.',
    'routine_nominations': 'Routine reminders and draft offers that cited a statement: identifiers and a fixed reason.',
    'executive_citations': 'Your executive records that cite a note from the source: your own text, a line reference and a hash.',
    'job_artefacts': 'Job results computed from the source (artefacts).',
    'jobs': 'Job records that read the source: identifiers, revisions and hashes.',
    'cache_copies': 'Copies of those job results in the local job cache.',
    'history_rows': 'Review history rows: identifiers, states and times, never a value.',
    'audit_rows': 'Audit entries that name the subject or its statements by identifier.',
    'lifecycle_receipts': 'Forget receipts for the subject: counts and identifiers.',
    'exports_on_disk': 'Portable exports ALFRED wrote that included the subject and are still on disk.',
    'backups': 'Backups on disk taken before the latest forget of the subject (or any backup, if never forgotten). '
               'A restore brings an ordinary forget back and applies an absolute one again.',
}
VALUE_FREE = ('captures', 'tombstones', 'voice_playbacks', 'routine_nominations', 'executive_citations', 'jobs',
              'history_rows', 'audit_rows', 'lifecycle_receipts')
NOT_COUNTED = ['SQLite free pages and WAL contents until checkpoint and vacuum.',
               'Filesystem snapshots, sync copies and anything copied out of ALFRED by hand.',
               'Your own files: ALFRED never deletes the notes or files a source read.']


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def exports_path(database) -> Path:
    database = Path(database)
    return database.with_name(database.name + EXPORTS_SUFFIX)


def register_export(database, entry: dict) -> None:
    """Append one line for an export ALFRED wrote. Beside the database, outside it, so a
    restore of an older backup still knows the export exists."""
    line = (json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(exports_path(database), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def exports(database) -> list[dict]:
    path = exports_path(database)
    if not path.exists() or path.is_symlink():
        return []
    found = []
    for line in path.read_text().splitlines():
        value = _json(line)
        if isinstance(value, dict) and isinstance(value.get('export_id'), str):
            found.append(value)
    return found


def _on_disk(entry) -> bool:
    try:
        manifest = Path(entry['directory']) / 'manifest.json'
        return (not manifest.is_symlink() and manifest.is_file()
                and json.loads(manifest.read_text()).get('export_id') == entry['export_id'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _in(ids):
    return ','.join('?' * len(ids))


def _rows(db, sql, ids, *args):
    """SELECT ... WHERE column IN ids, in chunks below SQLite's variable limit."""
    ids, result = sorted(ids), []
    for start in range(0, len(ids), 400):
        chunk = ids[start:start + 400]
        result += db.execute(sql.format(ids=_in(chunk)), (*args, *chunk)).fetchall()
    return result


def _keys(db, actor):
    """Every actor value naming this person's review ledger (per person since strict grants)."""
    if not _has(db, 'identity_devices'):
        return [actor]
    from .policy import ledger_keys
    return ledger_keys(db, actor)


def _linked(db, scope, actor, kind, subject, trace):
    """Every identifier that ties a row to the subject, from current links and earlier receipts."""
    t = {k: set(trace.get(k, ())) for k in TRACE}
    private = kind != 'source'
    keys = _keys(db, actor)
    mine = f"actor IN ({','.join('?' * len(keys))})"
    if kind == 'statement':
        t['claims'].add(subject)
    elif kind == 'entity' and _has(db, 'memory_claims'):
        t['claims'] |= {r[0] for r in db.execute(f'SELECT id FROM memory_claims WHERE scope=? AND {mine} AND (subject_id=? OR object_id=?)',
                                                 (scope, *keys, subject, subject))}
    elif kind == 'source':
        for table in ('knowledge_notes', 'knowledge_history', 'knowledge_identity', 'memory_tombstones'):
            column = 'note_id' if table == 'memory_tombstones' else 'id'
            if _has(db, table):
                t['notes'] |= {r[0] for r in db.execute(f'SELECT {column} FROM {table} WHERE scope=? AND source=?', (scope, subject))}
        if t['notes'] and _has(db, 'memory_claims'):
            t['claims'] |= {r[0] for r in _rows(db, 'SELECT id FROM memory_claims WHERE scope=? AND note_id IN ({ids})', t['notes'], scope)}
        if _has(db, 'events'):
            t['events'] |= {r[0] for r in db.execute('SELECT seq FROM events WHERE scope=? AND source=?', (scope, subject))}
        if _has(db, 'artefacts'):
            for row in db.execute('SELECT sha256,job_id,lineage FROM artefacts WHERE scope=?', (scope,)):
                if subject in ((_json(row['lineage']) or {}).get('sources') or []):
                    t['artefacts'].add(row['sha256']); t['jobs'].add(row['job_id'])
        if _has(db, 'jobs'):
            for row in db.execute('SELECT id,inputs FROM jobs WHERE scope=?', (scope,)):
                for item in _json(row['inputs']) or []:
                    if isinstance(item, dict) and (item.get('source') == subject or subject in (item.get('sources') or [])):
                        t['jobs'].add(row['id'])
    if private and t['claims'] and _has(db, 'memory_claims'):
        # Statements are private to the person who reviewed them.
        t['claims'] = {r[0] for r in _rows(db, f'SELECT id FROM memory_claims WHERE scope=? AND {mine} AND id IN ({{ids}})', t['claims'], scope, *keys)}
    if kind != 'statement' and t['claims'] and _has(db, 'lifecycle_receipts'):
        # A statement forgotten on its own earlier unlinked its answers and drafts; its receipt still names them.
        for row in _rows(db, "SELECT receipt FROM lifecycle_receipts WHERE scope=? AND kind='claim_forgotten' AND subject IN ({ids})",
                         t['claims'], scope):
            recorded = (_json(row['receipt']) or {}).get('trace') or {}
            for key in ('turns', 'actions'):
                t[key] |= {i for i in recorded.get(key) or [] if isinstance(i, str)}
    if _has(db, 'conversation_turns') and _has(db, 'conversations'):
        sql = '''SELECT t.id,t.result FROM conversation_turns t JOIN conversations s ON s.id=t.session
                 WHERE s.scope=? AND t.result IS NOT NULL''' + (f' AND s.actor IN ({_in(keys)})' if private else '')
        # Conversations are kept per device credential; the ledger actor may be the person.
        for row in db.execute(sql, (scope, *keys) if private else (scope,)):
            packet = (_json(sealing.open_row(sealing.of(db), 'conversation_turns', row)['result']) or {}).get('packet') or {}
            memory = [m for m in packet.get('memory') or [] if isinstance(m, dict)]
            cited = {m.get('claim_id') for m in memory}
            notes = {e.get('note_id') for e in packet.get('evidence') or [] if isinstance(e, dict)}
            notes |= {(m.get('support') or {}).get('note_id') for m in memory}
            focus = ((packet.get('focus') or {}).get('record_id') or '').removeprefix('note:')
            if cited & t['claims'] or (kind == 'source' and (notes & t['notes'] or focus in t['notes'])):
                t['turns'].add(row['id'])
    if _has(db, 'conversation_action_sources'):
        for link in db.execute('SELECT scope,action_id,turn_id,references_json FROM conversation_action_sources WHERE scope=?', (scope,)):
            binding = _json(sealing.open_row(sealing.of(db), 'conversation_action_sources', link)['references_json'])
            memory = binding.get('memory', []) if isinstance(binding, dict) else []
            refs = binding if isinstance(binding, list) else (binding or {}).get('sources', [])
            if (link['turn_id'] in t['turns'] or {m.get('claim_id') for m in memory if isinstance(m, dict)} & t['claims']
                    or (kind == 'source' and {r.get('note_id') for r in refs if isinstance(r, dict)} & t['notes'])):
                t['actions'].add(link['action_id'])
    if t['claims'] and _has(db, 'routine_action_sources'):
        t['actions'] |= {r[0] for r in _rows(db, "SELECT action_id FROM routine_action_sources WHERE scope=? AND cite_kind='statement' AND cite_id IN ({ids})",
                                             t['claims'], scope)}
    if t['events'] and _has(db, 'desk_action_evidence'):
        t['actions'] |= {r[0] for r in _rows(db, 'SELECT action_id FROM desk_action_evidence WHERE scope=? AND event_seq IN ({ids})', t['events'], scope)}
    if kind == 'source' and _has(db, 'actions'):
        for row in db.execute("SELECT scope,id,parameters FROM actions WHERE scope=? AND capability='vault.inbox_note'", (scope,)):
            if (_json(sealing.open_row(sealing.of(db), 'actions', row)['parameters']) or {}).get('source') == subject:
                t['actions'].add(row['id'])
    return t


def _category(count, holding, where, **detail):
    return {'count': count, 'holding_value': holding, 'where': list(where), **detail}


def scan(db, scope, actor, kind, subject, *, trace=None, cache_dir=None, database=None, forgotten_at=None):
    """What the workspace holds about one subject, by category. Identifiers only, never values.

    `trace` adds identifiers from earlier receipts; `cache_dir` is the job cache folder;
    `database` locates the export register; `forgotten_at` dates the latest forget."""
    if kind not in KINDS:
        raise Fault('invalid_deletion_subject_kind')
    t = _linked(db, scope, actor, kind, subject, trace or {})
    c = {}
    claims = _rows(db, 'SELECT id,value,object_id FROM memory_claims WHERE scope=? AND id IN ({ids})', t['claims'], scope) \
        if t['claims'] and _has(db, 'memory_claims') else []
    c['statements'] = _category(len(claims), sum(r['value'] is not None or r['object_id'] is not None for r in claims), ['memory_claims'])
    if kind == 'entity':
        keys = _keys(db, actor)
        held = _has(db, 'memory_entities') and db.execute(
            f"SELECT 1 FROM memory_entities WHERE id=? AND scope=? AND actor IN ({','.join('?' * len(keys))})",
            (subject, scope, *keys)).fetchone() is not None
        c['entity_name'] = _category(int(held), int(held), ['memory_entities'])
    captures = len(_rows(db, 'SELECT claim_id FROM memory_capture WHERE claim_id IN ({ids})', t['claims'])) \
        if t['claims'] and _has(db, 'memory_capture') else 0
    c['captures'] = _category(captures, 0, ['memory_capture'])
    from .memory_bin import count as binned
    held = binned(db, scope, entity=subject if kind == 'entity' else None, claims=t['claims'] if kind == 'statement' else (),
                  notes=t['notes'] if kind == 'source' else ())
    c['bin_copies'] = _category(held, held, ['memory_bin'])
    if kind == 'source':
        tables = {table: db.execute(f'SELECT count(*) FROM {table} WHERE scope=? AND source=?', (scope, subject)).fetchone()[0]
                  for table in INDEX_TABLES if _has(db, table)}
        c['source_index'] = _category(sum(tables.values()), sum(tables.values()), tables, by_table=tables)
        stones = db.execute('SELECT count(*) FROM memory_tombstones WHERE scope=? AND source=?', (scope, subject)).fetchone()[0] \
            if _has(db, 'memory_tombstones') else 0
        c['tombstones'] = _category(stones, 0, ['memory_tombstones'])
        count = holding = 0
        by_table = {}
        if _has(db, 'events'):
            bodies = [(_json(r['body']) or {}) for r in db.execute('SELECT body FROM events WHERE scope=? AND source=?', (scope, subject))]
            by_table['events'] = len(bodies)
            count += len(bodies); holding += sum(not isinstance(b, dict) or b.get('summary') != REMOVED for b in bodies)
        if _has(db, 'desk_documents'):
            titles = [r[0] for r in db.execute('SELECT title FROM desk_documents WHERE scope=? AND source=?', (scope, subject))]
            by_table['desk_documents'] = len(titles)
            count += len(titles); holding += sum(title != REMOVED for title in titles)
        if t['events'] and _has(db, 'desk_links'):
            titles = [r[0] for r in _rows(db, 'SELECT title FROM desk_links WHERE seq IN ({ids})', t['events'])]
            by_table['desk_links'] = len(titles)
            count += len(titles); holding += sum(title != REMOVED for title in titles)
        c['evidence_events'] = _category(count, holding, by_table, by_table=by_table)
        tables = {table: db.execute(f'SELECT count(*) FROM {table} WHERE scope=? AND source=?', (scope, subject)).fetchone()[0]
                  for table in CONNECTOR_TABLES if _has(db, table)}
        c['connector_records'] = _category(sum(tables.values()),
                                           tables.get('connector_instances', 0) + tables.get('connector_receipts', 0), tables, by_table=tables)
    turns = _rows(db, 'SELECT id,result FROM conversation_turns WHERE id IN ({ids})', t['turns']) \
        if t['turns'] and _has(db, 'conversation_turns') else []
    c['answers'] = _category(len(turns), sum(r['result'] is not None for r in turns), ['conversation_turns'],
                             question_text_kept=len(turns))
    plays = len(_rows(db, 'SELECT id FROM voice_playbacks WHERE scope=? AND turn_id IN ({ids})', t['turns'], scope)) \
        if t['turns'] and _has(db, 'voice_playbacks') else 0
    c['voice_playbacks'] = _category(plays, 0, ['voice_playbacks'])
    actions = _rows(db, 'SELECT id,state FROM actions WHERE scope=? AND id IN ({ids})', t['actions'], scope) \
        if t['actions'] and _has(db, 'actions') else []
    texts = len(_rows(db, 'SELECT action_id FROM drafts WHERE scope=? AND action_id IN ({ids})', t['actions'], scope)) \
        if t['actions'] and _has(db, 'drafts') else 0
    by_state = {}
    for row in actions:
        # Counted by whatever state the ledger records, so archived or lapsed drafts count too.
        by_state[row['state']] = by_state.get(row['state'], 0) + 1
    c['drafts'] = _category(len(actions), texts, ['actions', 'drafts'], by_state=dict(sorted(by_state.items())))
    nominations = len(_rows(db, "SELECT id FROM routine_nominations WHERE scope=? AND cite_kind='statement' AND cite_id IN ({ids})",
                            t['claims'], scope)) if t['claims'] and _has(db, 'routine_nominations') else 0
    c['routine_nominations'] = _category(nominations, 0, ['routine_nominations'])
    if kind == 'source':
        cited = 0
        if t['notes'] and _has(db, 'executive_records'):
            for row in db.execute('SELECT support FROM executive_records WHERE scope=? AND support IS NOT NULL', (scope,)):
                cited += (_json(row['support']) or {}).get('note_id') in t['notes']
        c['executive_citations'] = _category(cited, 0, ['executive_records'])
    artefacts = len(_rows(db, 'SELECT sha256 FROM artefacts WHERE scope=? AND sha256 IN ({ids})', t['artefacts'], scope)) \
        if t['artefacts'] and _has(db, 'artefacts') else 0
    c['job_artefacts'] = _category(artefacts, artefacts, ['artefacts'])
    jobs = len(_rows(db, 'SELECT id FROM jobs WHERE scope=? AND id IN ({ids})', t['jobs'], scope)) \
        if t['jobs'] and _has(db, 'jobs') else 0
    c['jobs'] = _category(jobs, 0, ['jobs'])
    wanted = {s for s in t['artefacts'] if isinstance(s, str) and SHA256.fullmatch(s)}
    if not wanted:
        c['cache_copies'] = _category(0, 0, ['job cache'], checked=True)
    elif cache_dir is None:
        c['cache_copies'] = _category(None, None, ['job cache'], checked=False)
    else:
        root = Path(cache_dir) / 'objects'
        copies = sum((root / s[:2] / s).is_file() for s in wanted)
        c['cache_copies'] = _category(copies, copies, ['job cache'], checked=True)
    history = len(_rows(db, 'SELECT seq FROM memory_claim_history WHERE scope=? AND claim_id IN ({ids})', t['claims'], scope)) \
        if t['claims'] and _has(db, 'memory_claim_history') else 0
    c['history_rows'] = _category(history, 0, ['memory_claim_history'])
    named = t['claims'] | {subject}
    c['audit_rows'] = _category(len(_rows(db, 'SELECT seq FROM audit WHERE scope=? AND subject IN ({ids})', named, scope)) if _has(db, 'audit') else 0,
                                0, ['audit'])
    c['lifecycle_receipts'] = _category(len(_rows(db, 'SELECT id FROM lifecycle_receipts WHERE scope=? AND subject IN ({ids})', named, scope))
                                        if _has(db, 'lifecycle_receipts') else 0, 0, ['lifecycle_receipts'])
    if database is None:
        c['exports_on_disk'] = _category(None, None, ['export register'], checked=False)
    else:
        present, gone = [], 0
        for entry in exports(database):
            if entry.get('scope') != scope or (kind != 'source' and entry.get('actor') not in _keys(db, actor)):
                continue
            hit = set(entry.get('statements') or []) & t['claims']
            hit = hit or (kind == 'entity' and subject in (entry.get('entities') or []))
            hit = hit or (kind == 'source' and (subject in (entry.get('sources') or []) or set(entry.get('notes') or []) & t['notes']))
            if not hit:
                continue
            if _on_disk(entry):
                present.append({'export_id': entry['export_id'], 'directory': entry['directory'], 'exported_at': entry.get('exported_at')})
            else:
                gone += 1
        c['exports_on_disk'] = _category(len(present), len(present), ['export register', 'export folders'], checked=True,
                                         exports=present, no_longer_on_disk=gone)
    backups = []
    if _has(db, 'lifecycle_backups'):
        for row in db.execute('SELECT id,created,file FROM lifecycle_backups ORDER BY created,id'):
            if (forgotten_at is None or row['created'] <= forgotten_at) and Path(row['file']).is_file():
                backups.append({'id': row['id'], 'file': Path(row['file']).name, 'created': row['created']})
    c['backups'] = _category(len(backups), len(backups), ['lifecycle_backups', 'backup files'], backups=backups)
    for name, value in c.items():
        value['description'] = CATEGORIES[name]
    return {'categories': c, 'trace': {k: sorted(v) for k, v in t.items()}}


def _short(category):
    return {'count': category['count'], 'holding_value': category['holding_value']}


def accounting(before, after, *, purge=False):
    """The receipt's view: per category, what was found, and what remains after the forget."""
    rows = {}
    for name, found in before['categories'].items():
        left = after['categories'].get(name, found)
        rows[name] = {'before': _short(found), 'after': _short(left), 'where': left['where']}
        for key in ('by_state', 'by_table', 'exports', 'backups', 'question_text_kept', 'checked'):
            if key in left:
                rows[name][key] = left[key]
    trace = {k: sorted(set(before['trace'][k]) | set(after['trace'][k])) for k in TRACE}
    known = lambda part: [v for v in part.values() if v['count'] is not None]
    return {'accounting': rows,
            'dependents_found': sum(v['count'] for v in known(before['categories'])),
            'still_held': {name: v['after']['count'] for name, v in rows.items() if v['after']['count']},
            'still_holding_value': {name: v['after']['holding_value'] for name, v in rows.items() if v['after']['holding_value']},
            'history': 'purged' if purge else 'value_free_rows_kept',
            'trace': trace, 'not_counted': NOT_COUNTED}


def traces(db, scope, actor, kind, subject):
    """Identifiers recorded by earlier receipts for this subject, and the latest forget time."""
    receipt_kind = {'source': 'source_forgotten', 'entity': 'entity_forgotten', 'statement': 'claim_forgotten'}[kind]
    merged, latest = {k: set() for k in TRACE}, None
    if not _has(db, 'lifecycle_receipts'):
        return merged, latest
    keys = _keys(db, actor)
    sql = 'SELECT at,receipt FROM lifecycle_receipts WHERE scope=? AND kind=? AND subject=?' + \
        ('' if kind == 'source' else f" AND actor IN ({','.join('?' * len(keys))})")
    for row in db.execute(sql, (scope, receipt_kind, subject) if kind == 'source' else (scope, receipt_kind, subject, *keys)):
        latest = max(latest or row['at'], row['at'])
        for k, ids in ((_json(row['receipt']) or {}).get('trace') or {}).items():
            if k in merged and isinstance(ids, list):
                merged[k] |= {i for i in ids if isinstance(i, (str, int))}
    return merged, latest


def report(store, bearer, kind, subject, *, cache_dir=None):
    """The deletion report: an owner asks what the workspace still holds about a subject."""
    if kind not in KINDS:
        raise Fault('invalid_deletion_subject_kind')
    ident(subject)
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        trace, latest = traces(db, p['scope'], p['id'], kind, subject)
        found = scan(db, p['scope'], p['id'], kind, subject, trace=trace, cache_dir=cache_dir,
                     database=store.path, forgotten_at=latest)
    held = found['categories']
    known = [v for v in held.values() if v['count'] is not None]
    return {'kind': 'deletion_report', 'subject': {'kind': kind, 'id': subject}, 'generated_at': store.now(),
            'forgotten_at': latest, 'held': held,
            'total_held': sum(v['count'] for v in known), 'total_holding_value': sum(v['holding_value'] for v in known),
            'not_checked': sorted(name for name, v in held.items() if v['count'] is None),
            'not_counted': NOT_COUNTED, 'basis': 'direct_scan_of_this_workspace_at_report_time',
            'values_included': False, 'secure_erasure': False, 'authority_granted': False}


def route(store, path, bearer, *, cache_dir=None):
    """GET /desk/deletion-report/{source|entity|statement}/{id}. Owner only; reads only."""
    match = re.fullmatch(r'/desk/deletion-report/(source|entity|statement)/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})', path)
    if not match:
        raise Fault('not_found', 404)
    return report(store, bearer, match.group(1), match.group(2), cache_dir=cache_dir)


def lines(result):
    """Plain lines for the command line."""
    subject = result['subject']
    out = [f"Deletion report for {subject['kind']} {subject['id']}: {result['total_held']} item(s) held, "
           f"{result['total_holding_value']} still holding a value or text."]
    for name, value in result['held'].items():
        if value['count'] is None:
            out.append(f'  {name}: not checked')
        elif value['count']:
            extra = ''
            if value.get('by_state'):
                extra = ' (' + ', '.join(f'{k} {v}' for k, v in value['by_state'].items()) + ')'
            out.append(f"  {name}: {value['count']} in {', '.join(value['where'])}, {value['holding_value']} holding a value{extra}")
            for item in value.get('exports', []):
                out.append(f"    export {item['export_id']} at {item['directory']}")
            for item in value.get('backups', []):
                out.append(f"    backup {item['file']}")
    out.append('Not counted: ' + ' '.join(NOT_COUNTED))
    return out
