"""Portable, readable export of what one credential may read (MEM-013).

An export is not a backup. `backup` copies the whole SQLite database, every table
and every person's records, as a consistent snapshot that `restore` can put back.
An export is a filtered, self-describing record, in plain JSON and readable
Markdown, of what this credential may read at the time: reviewed statements with
their review state, cited source revisions and lineage; capture settings and
retention; and executive records. It cannot be restored and grants nothing.

Never exported: access keys, credential digests, sessions, invitation codes,
other people's records, forgotten statements, statements whose support is
withheld, and captures whose chosen retention has ended. Note bodies stay in the
person's own Markdown files; only cited line references and currently permitted
quotes are included. The destination must be new or an empty folder outside every
vault and outside this repository. Files are private (0600 in a 0700 folder) and
are not encrypted.
"""
from __future__ import annotations
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
from contextlib import contextmanager, nullcontext
from .local import Fault

FORMAT, FORMAT_VERSION = 'alfred-portable-export', 1
REPOSITORY = Path(__file__).resolve().parents[1]
NEVER = ['access keys and credential digests', 'browser sessions', 'grant invitation codes',
         "other people's records", 'note bodies (your Markdown files remain the canonical copy)']
NOT_INCLUDED = ['knowledge index and note history', 'audit log', 'lifecycle receipts',
                'actions, drafts and approvals', 'jobs and artefacts',
                'recommendations and priorities order (recomputed from the records)']
DIFFERENCE = ('A backup is a consistent copy of the whole database for restore. '
              "This export is a filtered, readable record of one credential's authorised view. It cannot be restored.")


