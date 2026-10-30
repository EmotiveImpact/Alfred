"""Reviewed, person-private statements over indexed evidence, not automated truth.

The ledger belongs to the person (every paired device of that person shares it);
each review still records the device credential that made it.

Entities are explicitly created, never merged by name. Review records a user's
judgement; it grants no device/tool authority. Source slices are reconstructed,
not duplicated. Invalidated statement values are cleared on reconciliation.
Every review transition is also appended to a value-free history (memory_history).
"""
from __future__ import annotations
import json
import secrets
from .local import Fault, exact, ident, text, timestamp, fingerprint
from . import memory_bin, memory_history, sealing
from .policy import ledger, migrate_ledgers, person_credentials

KINDS = ('person', 'organisation', 'project', 'asset', 'decision', 'commitment', 'event')
RELATIONS = {
    'responsible_person': {'objects': ('person',), 'single': True},
    'depends_on': {'objects': KINDS, 'single': False},
    'status': {'objects': (), 'single': True},
    'scheduled_for': {'objects': (), 'single': True},
    'decision': {'objects': (), 'single': True},
}
MAX_ENTITIES, MAX_CLAIMS = 128, 256
MAX_CONTEXT_CLAIMS, MAX_CONTEXT_CHARACTERS = 4, 1600
CONTEXT_REF_KEYS = {'claim_id', 'version', 'note_id', 'sha256', 'revision',
                    'start_line', 'end_line', 'quote_hash'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS reviewed_memory_meta(version INTEGER NOT NULL);
INSERT INTO reviewed_memory_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM reviewed_memory_meta);
CREATE TABLE IF NOT EXISTS memory_entities(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
 name TEXT NOT NULL, created INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS memory_entities_owner ON memory_entities(scope,actor);
CREATE TABLE IF NOT EXISTS memory_claims(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, subject_id TEXT NOT NULL, predicate TEXT NOT NULL,
 object_id TEXT, value TEXT, valid_from INTEGER, valid_until INTEGER,
 note_id TEXT NOT NULL, note_hash TEXT NOT NULL, note_revision INTEGER NOT NULL,
 first_line INTEGER NOT NULL, last_line INTEGER NOT NULL, quote_hash TEXT NOT NULL,
 state TEXT NOT NULL, version INTEGER NOT NULL, created INTEGER NOT NULL,
 reviewed INTEGER, reviewer TEXT, replaces_id TEXT,
 UNIQUE(scope,actor,request_id));
CREATE INDEX IF NOT EXISTS memory_claims_owner ON memory_claims(scope,actor);
CREATE TABLE IF NOT EXISTS memory_capture(
 claim_id TEXT PRIMARY KEY REFERENCES memory_claims(id), memory_type TEXT NOT NULL,
 retention_until INTEGER, captured_from TEXT NOT NULL, created INTEGER NOT NULL);
'''
MEMORY_TYPES = ('semantic', 'episodic', 'preference', 'commitment', 'procedural')
FORGET_OPTIONS = {'purge_history', 'absolute', 'confirm'}
WITHDRAWN = 'Saved answers and drafts the forget withdrew stay withdrawn; ask again for a fresh answer.'


def forget_options(body, required, identity):
    """A forget body: the required keys plus any of purge_history, absolute and confirm.

    An ordinary forget is the default. An absolute forget is deliberate: the identifier
    must be typed back as `confirm`."""
    if type(body) is not dict or not required<=set(body) or set(body)-required-FORGET_OPTIONS:
        raise Fault('invalid_fields')
    purge,absolute=body.get('purge_history',False),body.get('absolute',False)
    if type(purge) is not bool or type(absolute) is not bool or ('confirm' in body and not absolute):
        raise Fault('invalid_fields')
    if absolute and body.get('confirm')!=identity:
        raise Fault('confirmation_mismatch')
    return purge,'absolute' if absolute else 'ordinary'


def overlap(a, b):
    """Half-open validity intervals, None means unbounded."""
    return max(a['valid_from'] or 0, b['valid_from'] or 0) < min(
        a['valid_until'] if a['valid_until'] is not None else 2**53,
        b['valid_until'] if b['valid_until'] is not None else 2**53)


class ReviewedMemory:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM reviewed_memory_meta')] != [1]:
                raise Fault('unsupported_reviewed_memory_version')
        memory_history.initialise(store)
        # The review ledger is per person, so a paired device shows the same history.
        with store.transaction() as db:
            migrate_ledgers(db)

    @staticmethod
    def _entity(db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM memory_entities WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], ledger(db, p))).fetchone()
        if not row:
            raise Fault('memory_entity_not_found', 404)
        return dict(row)

    @staticmethod
    def _claim(db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM memory_claims WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], ledger(db, p))).fetchone()
        if not row:
            raise Fault('memory_claim_not_found', 404)
        return dict(row)

    @staticmethod
    def _source(db, scope, ref, now, principal=None):
        """Read and check current indexed source in the caller's transaction."""
        exact(ref, {'note_id', 'sha256', 'revision', 'start_line', 'end_line'})
        ident(ref['note_id'])
        if type(ref['sha256']) is not str or len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256']):
            raise Fault('invalid_memory_source_hash')
        if type(ref['revision']) is not int or ref['revision'] < 1:
            raise Fault('invalid_memory_source_revision')
        first, last = ref['start_line'], ref['end_line']
        if type(first) is not int or type(last) is not int or not 1 <= first <= last or last-first >= 8:
            raise Fault('invalid_memory_source_range')
        raw = db.execute('''SELECT n.* FROM knowledge_notes n
          JOIN knowledge_sources s ON n.scope=s.scope AND n.source=s.source
          JOIN credentials c ON c.scope=n.scope AND c.id=n.source
          WHERE n.scope=? AND n.id=? AND n.status='ready' AND s.status IN ('ready','attention')
          AND c.role='source' AND c.revoked=0 AND c.expires>?''',
          (scope, ref['note_id'], now)).fetchone()
        sealer = sealing.of(db)
        n = sealing.open_row(sealer, 'knowledge_notes', raw)
        from .policy import permitted
        if not n or (principal is not None and not permitted(db,principal,n['source'],now)) or n['sha256'] != ref['sha256'] or n['revision'] != ref['revision']:
            raise Fault('memory_source_changed', 409)
        lines = n['body'].splitlines()
        if last > len(lines):
            raise Fault('invalid_memory_source_range')
        quote = '\n'.join(lines[first-1:last])
        if not quote.strip() or len(quote) > 1400:
            raise Fault('memory_source_excerpt_capacity')
        return {'note_id':n['id'], 'path':n['path'], 'title':n['title'], 'sha256':n['sha256'],
                'revision':n['revision'], 'start_line':first, 'end_line':last, 'quote':quote,
                'quote_hash':sealer.fingerprint(sealing.area_of(raw['body']), sealing.text_digest(quote))}

    @staticmethod
    def _ref(c):
        return {'note_id':c['note_id'], 'sha256':c['note_hash'], 'revision':c['note_revision'],
                'start_line':c['first_line'], 'end_line':c['last_line']}

    @staticmethod
    def _support_state(db, scope, c):
        """Why a claim's support is or is not usable, independent of who may read it.

        'changed' means the supporting text was edited, renamed, deleted or came back
        under a new revision: a durable change that needs a fresh human review. There
        is deliberately no automatic revival across revisions.
        'withheld' means the file is temporarily unreadable; nothing is invalidated.
        Permission, source availability and credential state are checked separately at
        use, so losing access withholds a review instead of destroying it, and restoring
        access restores it while the supporting revision is unchanged.
        """
        raw = db.execute('SELECT scope,source,id,status,sha256,revision,body FROM knowledge_notes WHERE scope=? AND id=?',
                         (scope, c['note_id'])).fetchone()
        sealer = sealing.of(db)
        n = sealing.open_row(sealer, 'knowledge_notes', raw)
        if not n or n['status'] == 'missing':
            return 'changed'
        if n['status'] != 'ready':
            return 'withheld'
        if n['sha256'] != c['note_hash'] or n['revision'] != c['note_revision']:
            return 'changed'
        lines = n['body'].splitlines()
        if c['last_line'] > len(lines):
            return 'changed'
        quote = '\n'.join(lines[c['first_line']-1:c['last_line']])
        digest = sealer.fingerprint(sealing.area_of(raw['body']), sealing.text_digest(quote))
        return 'changed' if digest != c['quote_hash'] else 'current'

    def _reconcile(self, db, p):
        for row in db.execute("SELECT * FROM memory_claims WHERE scope=? AND actor=? AND state!='invalidated' AND (value IS NOT NULL OR object_id IS NOT NULL)",
                              (p['scope'], ledger(db, p))).fetchall():
            c=dict(row)
            state=self._support_state(db,p['scope'],c)
            if state=='changed':
                db.execute("UPDATE memory_claims SET state='invalidated',value=NULL,object_id=NULL,version=version+1 WHERE id=?",(c['id'],))
                self.store.log(db,p['scope'],p['id'],'memory.invalidated',c['id'])
                memory_history.record(db,p['scope'],ledger(db,p),c['id'],'invalidated',self.store.now(),memory_history.SYSTEM,detail='support_changed')

    def create_entity(self, bearer, body):
        exact(body, {'id','kind','name'});ident(body['id']);text(body['name'],120)
        if type(body['kind']) is not str or body['kind'] not in KINDS or not body['name'].strip():
            raise Fault('invalid_memory_entity')
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            existing=db.execute('SELECT * FROM memory_entities WHERE id=?',(body['id'],)).fetchone()
            if existing:
                if (existing['scope'],existing['actor'],existing['kind'],existing['name'])!=(p['scope'],ledger(db,p),body['kind'],body['name'].strip()):
                    raise Fault('memory_entity_id_unavailable',409)
                return {'id':body['id'],'reused':True}
            if db.execute('SELECT count(*) FROM memory_entities WHERE actor=?',(ledger(db,p),)).fetchone()[0]>=MAX_ENTITIES:
                raise Fault('memory_entity_capacity',409)
            db.execute('INSERT INTO memory_entities VALUES (?,?,?,?,?,?)',
                       (body['id'],p['scope'],ledger(db,p),body['kind'],body['name'].strip(),self.store.now()))
            self.store.log(db,p['scope'],p['id'],'memory.entity_created',body['id'])
        return {'id':body['id'],'reused':False}

    def capture(self, bearer, body):
        """'Remember this': an editable proposal with type and retention. Never auto-accepted."""
        keys={'request_id','subject_id','predicate','object_id','value','valid_from','valid_until','evidence'}
        exact(body, keys|{'memory_type','retention_days','captured_from'})
        if body['memory_type'] not in MEMORY_TYPES:raise Fault('invalid_memory_type')
        days=body['retention_days']
        if days is not None and (type(days) is not int or not 1<=days<=3650):raise Fault('invalid_retention')
        origin=body['captured_from']
        if type(origin) is not dict or set(origin)-{'turn_id','note_id'} or not all(type(v) is str and len(v)<=80 for v in origin.values()):
            raise Fault('invalid_capture_origin')
        made=self.propose(bearer,{k:body[k] for k in keys},capture={'memory_type':body['memory_type'],'retention_days':days,'captured_from':origin})
        return {**made,'preview':self._preview(bearer,made['id'])}

    def _preview(self, bearer, identity):
        view=self.view(bearer);claim=next(c for c in view['claims'] if c['id']==identity)
        entities={e['id']:e for e in view['entities']}
        return {'scope':view['scope'],'memory_type':claim.get('memory_type'),'retention_until':claim.get('retention_until'),
                'valid_from':claim['valid_from'],'valid_until':claim['valid_until'],
                'subject':entities[claim['subject_id']]['name'],'predicate':claim['predicate'],
                'value':claim['value'],'object':entities[claim['object_id']]['name'] if claim['object_id'] in entities else None,
                'source':{k:claim['source'][k] for k in ('note_id','path','title','start_line','end_line','quote')} if claim['source'] else None,
                'state':claim['state'],'needs_review':True,'authority_granted':False}

    def apply_retention(self, bearer):
        """Forget captured statements whose user-chosen retention has ended, with receipts.

        The owner chose the end at capture, so it is absolute: no bin, and no restore
        brings the statement back. A copy already in the bin goes too, and a statement
        forgotten ordinarily is journalled again as absolute, even after its bin copy left."""
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            held=memory_bin.held_claims(db,p['scope'])
            def settled(r):
                if r['state']!='forgotten' or r['id'] in held:return False
                latest=self._latest(db,p,'claim_forgotten',r['id'])
                return latest is not None and latest.get('layer','absolute')=='absolute'
            due=[(r['id'],r['version']) for r in db.execute('''SELECT c.id,c.version,c.state FROM memory_claims c JOIN memory_capture m ON m.claim_id=c.id
                 WHERE c.scope=? AND c.actor=? AND m.retention_until IS NOT NULL AND m.retention_until<=?''',
                 (p['scope'],ledger(db,p),self.store.now())) if not settled(r)]
        return [self._forget(bearer,identity,version,'absolute',False,reason='retention_ended') for identity,version in due]

    def propose(self, bearer, body, capture=None):
        exact(body, {'request_id','subject_id','predicate','object_id','value','valid_from','valid_until','evidence'})
        ident(body['request_id']);ident(body['subject_id'])
        if type(body['predicate']) is not str or body['predicate'] not in RELATIONS:
            raise Fault('invalid_memory_predicate')
        relation=RELATIONS[body['predicate']]
        if relation['objects']:
            ident(body['object_id'])
            if body['value'] is not None:raise Fault('memory_object_not_text')
        else:
            if body['object_id'] is not None:raise Fault('memory_value_not_entity')
            text(body['value'],400)
            if not body['value'].strip():raise Fault('invalid_memory_value')
        for key in ('valid_from','valid_until'):
            if body[key] is not None:timestamp(body[key])
        if body['valid_until'] is not None and body['valid_until'] <= (body['valid_from'] or 0):
            raise Fault('invalid_memory_validity')
        digest=fingerprint(body)
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'});self._reconcile(db,p)
            old=db.execute('SELECT id,request_hash,state FROM memory_claims WHERE scope=? AND actor=? AND request_id=?',
                           (p['scope'],ledger(db,p),body['request_id'])).fetchone()
            if old:
                if old['request_hash']!=digest:raise Fault('memory_request_collision',409)
                return {'id':old['id'],'state':old['state'],'reused':True}
            self._entity(db,p,body['subject_id'])
            if body['object_id']:
                other=self._entity(db,p,body['object_id'])
                if other['kind'] not in relation['objects']:raise Fault('memory_object_kind')
                if body['subject_id']==body['object_id']:raise Fault('memory_self_relation')
            source=self._source(db,p['scope'],body['evidence'],self.store.now(),p)
            if db.execute('SELECT count(*) FROM memory_claims WHERE actor=?',(ledger(db,p),)).fetchone()[0]>=MAX_CLAIMS:
                raise Fault('memory_claim_capacity',409)
            cid='claim-'+secrets.token_hex(12)
            db.execute('INSERT INTO memory_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (cid,p['scope'],ledger(db,p),body['request_id'],digest,body['subject_id'],body['predicate'],
                        body['object_id'],body['value'].strip() if body['value'] else None,body['valid_from'],body['valid_until'],
                        source['note_id'],source['sha256'],source['revision'],source['start_line'],source['end_line'],
                        source['quote_hash'],'proposed',1,self.store.now(),None,None,None))
            if capture is not None:
                until=self.store.now()+capture['retention_days']*86400 if capture['retention_days'] else None
                db.execute('INSERT INTO memory_capture VALUES (?,?,?,?,?)',(cid,capture['memory_type'],until,json.dumps(capture['captured_from'],sort_keys=True),self.store.now()))
            self.store.log(db,p['scope'],p['id'],'memory.proposed',cid)
            memory_history.record(db,p['scope'],ledger(db,p),cid,'proposed',self.store.now(),p['id'],
                                  detail='captured' if capture is not None else None,valid=(body['valid_from'],body['valid_until']))
        return {'id':cid,'state':'proposed','reused':False}

    def review(self, bearer, identity, body):
        """Record one decision. Accepting or superseding a proposal may also set its valid
        period, once, before it is first decided; after that the period is fixed, so the
        recorded history stays a faithful account of what was held and for when."""
        base={'version','decision','replaces_id','replaces_version'}
        if type(body) is not dict or set(body) not in (base,base|{'valid_from','valid_until'}):
            raise Fault('invalid_fields')
        if type(body['version']) is not int or body['version'] < 1 or body['decision'] not in ('accept','dispute','withdraw','supersede'):
            raise Fault('invalid_memory_review')
        if body['decision']!='supersede' and (body['replaces_id'] is not None or body['replaces_version'] is not None):
            raise Fault('unexpected_memory_replacement')
        validity=None
        if 'valid_from' in body:
            if body['decision'] not in ('accept','supersede'):raise Fault('unexpected_memory_validity')
            for key in ('valid_from','valid_until'):
                if body[key] is not None:timestamp(body[key])
            if body['valid_until'] is not None and body['valid_until'] <= (body['valid_from'] or 0):
                raise Fault('invalid_memory_validity')
            validity=(body['valid_from'],body['valid_until'])
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'});self._reconcile(db,p)
            c=self._claim(db,p,identity)
            if c['state']=='invalidated':raise Fault('memory_source_changed',409)
            if c['version']!=body['version']:raise Fault('memory_review_changed',409)
            if c['state'] not in ('proposed','accepted','disputed'):raise Fault('memory_review_closed',409)
            if validity==(c['valid_from'],c['valid_until']):validity=None
            if validity is not None and c['state']!='proposed':raise Fault('memory_validity_fixed',409)
            if memory_history.count(db,p['scope'],ledger(db,p),c['id'])>=memory_history.MAX_HISTORY_PER_CLAIM:
                raise Fault('memory_history_capacity',409)
            self._source(db,p['scope'],self._ref(c),self.store.now(),p)
            replacement=c['replaces_id']
            if validity is not None:
                db.execute('UPDATE memory_claims SET valid_from=?,valid_until=? WHERE id=?',(*validity,c['id']))
            if body['decision']=='supersede':
                if c['replaces_id'] is not None:raise Fault('memory_replacement_already_recorded',409)
                if type(body['replaces_version']) is not int:raise Fault('invalid_memory_replacement')
                prior=self._claim(db,p,body['replaces_id'])
                if prior['id']==c['id'] or prior['state'] not in ('accepted','disputed','invalidated') or prior['version']!=body['replaces_version']:
                    raise Fault('memory_replacement_changed',409)
                if (prior['subject_id'],prior['predicate'])!=(c['subject_id'],c['predicate']):raise Fault('memory_replacement_mismatch')
                replacement=prior['id']
                db.execute("UPDATE memory_claims SET state='superseded',version=version+1,reviewed=?,reviewer=? WHERE id=?",
                           (self.store.now(),p['id'],replacement))
                self.store.log(db,p['scope'],p['id'],'memory.superseded',replacement)
                memory_history.record(db,p['scope'],ledger(db,p),replacement,'superseded',self.store.now(),p['id'],related=c['id'])
            state={'accept':'accepted','supersede':'accepted','dispute':'disputed','withdraw':'withdrawn'}[body['decision']]
            db.execute('UPDATE memory_claims SET state=?,version=version+1,reviewed=?,reviewer=?,replaces_id=? WHERE id=?',
                       (state,self.store.now(),p['id'],replacement,c['id']))
            self.store.log(db,p['scope'],p['id'],'memory.'+state,c['id'])
            memory_history.record(db,p['scope'],ledger(db,p),c['id'],state,self.store.now(),p['id'],
                                  related=replacement if body['decision']=='supersede' else None,
                                  detail='supersede' if body['decision']=='supersede' else None,valid=validity)
        return self.view(bearer)

    def forget(self, bearer, identity, body):
        """Forget one reviewed statement everywhere current retrieval could use it.

        Ordinary by default: a copy waits in the bin and a restore brings it back. With
        `absolute` and the identifier typed back, no restore brings it back."""
        # Value-free history rows are kept unless the owner explicitly asks to purge them (decision 0.3).
        purge,layer=forget_options(body,{'version'},identity)
        if type(body['version']) is not int or body['version'] < 1:
            raise Fault('invalid_memory_review')
        return self._forget(bearer,identity,body['version'],layer,purge)

    def _forget(self, bearer, identity, version, layer, purge, reason=None):
        from . import lifecycle
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            c=self._claim(db,p,identity)
            if c['state']=='forgotten':
                # Asking again returns the receipt, unless an ordinary forget is now made absolute.
                held=self._latest(db,p,'claim_forgotten',identity)
                if layer=='ordinary' or (held is not None and held.get('layer','absolute')=='absolute'):
                    if held is None:raise Fault('memory_claim_not_found',404)
                    return held
            elif c['version']!=version:raise Fault('memory_review_changed',409)
            # Intent is journalled before the database changes, so a restore replays it.
            entry={'kind':'claim_forgotten','scope':p['scope'],'actor':ledger(db,p),'by':p['id'],'subject':identity,'at':self.store.now(),'layer':layer}
            if purge:entry['purge_history']=True
            if reason:entry['reason']=reason
            keep=memory_bin.snapshot(db,p['scope'],[ledger(db,p)],'claim_forgotten',identity) if layer=='ordinary' else None
            lifecycle.append(self.store,entry)
            removed=(['reviewed value','reviewed relationship'] if c['state']!='forgotten'
                     else ['copies in the bin'] if identity in memory_bin.held_claims(db,p['scope']) else [])
            return lifecycle.forget_accounted(self.store,db,p,entry,{'removed':removed,'layer':layer,**({'reason':reason} if reason else {})},
                                              lifecycle.remains(layer),keep=keep)

    def forget_entity(self, bearer, identity, body):
        """Forget an entity's name and every statement that mentions it, in either layer."""
        purge,layer=forget_options(body,set(),identity)
        from . import lifecycle
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            if not db.execute('SELECT 1 FROM memory_entities WHERE id=? AND scope=? AND actor=?',(identity,p['scope'],ledger(db,p))).fetchone():
                held=self._latest(db,p,'entity_forgotten',identity)
                if held is None:raise Fault('memory_entity_not_found',404)
                if layer=='ordinary' or held.get('layer','absolute')=='absolute':return held
            claims=db.execute('SELECT count(*) FROM memory_claims WHERE scope=? AND actor=? AND (subject_id=? OR object_id=?) AND state!=?',
                              (p['scope'],ledger(db,p),identity,identity,'forgotten')).fetchone()[0]
            entry={'kind':'entity_forgotten','scope':p['scope'],'actor':ledger(db,p),'by':p['id'],'subject':identity,'at':self.store.now(),'layer':layer}
            if purge:entry['purge_history']=True
            keep=memory_bin.snapshot(db,p['scope'],[ledger(db,p)],'entity_forgotten',identity) if layer=='ordinary' else None
            lifecycle.append(self.store,entry)
            return lifecycle.forget_accounted(self.store,db,p,entry,{'removed':['entity name',f'{claims} reviewed statement(s)'],'layer':layer},
                                              lifecycle.remains(layer),keep=keep)

    def bin(self, bearer):
        """The owner's bin: ordinary forgets that can still be undone, newest first."""
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            return {'items':memory_bin.items(db,p['scope'],ledger(db,p),self.store.now()),'days':memory_bin.DAYS}

    def undo(self, bearer, identity, body):
        """Put back what an ordinary forget cleared, while its copy is in the bin.

        A statement comes back in the state it had, with its value; a record comes back
        with its name and the statements forgotten with it. Answers and drafts the forget
        withdrew stay withdrawn."""
        exact(body,set());ident(identity)
        from . import lifecycle
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            person,now=ledger(db,p),self.store.now()
            item=memory_bin.take(db,p['scope'],person,identity,now)
            snap=item['snapshot']
            if item['kind']=='entity':
                e=snap['entity']
                if db.execute('SELECT 1 FROM memory_entities WHERE id=?',(e['id'],)).fetchone():
                    raise Fault('memory_entity_id_unavailable',409)
                if db.execute('SELECT count(*) FROM memory_entities WHERE actor=?',(person,)).fetchone()[0]>=MAX_ENTITIES:
                    raise Fault('memory_entity_capacity',409)
                db.execute('INSERT INTO memory_entities VALUES (?,?,?,?,?,?)',(e['id'],p['scope'],person,e['kind'],e['name'],e['created']))
            present={r[0] for r in db.execute('SELECT id FROM memory_entities WHERE scope=? AND actor=?',(p['scope'],person))}
            restored,gone,waiting=0,0,[]
            for c in snap['claims']:
                if c['subject_id'] not in present or (c['object_id'] and c['object_id'] not in present):
                    # A statement cannot come back without the records it names.
                    if item['kind']=='statement':raise Fault('undo_record_first',409)
                    waiting.append(c);continue
                if db.execute("UPDATE memory_claims SET state=?,value=?,object_id=?,version=version+1 WHERE id=? AND scope=? AND actor=? AND state='forgotten'",
                              (c['state'],c['value'],c['object_id'],c['id'],p['scope'],person)).rowcount:
                    restored+=1
                    memory_history.record(db,p['scope'],person,c['id'],c['state'],now,p['id'],detail='undone_from_bin')
                else:gone+=1
            memory_bin.keep(db,p['scope'],item,waiting)
            row=db.execute('SELECT receipt FROM lifecycle_receipts WHERE id=?',(item['receipt'],)).fetchone()
            receipt=json.loads(row['receipt']) if row else {}
            if row:
                db.execute('UPDATE lifecycle_receipts SET receipt=? WHERE id=?',(json.dumps(receipt|{'undone_at':now}),item['receipt']))
            self.store.log(db,p['scope'],p['id'],'lifecycle.forget_undone',item['subject'])
            # Last, so a failed write leaves the forget in place; a restore then knows it was undone.
            lifecycle.append(self.store,{'kind':'forget_undone','undoes':memory_bin.FORGET[item['kind']],'scope':p['scope'],'actor':person,
                                         'by':p['id'],'subject':item['subject'],'at':now})
        left=[WITHDRAWN]+(['Review history rows purged with the forget stay purged.'] if receipt.get('history')=='purged' else [])
        if gone:left.append(f'{gone} statement(s) were back already or no longer exist.')
        if waiting:left.append(f'{len(waiting)} statement(s) name a record that is still forgotten. They stay in the bin: undo that record, then them.')
        return {'kind':item['kind'],'subject':item['subject'],'statements_restored':restored,'statements_not_restored':gone+len(waiting),
                'not_restored':left}

    def empty_bin(self, bearer):
        """Remove copies whose 30 days have passed. Returns how many went."""
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            gone=memory_bin.expire(db,p['scope'],self.store.now())
            for subject in gone:
                self.store.log(db,p['scope'],p['id'],'lifecycle.bin_emptied',subject)
        return len(gone)

    @staticmethod
    def _latest(db,p,kind,subject):
        row=db.execute('SELECT receipt FROM lifecycle_receipts WHERE scope=? AND actor=? AND kind=? AND subject=? ORDER BY at DESC,rowid DESC LIMIT 1',
                       (p['scope'],ledger(db,p),kind,subject)).fetchone()
        return json.loads(row['receipt']) if row else None

    @classmethod
    def _claims(cls, db, p, now):
        """One currentness/conflict rule for review, retrieval and final checks."""
        claims=[]
        person=ledger(db,p)
        # A review made on any device of this person counts; the reviewer stays the device credential.
        reviewers=person_credentials(db,person)|{p['id']}
        for row in db.execute('SELECT * FROM memory_claims WHERE scope=? AND actor=? ORDER BY created DESC,id',(p['scope'],person)):
            c=dict(row)
            c.pop('request_hash');c.pop('request_id');c.pop('scope');c.pop('actor')
            c['source']=None
            if c['state']!='invalidated' and (c['value'] is not None or c['object_id'] is not None):
                try:
                    source=cls._source(db,p['scope'],cls._ref(c),now,p)
                    if source['quote_hash']==c['quote_hash']:c['source']=source
                except Fault:pass
            c['valid_now']=(c['valid_from'] is None or c['valid_from']<=now) and (c['valid_until'] is None or c['valid_until']>now)
            c['conflicts']=[];claims.append(c)
        for c in claims:
            if c['state']!='accepted' or not c['source'] or not RELATIONS[c['predicate']]['single']:continue
            for other in claims:
                if other['id']!=c['id'] and other['state']=='accepted' and other['source'] and (other['subject_id'],other['predicate'])==(c['subject_id'],c['predicate']) and (other['object_id'],other['value'])!=(c['object_id'],c['value']) and overlap(c,other):
                    c['conflicts'].append(other['id'])
        for c in claims:
            c['usable']=(c['state']=='accepted' and c['valid_now'] and bool(c['source'])
                         and c['reviewed'] is not None and c['reviewer'] in reviewers and not c['conflicts'])
        return claims

    def _snapshot(self, db, p, now):
        """Reconciled entities and claims with withheld values removed, in the caller's
        transaction. The reviewed-memory view, history and as-of report all read this."""
        self._reconcile(db,p)
        entities=[dict(r) for r in db.execute('SELECT id,kind,name,created FROM memory_entities WHERE scope=? AND actor=? ORDER BY created,id',(p['scope'],ledger(db,p)))]
        claims=self._claims(db,p,now)
        captures={r['claim_id']:dict(r) for r in db.execute('SELECT m.* FROM memory_capture m JOIN memory_claims c ON c.id=m.claim_id WHERE c.scope=? AND c.actor=?',(p['scope'],ledger(db,p)))}
        for c in claims:
            m=captures.get(c['id'])
            c['memory_type'],c['retention_until']=(m['memory_type'],m['retention_until']) if m else (None,None)
        for c in claims:
            # Support that is unavailable or no longer permitted is withheld, and so is
            # what was derived from it. Restored access or availability restores both.
            c['withheld']=c['state']!='invalidated' and c['source'] is None and (c['value'] is not None or c['object_id'] is not None)
            if c['withheld']:c['value']=None;c['object_id']=None
        memory_history.observe(db,p,claims,now)
        return {e['id']:e for e in entities},claims

    def view(self, bearer):
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner','reader'})
            entities,claims=self._snapshot(db,p,self.store.now())
            entities=list(entities.values())
            return {'entities':entities,'claims':claims,'scope':p['scope'],'actor_private':True,
                    'basis':'user_reviewed_statements_not_verified_facts','model_extraction':False,
                    'counts':{'proposed':sum(c['state']=='proposed' for c in claims),'usable':sum(c['usable'] for c in claims),
                              'conflicted':sum(bool(c['conflicts']) for c in claims)},
                    'graph':{'nodes':entities,'edges':[{'source':c['subject_id'],'target':c['object_id'],'predicate':c['predicate'],'claim_id':c['id']} for c in claims if c['usable'] and c['object_id']]},
                    'limits':{'entities':MAX_ENTITIES,'claims':MAX_CLAIMS},'authority_granted':False}


def context_reference(statement):
    source=statement['support']
    return {'claim_id':statement['claim_id'],'version':statement['version'],
            **{k:source[k] for k in CONTEXT_REF_KEYS-{'claim_id','version'}}}


def context_references(packet):
    return [context_reference(c) for c in packet.get('memory',[])]


def context_statement(claim, entities, source_id):
    """A labelled review judgement with its original support, never authority."""
    def entity(identity):
        return {k:entities[identity][k] for k in ('id','kind','name')}
    return {'claim_id':claim['id'],'version':claim['version'],
            'subject':entity(claim['subject_id']), 'predicate':claim['predicate'],
            'object':entity(claim['object_id']) if claim['object_id'] else None, 'value':claim['value'],
            'valid_from':claim['valid_from'],'valid_until':claim['valid_until'],
            'recorded':claim['created'],'reviewed':claim['reviewed'],'review_state':'accepted',
            'replaces_id':claim['replaces_id'],
            'support':{'source_id':source_id,**{k:claim['source'][k] for k in
                       ('note_id','sha256','revision','start_line','end_line','quote_hash')}},
            'basis':'user_reviewed_statement_not_verified_fact','authority_granted':False}


def context_ambiguities(entities, statements):
    ambiguities=[];seen=set()
    for m in statements:
        for e in (m['subject'],m['object']):
            if e is None:continue
            key=(e['kind'],e['name'].casefold())
            if key in seen:continue
            seen.add(key)
            same=sorted(x['id'] for x in entities.values() if (x['kind'],x['name'].casefold())==key)
            if len(same)>1:ambiguities.append({'name':e['name'],'kind':e['kind'],'entity_ids':same[:8],'more_entities':len(same)>8})
    return ambiguities


def ambiguities_current_db(db, p, statements, expected):
    if not statements:return not expected
    entities={r['id']:dict(r) for r in db.execute('SELECT id,kind,name FROM memory_entities WHERE scope=? AND actor=?',(p['scope'],ledger(db,p)))}
    return context_ambiguities(entities,statements)==expected


def context_current_db(db, p, refs, now):
    """Validate review, conflict, temporal and source state in the caller's transaction.

    Returns reconstructed current statements, or None for a stale/foreign binding.
    Empty bindings preserve pre-M03 source-only conversations and action receipts.
    """
    if type(refs) is not list or len(refs)>MAX_CONTEXT_CLAIMS:
        raise Fault('invalid_memory_references')
    for ref in refs:
        exact(ref,CONTEXT_REF_KEYS);ident(ref['claim_id'])
        if type(ref['version']) is not int or ref['version']<1:
            raise Fault('invalid_memory_review_version')
        if type(ref['quote_hash']) is not str or len(ref['quote_hash'])!=64 or any(c not in '0123456789abcdef' for c in ref['quote_hash']):
            raise Fault('invalid_memory_quote_hash')
        # Validate source reference types even when the claim is no longer present.
        ident(ref['note_id'])
        if type(ref['sha256']) is not str or len(ref['sha256'])!=64 or any(c not in '0123456789abcdef' for c in ref['sha256']):
            raise Fault('invalid_memory_source_hash')
        if type(ref['revision']) is not int or ref['revision']<1:
            raise Fault('invalid_memory_source_revision')
        first,last=ref['start_line'],ref['end_line']
        if type(first) is not int or type(last) is not int or not 1<=first<=last or last-first>=8:
            raise Fault('invalid_memory_source_range')
    if not refs:return []
    if len({r['claim_id'] for r in refs})!=len(refs):raise Fault('duplicate_memory_reference')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_claims'").fetchone():return None
    claims={c['id']:c for c in ReviewedMemory._claims(db,p,now)}
    entities={r['id']:dict(r) for r in db.execute('SELECT id,kind,name FROM memory_entities WHERE scope=? AND actor=?',(p['scope'],ledger(db,p)))}
    current=[]
    for ref in refs:
        c=claims.get(ref['claim_id'])
        if not c or not c['usable'] or c['subject_id'] not in entities or (c['object_id'] and c['object_id'] not in entities):return None
        statement=context_statement(c,entities,'')
        if context_reference(statement)!=ref:return None
        current.append(statement)
    return current
