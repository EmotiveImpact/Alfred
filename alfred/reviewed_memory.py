"""Reviewed, actor-private statements over indexed evidence, not automated truth.

Entities are explicitly created, never merged by name. Review records a user's
judgement; it grants no device/tool authority. Source slices are reconstructed,
not duplicated. Invalidated statement values are cleared on reconciliation.
"""
from __future__ import annotations
import hashlib
import json
import secrets
from .local import Fault, exact, ident, text, timestamp, fingerprint

KINDS = ('person', 'organisation', 'project', 'asset', 'decision', 'commitment', 'event')
RELATIONS = {
    'responsible_person': {'objects': ('person',), 'single': True},
    'depends_on': {'objects': KINDS, 'single': False},
    'status': {'objects': (), 'single': True},
    'scheduled_for': {'objects': (), 'single': True},
    'decision': {'objects': (), 'single': True},
}
MAX_ENTITIES, MAX_CLAIMS = 128, 256
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
'''


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

    @staticmethod
    def _entity(db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM memory_entities WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('memory_entity_not_found', 404)
        return dict(row)

    @staticmethod
    def _claim(db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM memory_claims WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('memory_claim_not_found', 404)
        return dict(row)

    def _source(self, db, scope, ref):
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
        n = db.execute('''SELECT n.* FROM knowledge_notes n
          JOIN knowledge_sources s ON n.scope=s.scope AND n.source=s.source
          JOIN credentials c ON c.scope=n.scope AND c.id=n.source
          WHERE n.scope=? AND n.id=? AND n.status='ready' AND s.status IN ('ready','attention')
          AND c.role='source' AND c.revoked=0 AND c.expires>?''',
          (scope, ref['note_id'], self.store.now())).fetchone()
        if not n or n['sha256'] != ref['sha256'] or n['revision'] != ref['revision']:
            raise Fault('memory_source_changed', 409)
        lines = n['body'].splitlines()
        if last > len(lines):
            raise Fault('invalid_memory_source_range')
        quote = '\n'.join(lines[first-1:last])
        if not quote.strip() or len(quote) > 1400:
            raise Fault('memory_source_excerpt_capacity')
        return {'note_id':n['id'], 'path':n['path'], 'title':n['title'], 'sha256':n['sha256'],
                'revision':n['revision'], 'start_line':first, 'end_line':last, 'quote':quote,
                'quote_hash':hashlib.sha256(quote.encode()).hexdigest()}

    @staticmethod
    def _ref(c):
        return {'note_id':c['note_id'], 'sha256':c['note_hash'], 'revision':c['note_revision'],
                'start_line':c['first_line'], 'end_line':c['last_line']}

    def _reconcile(self, db, p):
        for row in db.execute("SELECT * FROM memory_claims WHERE scope=? AND actor=? AND state!='invalidated' AND (value IS NOT NULL OR object_id IS NOT NULL)",
                              (p['scope'], p['id'])).fetchall():
            c=dict(row)
            try:
                source=self._source(db,p['scope'],self._ref(c))
                valid=source['quote_hash']==c['quote_hash']
            except Fault:
                valid=False
            if not valid:
                db.execute("UPDATE memory_claims SET state='invalidated',value=NULL,object_id=NULL,version=version+1 WHERE id=?",(c['id'],))
                self.store.log(db,p['scope'],p['id'],'memory.invalidated',c['id'])

    def create_entity(self, bearer, body):
        exact(body, {'id','kind','name'});ident(body['id']);text(body['name'],120)
        if type(body['kind']) is not str or body['kind'] not in KINDS or not body['name'].strip():
            raise Fault('invalid_memory_entity')
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'})
            existing=db.execute('SELECT * FROM memory_entities WHERE id=?',(body['id'],)).fetchone()
            if existing:
                if (existing['scope'],existing['actor'],existing['kind'],existing['name'])!=(p['scope'],p['id'],body['kind'],body['name'].strip()):
                    raise Fault('memory_entity_id_unavailable',409)
                return {'id':body['id'],'reused':True}
            if db.execute('SELECT count(*) FROM memory_entities WHERE actor=?',(p['id'],)).fetchone()[0]>=MAX_ENTITIES:
                raise Fault('memory_entity_capacity',409)
            db.execute('INSERT INTO memory_entities VALUES (?,?,?,?,?,?)',
                       (body['id'],p['scope'],p['id'],body['kind'],body['name'].strip(),self.store.now()))
            self.store.log(db,p['scope'],p['id'],'memory.entity_created',body['id'])
        return {'id':body['id'],'reused':False}

    def propose(self, bearer, body):
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
                           (p['scope'],p['id'],body['request_id'])).fetchone()
            if old:
                if old['request_hash']!=digest:raise Fault('memory_request_collision',409)
                return {'id':old['id'],'state':old['state'],'reused':True}
            self._entity(db,p,body['subject_id'])
            if body['object_id']:
                other=self._entity(db,p,body['object_id'])
                if other['kind'] not in relation['objects']:raise Fault('memory_object_kind')
                if body['subject_id']==body['object_id']:raise Fault('memory_self_relation')
            source=self._source(db,p['scope'],body['evidence'])
            if db.execute('SELECT count(*) FROM memory_claims WHERE actor=?',(p['id'],)).fetchone()[0]>=MAX_CLAIMS:
                raise Fault('memory_claim_capacity',409)
            cid='claim-'+secrets.token_hex(12)
            db.execute('INSERT INTO memory_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (cid,p['scope'],p['id'],body['request_id'],digest,body['subject_id'],body['predicate'],
                        body['object_id'],body['value'].strip() if body['value'] else None,body['valid_from'],body['valid_until'],
                        source['note_id'],source['sha256'],source['revision'],source['start_line'],source['end_line'],
                        source['quote_hash'],'proposed',1,self.store.now(),None,None,None))
            self.store.log(db,p['scope'],p['id'],'memory.proposed',cid)
        return {'id':cid,'state':'proposed','reused':False}

    def review(self, bearer, identity, body):
        exact(body, {'version','decision','replaces_id','replaces_version'})
        if type(body['version']) is not int or body['version'] < 1 or body['decision'] not in ('accept','dispute','withdraw','supersede'):
            raise Fault('invalid_memory_review')
        if body['decision']!='supersede' and (body['replaces_id'] is not None or body['replaces_version'] is not None):
            raise Fault('unexpected_memory_replacement')
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner'});self._reconcile(db,p)
            c=self._claim(db,p,identity)
            if c['state']=='invalidated':raise Fault('memory_source_changed',409)
            if c['version']!=body['version']:raise Fault('memory_review_changed',409)
            if c['state'] not in ('proposed','accepted','disputed'):raise Fault('memory_review_closed',409)
            self._source(db,p['scope'],self._ref(c))
            replacement=c['replaces_id']
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
            state={'accept':'accepted','supersede':'accepted','dispute':'disputed','withdraw':'withdrawn'}[body['decision']]
            db.execute('UPDATE memory_claims SET state=?,version=version+1,reviewed=?,reviewer=?,replaces_id=? WHERE id=?',
                       (state,self.store.now(),p['id'],replacement,c['id']))
            self.store.log(db,p['scope'],p['id'],'memory.'+state,c['id'])
        return self.view(bearer)

    def view(self, bearer):
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner','reader'});self._reconcile(db,p)
            entities=[dict(r) for r in db.execute('SELECT id,kind,name,created FROM memory_entities WHERE scope=? AND actor=? ORDER BY created,id',(p['scope'],p['id']))]
            claims=[];now=self.store.now()
            for row in db.execute('SELECT * FROM memory_claims WHERE scope=? AND actor=? ORDER BY created DESC,id',(p['scope'],p['id'])):
                c=dict(row)
                c.pop('request_hash');c.pop('request_id');c.pop('scope');c.pop('actor')
                c['source']=None
                if c['state']!='invalidated' and (c['value'] is not None or c['object_id'] is not None):
                    try:c['source']=self._source(db,p['scope'],self._ref(c))
                    except Fault:pass
                c['valid_now']=(c['valid_from'] is None or c['valid_from']<=now) and (c['valid_until'] is None or c['valid_until']>now)
                c['conflicts']=[];claims.append(c)
            for c in claims:
                if c['state']!='accepted' or not RELATIONS[c['predicate']]['single']:continue
                for other in claims:
                    if other['id']!=c['id'] and other['state']=='accepted' and (other['subject_id'],other['predicate'])==(c['subject_id'],c['predicate']) and (other['object_id'],other['value'])!=(c['object_id'],c['value']) and overlap(c,other):
                        c['conflicts'].append(other['id'])
            for c in claims:
                c['usable']=c['state']=='accepted' and c['valid_now'] and bool(c['source']) and not c['conflicts']
            return {'entities':entities,'claims':claims,'scope':p['scope'],'actor_private':True,
                    'basis':'user_reviewed_statements_not_verified_facts','model_extraction':False,
                    'counts':{'proposed':sum(c['state']=='proposed' for c in claims),'usable':sum(c['usable'] for c in claims),
                              'conflicted':sum(bool(c['conflicts']) for c in claims)},
                    'graph':{'nodes':entities,'edges':[{'source':c['subject_id'],'target':c['object_id'],'predicate':c['predicate'],'claim_id':c['id']} for c in claims if c['usable'] and c['object_id']]},
                    'limits':{'entities':MAX_ENTITIES,'claims':MAX_CLAIMS},'authority_granted':False}