def _utc(seconds):
    return None if seconds is None else datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def collect(store, bearer):
    """Read through the existing authorised views; fail if authority moves meanwhile."""
    from .console_api import grant_revision
    from .executive import ExecutiveRecords
    from .reviewed_memory import ReviewedMemory
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        now = store.now()
        before = grant_revision(db, p, now)
    memory = ReviewedMemory(store).view(bearer)
    executive = ExecutiveRecords(store).view(bearer)
    with store.transaction() as db:
        q = store.authenticate(db, bearer, {'owner', 'reader'})
        if q['id'] != p['id'] or grant_revision(db, q, store.now()) != before:
            raise Fault('export_authority_changed', 409)
        captures = {r['claim_id']: dict(r) for r in db.execute(
            'SELECT m.* FROM memory_capture m JOIN memory_claims c ON c.id=m.claim_id WHERE c.scope=? AND c.actor=?',
            (p['scope'], p['id']))}
    entities = {e['id']: e for e in memory['entities']}
    replaced_by = {c['replaces_id']: c['id'] for c in memory['claims'] if c['replaces_id']}
    excluded = {'forgotten_statements': 0, 'withheld_statements': 0, 'retention_ended_statements': 0}
    statements, kept_captures = [], []

    def entity(identity):
        e = entities.get(identity)
        return {'id': identity, 'kind': e['kind'], 'name': e['name']} if e else {'id': identity, 'kind': None, 'name': None}

    for c in memory['claims']:
        capture = captures.get(c['id'])
        if c['state'] == 'forgotten':
            excluded['forgotten_statements'] += 1
            continue
        if c['withheld']:
            excluded['withheld_statements'] += 1
            continue
        if capture and capture['retention_until'] is not None and capture['retention_until'] <= now:
            excluded['retention_ended_statements'] += 1
            continue
        source = c['source']
        statements.append({
            'id': c['id'], 'version': c['version'], 'review_state': c['state'], 'usable_now': c['usable'],
            'subject': entity(c['subject_id']), 'predicate': c['predicate'],
            'object': entity(c['object_id']) if c['object_id'] else None, 'value': c['value'],
            'valid_from': c['valid_from'], 'valid_until': c['valid_until'],
            'recorded_at': c['created'], 'reviewed_at': c['reviewed'], 'reviewer': c['reviewer'],
            'lineage': {'replaces': c['replaces_id'], 'replaced_by': replaced_by.get(c['id'])},
            'conflicts_with': c['conflicts'],
            'source': {'note_id': c['note_id'], 'sha256': c['note_hash'], 'revision': c['note_revision'],
                       'start_line': c['first_line'], 'end_line': c['last_line'], 'quote_sha256': c['quote_hash'],
                       'state': 'current' if source else 'changed',
                       'path': source['path'] if source else None, 'title': source['title'] if source else None,
                       'quote': source['quote'] if source else None}})
        if capture:
            kept_captures.append({'statement_id': c['id'], 'memory_type': capture['memory_type'],
                                  'retention_until': capture['retention_until'], 'retention_until_utc': _utc(capture['retention_until']),
                                  'retention': 'kept until the date shown, then forgotten with a receipt' if capture['retention_until'] is not None
                                  else 'no automatic expiry; kept until the person forgets it',
                                  'captured_from': json.loads(capture['captured_from']), 'captured_at': capture['created']})
    # Lineage and conflicts never name a statement that was left out.
    kept = {s['id'] for s in statements}

    def reference(identity):
        return identity if identity in kept or identity is None else 'not_exported'

    for s in statements:
        s['lineage'] = {k: reference(v) for k, v in s['lineage'].items()}
        s['conflicts_with'] = [reference(i) for i in s['conflicts_with']]
    exported = {s['subject']['id'] for s in statements} | {s['object']['id'] for s in statements if s['object']}
    names = {}
    for e in memory['entities']:
        names.setdefault((e['kind'], e['name'].casefold()), []).append(e['id'])
    listed = [{'id': e['id'], 'kind': e['kind'], 'name': e['name'], 'created_at': e['created'],
               'same_name_as': sorted(i for i in names[(e['kind'], e['name'].casefold())] if i != e['id']),
               'referenced_by_exported_statements': e['id'] in exported} for e in memory['entities']]
    records = [{k: r[k] for k in ('id', 'kind', 'title', 'detail', 'status', 'open', 'project', 'due', 'overdue', 'rank',
                                  'origin', 'derived_from', 'version', 'created', 'updated', 'support')} | {'due_utc': _utc(r['due'])}
               for r in executive['records']]
    return {'principal': {'workspace': p['scope'], 'credential': p['id'], 'role': p['role'], 'person': p['person_id']},
            'exported_at': now, 'grant_revision': before, 'entities': listed, 'statements': statements,
            'captures': kept_captures, 'executive_records': records, 'excluded': excluded}


def _longest_backticks(value):
    return max((len(run) for run in ''.join(c if c == '`' else ' ' for c in value).split()), default=0)


def _code(value):
    """Inline code, so note text is shown literally and never rendered as Markdown or HTML."""
    if value is None:
        return '(none)'
    value = ' '.join(str(value).split())
    if not value:
        return '(empty)'
    fence = '`' * (_longest_backticks(value) + 1)
    padding = ' ' if value.startswith('`') or value.endswith('`') else ''
    return f'{fence}{padding}{value}{padding}{fence}'


def _block(value):
    fence = '`' * max(3, _longest_backticks(value) + 1)
    return f'{fence}text\n{value}\n{fence}'


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


def render(bundle):
    """The bundle's files as bytes: plain JSON, readable Markdown and checksums."""
    when = _utc(bundle['exported_at'])
    who = bundle['principal']
    statements = {'format': FORMAT, 'kind': 'reviewed_statements', 'basis': 'user_reviewed_statements_not_verified_facts',
                  'time_unit': 'unix_seconds_utc', 'entities': bundle['entities'], 'statements': bundle['statements']}
    captures = {'format': FORMAT, 'kind': 'memory_captures', 'basis': 'capture_settings_chosen_by_the_person',
                'time_unit': 'unix_seconds_utc', 'captures': bundle['captures']}
    executive = {'format': FORMAT, 'kind': 'executive_records', 'basis': 'user_authored_record_not_verified_fact',
                 'time_unit': 'unix_seconds_utc', 'records': bundle['executive_records']}
    lines = ['# Reviewed statements', '',
             f'Exported {when} for workspace {_code(who["workspace"])} by credential {_code(who["credential"])}.',
             'These are statements the person reviewed or proposed, not verified facts. A proposed statement has not been reviewed.', '']
    for state in ('accepted', 'proposed', 'disputed', 'superseded', 'withdrawn', 'invalidated'):
        chosen = [s for s in bundle['statements'] if s['review_state'] == state]
        if not chosen:
            continue
        lines += [f'## {state.capitalize()} ({len(chosen)})', '']
        for s in chosen:
            target = _code(s['value']) if s['object'] is None else f"{_code(s['object']['name'])} ({s['object']['kind']}, {_code(s['object']['id'])})"
            lines.append(f"- {_code(s['subject']['name'])} ({s['subject']['kind']}, {_code(s['subject']['id'])}) "
                         f"{s['predicate'].replace('_', ' ')}: {target}")
            src = s['source']
            lines.append(f"  - Statement {_code(s['id'])}, version {s['version']}, usable now: {'yes' if s['usable_now'] else 'no'}")
            lines.append(f"  - Source note {_code(src['note_id'])} revision {src['revision']}, lines {src['start_line']} to {src['end_line']}, "
                         f"sha256 {_code(src['sha256'])}, support {src['state']}")
            if src['quote'] is not None:
                lines.append(f"  - Cited text: {_code(src['quote'])}")
            if s['valid_from'] is not None or s['valid_until'] is not None:
                lines.append(f"  - Valid from {_utc(s['valid_from']) or 'any time'} until {_utc(s['valid_until']) or 'no end'}")
            if s['conflicts_with']:
                lines.append(f"  - Conflicts with {', '.join(_code(i) for i in s['conflicts_with'])}, so it is not used until the person resolves it")
            if s['lineage']['replaces'] or s['lineage']['replaced_by']:
                lines.append(f"  - Replaces {_code(s['lineage']['replaces'])}; replaced by {_code(s['lineage']['replaced_by'])}")
        lines.append('')
    if bundle['captures']:
        lines += ['## Capture settings and retention', '']
        for c in bundle['captures']:
            lines.append(f"- Statement {_code(c['statement_id'])}: {c['memory_type']}; "
                         f"{'kept until ' + c['retention_until_utc'] if c['retention_until'] is not None else 'no automatic expiry'}")
        lines.append('')
    same = [e for e in bundle['entities'] if e['same_name_as']]
    if same:
        lines += ['## Entities that share a name', '', 'They are separate records and were never merged.', '']
        lines += [f"- {_code(e['name'])} ({e['kind']}, {_code(e['id'])}); same name as {', '.join(_code(i) for i in e['same_name_as'])}" for e in same]
        lines.append('')
    records_md = ['# Executive records', '', f'Exported {when}. Written by the person; not verified facts and no authority to act.', '']
    for r in bundle['executive_records']:
        support = r['support']
        records_md.append(f"## {r['kind'].replace('_', ' ').capitalize()}: {_code(r['title'])}")
        records_md.append('')
        records_md.append(f"- Record {_code(r['id'])}, version {r['version']}, status {r['status']}"
                          + (f", due {r['due_utc']}" + (' (overdue)' if r['overdue'] else '') if r['due'] is not None else ''))
        if r['project']:
            records_md.append(f"- Project {_code(r['project'])}")
        if r['derived_from']:
            records_md.append(f"- Accepted from a recommendation based on {_code(r['derived_from'])}")
        if support:
            records_md.append(f"- Cited note {_code(support['note_id'])}, lines {support['start_line']} to {support['end_line']}: {support['state']}")
        if r['detail']:
            records_md += ['', _block(r['detail'])]
        records_md.append('')
    files = {'statements.json': _json(statements), 'captures.json': _json(captures),
             'executive-records.json': _json(executive),
             'statements.md': ('\n'.join(lines).rstrip() + '\n').encode(),
             'executive-records.md': ('\n'.join(records_md).rstrip() + '\n').encode()}
    counts = {'entities': len(bundle['entities']), 'statements': len(bundle['statements']),
              'captures': len(bundle['captures']), 'executive_records': len(bundle['executive_records'])}
    readme = '\n'.join([
        '# ALFRED portable export', '',
        f'Exported {when} for workspace {_code(who["workspace"])}, credential {_code(who["credential"])} ({who["role"]}).', '',
        'This folder holds what that credential could read when the export was assembled: '
        f"{counts['statements']} reviewed statement(s), {counts['entities']} entities, "
        f"{counts['captures']} capture setting(s) and {counts['executive_records']} executive record(s).", '',
        '| File | Contents |', '|---|---|',
        '| `manifest.json` | Format, time, counts, exclusions and the SHA-256 of every other file |',
        '| `statements.json`, `statements.md` | Reviewed statements with review state, cited source revision and lineage |',
        '| `captures.json` | Memory type and retention chosen at capture |',
        '| `executive-records.json`, `executive-records.md` | Goals, priorities, commitments, decisions, milestones and follow-ups |',
        '| `SHA256SUMS` | Checksums; verify with `sha256sum -c SHA256SUMS` |', '',
        '## Not a backup', '', DIFFERENCE, '',
        '## Left out on purpose', '',
        *[f'- {item}' for item in NEVER],
        f"- {bundle['excluded']['forgotten_statements']} forgotten statement(s), {bundle['excluded']['withheld_statements']} withheld statement(s) "
        f"and {bundle['excluded']['retention_ended_statements']} statement(s) whose retention has ended", '',
        'Not part of this export: ' + '; '.join(NOT_INCLUDED) + '.', '',
        'Statements and records are what the person reviewed or wrote, not verified facts, and grant no authority. '
        'The files are not encrypted: keep them private.', ''])
    files['README.md'] = readme.encode()
    export_id = 'export-' + datetime.fromtimestamp(bundle['exported_at'], timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4)
    manifest = {'format': FORMAT, 'format_version': FORMAT_VERSION, 'export_id': export_id,
                'exported_at': bundle['exported_at'], 'exported_at_utc': when, **who,
                'authority': {'grant_revision': bundle['grant_revision'],
                              'rule': 'Only what this credential could read when the export was assembled.'},
                'counts': counts,
                'excluded': {**bundle['excluded'], 'never_exported': NEVER},
                'not_included': NOT_INCLUDED, 'differs_from_backup': DIFFERENCE,
                'files': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                           'media_type': 'application/json' if name.endswith('.json') else 'text/markdown'}
                          for name, data in sorted(files.items())],
                'basis': {'statements': 'user_reviewed_statements_not_verified_facts',
                          'executive_records': 'user_authored_record_not_verified_fact'},
                'encrypted': False, 'restorable': False, 'authority_granted': False}
    files['manifest.json'] = _json(manifest)
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())).encode()
    return manifest, files


def check_destination(destination, vaults=()):
    """A new or empty folder, outside every vault and this repository. Never a symlink."""
    from .placement import INSIDE_VAULT, contains, locate
    target = Path(os.path.normpath(Path(destination).expanduser().absolute()))
    if target.is_symlink():
        raise Fault('export_destination_symlink')
    if contains(REPOSITORY, target):
        raise Fault('export_destination_inside_repository')
    found = locate(target)
    if any(v is not None and contains(v, target) for v in vaults) or (found and found['code'] == INSIDE_VAULT):
        raise Fault('export_destination_inside_vault')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise Fault('export_destination_not_empty', 409)
    if not target.parent.is_dir():
        raise Fault('export_parent_missing', 404)
    return target


def write(destination, files, vaults=(), *, publication_guard=nullcontext):
    """Write into a private staging folder, then rename it into place."""
    target = check_destination(destination, vaults)
    staging = target.parent / f'.{target.name}.partial-{secrets.token_hex(6)}'
    os.mkdir(staging, 0o700)
    try:
        os.chmod(staging, 0o700)
        for name, data in files.items():
            fd = os.open(staging / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
        handle = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
        try:
            # rename() replaces only an empty directory; anything that appeared meanwhile stops it.
            with publication_guard():
                os.rename(staging, target)
        except OSError as exc:
            if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST, errno.ENOTDIR, errno.EISDIR):
                raise
            raise Fault('export_destination_not_empty', 409) from None
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    handle = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return target


def export(store, bearer, destination, *, vaults=()):
    """Stage privately, recheck authority/data at publication, account for copies.

    Export copies are readable files. A later forget marks this ledger's copy for
    review; it cannot recall moved/copied files or claim secure deletion.
    """
    from .console_api import grant_revision
    check_destination(destination, vaults)
    bundle = collect(store,bearer)
    manifest, files = render(bundle)
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        note_ids = {s['source']['note_id'] for s in bundle['statements']}
        sources = {r[0] for n in note_ids for r in db.execute('SELECT source FROM knowledge_notes WHERE scope=? AND id=?',(p['scope'],n))}
        # Preserve copy accounting even when a backup predates this export.
        # Intent is conservative: a crash may leave a readable copy or staging.
        from .lifecycle import append
        append(store, {'kind':'export_intent','scope':p['scope'],'actor':p['id'],'at':store.now(),
                      'subject':manifest['export_id'],'directory':str(Path(destination).absolute()),
                      'manifest_sha256':hashlib.sha256(files['manifest.json']).hexdigest(),
                      'sources':sorted(sources),'claims':[s['id'] for s in bundle['statements']]})
        db.execute('INSERT INTO lifecycle_exports VALUES (?,?,?,?,?,?,?,?,?)',
                   (manifest['export_id'],p['scope'],p['id'],store.now(),str(Path(destination).absolute()),
                    hashlib.sha256(files['manifest.json']).hexdigest(),json.dumps(sorted(sources)),
                    json.dumps([s['id'] for s in bundle['statements']]),'writing'))

    renamed = [False]
    @contextmanager
    def guard():
        with store.transaction() as db:
            q = store.authenticate(db,bearer,{'owner','reader'})
            if q['id'] != bundle['principal']['credential'] or grant_revision(db,q,store.now()) != bundle['grant_revision']:
                raise Fault('export_authority_changed',409)
            for statement in bundle['statements']:
                row = db.execute('SELECT version,state FROM memory_claims WHERE id=? AND scope=? AND actor=?',
                                 (statement['id'],q['scope'],q['id'])).fetchone()
                if not row or row['version'] != statement['version'] or row['state'] == 'forgotten':
                    raise Fault('export_data_changed',409)
                source = statement['source']
                if source['state'] == 'current':
                    note = db.execute("SELECT sha256,revision FROM knowledge_notes WHERE scope=? AND id=? AND status='ready'",
                                      (q['scope'],source['note_id'])).fetchone()
                    if not note or (note['sha256'],note['revision']) != (source['sha256'],source['revision']):
                        raise Fault('export_data_changed',409)
            for record in bundle['executive_records']:
                row = db.execute('SELECT version FROM executive_records WHERE id=? AND scope=? AND actor=?',
                                 (record['id'],q['scope'],q['id'])).fetchone()
                if not row or row['version'] != record['version']:
                    raise Fault('export_data_changed',409)
            yield
            renamed[0] = True
            db.execute("UPDATE lifecycle_exports SET status='published' WHERE id=?",(manifest['export_id'],))
            store.log(db,q['scope'],q['id'],'export.written',manifest['export_id'])
    try:
        target = write(destination,files,vaults,publication_guard=guard)
    except BaseException:
        with store.transaction() as db:
            db.execute('UPDATE lifecycle_exports SET status=? WHERE id=?',
                       ('publication_unknown' if renamed[0] else 'failed',manifest['export_id']))
        raise
    return manifest | {'directory': str(target)}
