"""Actor-private, bounded conversations over the existing source/authority layer.

No model tools. Jobs retain bearer authority in process memory only. Pending work
is interrupted on host restart, never silently re-issued. Default retention: 24h.
"""
from __future__ import annotations
import json
import queue
import secrets
import threading
import time
from .local import Fault, exact, ident, text, fingerprint, canonical
from .grounded import retrieve, question_terms, references, check_sources, validate_interpretation

SCHEMA = '''
CREATE TABLE IF NOT EXISTS conversation_meta(version INTEGER NOT NULL);
INSERT INTO conversation_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM conversation_meta);
CREATE TABLE IF NOT EXISTS conversations(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, title TEXT NOT NULL,
 created INTEGER NOT NULL, updated INTEGER NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_turns(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 question TEXT NOT NULL, mode TEXT NOT NULL, follow_up INTEGER NOT NULL,
 state TEXT NOT NULL, created INTEGER NOT NULL, completed INTEGER, result TEXT,
 UNIQUE(session,ordinal), UNIQUE(session,request_id));
CREATE TABLE IF NOT EXISTS conversation_action_sources(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, session TEXT NOT NULL, turn_id TEXT NOT NULL,
 references_json TEXT NOT NULL, PRIMARY KEY(scope,action_id));
'''
TTL = 86400
MAX_SESSIONS, MAX_TURNS = 24, 40


def refs_current_db(db, scope, refs, now):
    """Check source authority/revisions in the SAME transaction as action approval."""
    if not refs or len(refs) > 5:
        return False
    for ref in refs:
        row = db.execute('''SELECT n.sha256,n.revision FROM knowledge_notes n
          JOIN credentials c ON c.id=n.source AND c.scope=n.scope
          JOIN knowledge_sources s ON s.source=n.source AND s.scope=n.scope
          WHERE n.scope=? AND n.id=? AND n.status='ready' AND c.revoked=0
          AND c.expires>? AND s.status IN ('ready','attention')''',
          (scope, ref['note_id'], now)).fetchone()
        if not row or row['sha256'] != ref['sha256'] or row['revision'] != ref['revision']:
            return False
    return True


def knowledge_action_current(store, db, row):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_action_sources'").fetchone():
        return False
    link = db.execute('SELECT * FROM conversation_action_sources WHERE scope=? AND action_id=?',
                      (row['scope'], row['id'])).fetchone()
    if not link:
        return False
    active = db.execute('SELECT 1 FROM conversations WHERE id=? AND scope=? AND actor=? AND expires>?',
                        (link['session'], row['scope'], row['actor'], store.now())).fetchone()
    return bool(active) and refs_current_db(db, row['scope'], json.loads(link['references_json']), store.now())


class ConversationService:
    def __init__(self, store, provider=None, provider_scope=None):
        self.store, self.provider, self.provider_scope = store, provider, provider_scope
        self.jobs = queue.Queue(maxsize=8)
        self.lock, self.stop_event = threading.RLock(), threading.Event()
        self.thread = None
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM conversation_meta')] != [1]:
                raise Fault('unsupported_conversation_version')

    def cleanup(self, db):
        # Deletes application rows, not secure erasure of WAL/backups/filesystem.
        dead = [r[0] for r in db.execute('''SELECT s.id FROM conversations s JOIN credentials c ON c.id=s.actor
          WHERE s.expires<=? OR c.revoked=1 OR c.expires<=?''', (self.store.now(), self.store.now()))]
        for sid in dead:
            db.execute('DELETE FROM conversation_action_sources WHERE session=?', (sid,))
            db.execute('DELETE FROM conversations WHERE id=?', (sid,))

    def own(self, db, bearer, sid):
        ident(sid)
        p = self.store.authenticate(db, bearer, {'owner','reader'})
        row = db.execute('SELECT * FROM conversations WHERE id=? AND scope=? AND actor=? AND expires>?',
                         (sid,p['scope'],p['id'],self.store.now())).fetchone()
        if not row:
            raise Fault('conversation_not_found',404)
        return p,row

    def create(self, bearer, body):
        exact(body, {'title'}); text(body['title'], 100)
        with self.store.transaction() as db:
            p = self.store.authenticate(db,bearer,{'owner','reader'}); self.cleanup(db)
            if db.execute('SELECT count(*) FROM conversations WHERE scope=? AND actor=?',(p['scope'],p['id'])).fetchone()[0] >= MAX_SESSIONS:
                raise Fault('conversation_capacity',409)
            sid = 'chat-' + secrets.token_hex(12); now=self.store.now()
            db.execute('INSERT INTO conversations VALUES (?,?,?,?,?,?,?)',(sid,p['scope'],p['id'],body['title'],now,now,now+TTL))
        return self.view(bearer,sid)

    def listing(self,bearer):
        with self.store.transaction() as db:
            p=self.store.authenticate(db,bearer,{'owner','reader'});self.cleanup(db)
            sessions=[dict(r) for r in db.execute('SELECT id,title,created,updated,expires FROM conversations WHERE scope=? AND actor=? ORDER BY updated DESC,id',(p['scope'],p['id']))]
        return {'sessions':sessions,'retention_seconds':TTL,'model_configured':self.provider is not None,
                'model':self.provider.model if self.provider else None,
                'model_allowed':p['role']=='owner' and p['scope']==self.provider_scope,'tools_enabled':False}

    def forget(self,bearer,sid):
        with self.store.transaction() as db:
            self.own(db,bearer,sid)
            db.execute('DELETE FROM conversation_action_sources WHERE session=?',(sid,))
            db.execute('DELETE FROM conversations WHERE id=?',(sid,))
        return {'forgotten':True,'secure_erasure':False,'approved_drafts_undone':False}

    def submit(self,bearer,sid,body):
        exact(body,{'question','mode','follow_up','request_id','after'})
        question_terms(body['question']);ident(body['request_id'])
        if body['mode'] not in {'sources','local_model'} or type(body['follow_up']) is not bool or type(body['after']) is not int or body['after']<0:
            raise Fault('invalid_conversation_request')
        request_hash=fingerprint(body)
        with self.lock:
            if self.stop_event.is_set():raise Fault('conversation_worker_stopped',409)
            with self.store.transaction() as db:
                p,row=self.own(db,bearer,sid)
                if self.store.paused(p['scope']):raise Fault('conversation_processing_paused',409)
                previous=db.execute('SELECT id,request_hash,state FROM conversation_turns WHERE session=? AND request_id=?',(sid,body['request_id'])).fetchone()
                if previous:
                    if previous['request_hash']!=request_hash:raise Fault('conversation_request_collision',409)
                    return {'turn_id':previous['id'],'state':previous['state'],'reused':True}
                count=db.execute('SELECT count(*) FROM conversation_turns WHERE session=?',(sid,)).fetchone()[0]
                if count>=MAX_TURNS:raise Fault('conversation_turn_capacity',409)
                if count!=body['after']:raise Fault('conversation_changed',409)
                if db.execute("SELECT 1 FROM conversation_turns WHERE session=? AND state IN ('queued','running')",(sid,)).fetchone():
                    raise Fault('conversation_busy',409)
                if body['mode']=='local_model':
                    if self.provider is None:raise Fault('local_model_not_configured',409)
                    if p['role']!='owner' or p['scope']!=self.provider_scope:raise Fault('model_workspace_not_authorised',403)
                if self.jobs.full():raise Fault('conversation_queue_full',429)
                # Also cap starts independently of the session count.
                if db.execute('''SELECT count(*) FROM conversation_turns t JOIN conversations s ON s.id=t.session
                    WHERE s.actor=? AND t.created>?''',(p['id'],self.store.now()-60)).fetchone()[0]>=6:
                    raise Fault('conversation_rate_limited',429)
                tid='turn-'+secrets.token_hex(12)
                db.execute('INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (tid,sid,count+1,body['request_id'],request_hash,body['question'].strip(),body['mode'],int(body['follow_up']),
                            'queued',self.store.now(),None,None))
                db.execute('UPDATE conversations SET updated=? WHERE id=?',(self.store.now(),sid))
            self.jobs.put_nowait((bearer,sid,tid))
        return {'turn_id':tid,'state':'queued','reused':False}

    def recover(self):
        with self.store.transaction() as db:
            self.cleanup(db)
            db.execute("UPDATE conversation_turns SET state='interrupted',completed=?,result=NULL WHERE state IN ('queued','running')",(self.store.now(),))

    def start(self):
        if self.thread is not None:return
        self.recover()
        self.thread=threading.Thread(target=self.loop,name='alfred-conversation',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=1)
        while True:
            try: _,_,tid=self.jobs.get_nowait();self.finish_error(tid,'interrupted');self.jobs.task_done()
            except queue.Empty:break

    def loop(self):
        last_cleanup=0.0
        while not self.stop_event.is_set():
            if time.monotonic()-last_cleanup>30:
                with self.store.transaction() as db: self.cleanup(db)
                last_cleanup=time.monotonic()
            if not self.process_one():self.stop_event.wait(.1)

    def finish_error(self,tid,state):
        with self.store.transaction() as db:
            db.execute("UPDATE conversation_turns SET state=?,completed=?,result=NULL WHERE id=? AND state IN ('queued','running')",(state,self.store.now(),tid))

    def process_one(self):
        try: bearer,sid,tid=self.jobs.get_nowait()
        except queue.Empty:return False
        try:
            with self.store.transaction() as db:
                p,_=self.own(db,bearer,sid)
                row=db.execute('SELECT * FROM conversation_turns WHERE id=?',(tid,)).fetchone()
                if not row or row['state']!='queued':return True
                history=[dict(r) for r in db.execute('SELECT question,follow_up FROM conversation_turns WHERE session=? AND ordinal<? ORDER BY ordinal DESC LIMIT 3',(sid,row['ordinal']))]
                db.execute("UPDATE conversation_turns SET state='running' WHERE id=?",(tid,))
                current=dict(row)
            if self.store.paused(p['scope']):raise Fault('conversation_processing_paused')
            question=current['question']
            # A user-selected new topic is a hard boundary for later follow-ups.
            bounded=[]
            if current['follow_up']:
                for item in history:
                    bounded.append(item)
                    if not item['follow_up']:break
            history=list(reversed(bounded))
            # User-selected continuity. Prior questions orient retrieval; previous
            # generated claims are NEVER promoted to source evidence.
            previous_terms=[]
            for item in history:previous_terms.extend(question_terms(item['question']))
            prefix=' '.join(dict.fromkeys(previous_terms))[:min(180,max(0,499-len(question)))]
            contextual=(prefix+' '+question).strip() if prefix else question
            packet=retrieve(self.store,bearer,contextual);packet['question']=question
            packet['conversation_questions']=[h['question'] for h in history]
            packet['retrieval_question']=contextual
            result={'packet':packet,'claims':[],'mode':current['mode'],'model_used':False,'model':None,
                    'status':'sources_found' if packet['evidence'] else 'no_sources','actions_executed':False,
                    'semantic_entailment_verified':False,'content_sent_to_model':False,'usage':None}
            started=time.monotonic()
            if current['mode']=='local_model' and packet['evidence']:
                principal=self.store.principal(bearer,{'owner'})
                if self.provider is None or principal['scope']!=self.provider_scope:raise Fault('model_workspace_not_authorised')
                if not check_sources(self.store,bearer,references(packet))['current_index_match']:raise Fault('sources_changed')
                result['content_sent_to_model']=True
                value=self.provider.generate(packet)
                result['claims']=validate_interpretation(value,packet)
                result.update(model_used=True,model=self.provider.model,status='model_interpretation' if result['claims'] else 'model_abstained',
                              usage=getattr(self.provider,'last_usage',None))
            result['elapsed_ms']=round((time.monotonic()-started)*1000)
            if self.stop_event.is_set():raise Fault('conversation_worker_stopped')
            with self.store.transaction() as db:
                principal,_=self.own(db,bearer,sid)
                paused=db.execute('SELECT paused FROM desk_settings WHERE scope=?',(principal['scope'],)).fetchone()
                if paused and paused[0]:raise Fault('conversation_processing_paused')
                if packet['evidence'] and not refs_current_db(db,principal['scope'],references(packet),self.store.now()):raise Fault('sources_changed')
                # Persist references, not another copy of source passages/quotes.
                stored=json.loads(json.dumps(result))
                for source in stored['packet']['evidence']:source.pop('excerpt',None)
                for claim in stored['claims']:
                    for cite in claim['citations']:cite.pop('quote',None)
                db.execute("UPDATE conversation_turns SET state='completed',completed=?,result=? WHERE id=? AND state='running'",(self.store.now(),json.dumps(stored),tid))
        except Exception as exc:
            state='source_changed' if isinstance(exc,Fault) and exc.code in {'sources_changed','sources_changed_during_question'} else 'failed'
            self.finish_error(tid,state)
        finally:self.jobs.task_done()
        return True

    def view(self,bearer,sid):
        with self.store.transaction() as db:
            p,session=self.own(db,bearer,sid)
            rows=[dict(r) for r in db.execute('SELECT id,ordinal,question,mode,follow_up,state,created,completed,result FROM conversation_turns WHERE session=? ORDER BY ordinal',(sid,))]
            for turn in rows:
                if not turn['result']:continue
                result=json.loads(turn['result']);sources=result['packet']['evidence']
                if sources and not refs_current_db(db,p['scope'],references(result['packet']),self.store.now()):
                    # Remove stale interpretations from active application storage.
                    db.execute("UPDATE conversation_turns SET state='source_changed',result=NULL WHERE id=?",(turn['id'],))
                    turn['state'],turn['result']='source_changed',None;continue
                for source in sources:
                    note=db.execute('SELECT body FROM knowledge_notes WHERE scope=? AND id=?',(p['scope'],source['note_id'])).fetchone()
                    source['excerpt']='\n'.join(note['body'].splitlines()[source['start_line']-1:source['end_line']])
                turn['result']=result
            return {'id':sid,'title':session['title'],'expires':session['expires'],'turns':rows,'retention_seconds':TTL,
                    'private_to_current_credential':True,'role':p['role'],'actions_executed_by_conversation':False}

    def propose_draft(self,bearer,sid,body):
        exact(body,{'turn_id','text','request_id'});ident(body['turn_id']);ident(body['request_id']);text(body['text'])
        with self.store.transaction() as db:
            p,session=self.own(db,bearer,sid)
            if p['role']!='owner':raise Fault('forbidden',403)
            row=db.execute('SELECT * FROM conversation_turns WHERE session=? AND id=?',(sid,body['turn_id'])).fetchone()
            if not row or row['state']!='completed' or not row['result']:raise Fault('conversation_result_required',409)
            refs=references(json.loads(row['result'])['packet'])
            if not refs_current_db(db,p['scope'],refs,self.store.now()):raise Fault('evidence_not_current',409)
            aid=body['request_id'];params={'text':body['text']}
            existing=db.execute('SELECT * FROM actions WHERE scope=? AND id=?',(p['scope'],aid)).fetchone()
            if existing:
                link=db.execute('SELECT * FROM conversation_action_sources WHERE scope=? AND action_id=?',(p['scope'],aid)).fetchone()
                if not link or link['session']!=sid or link['turn_id']!=row['id'] or existing['actor']!=p['id'] or json.loads(existing['parameters'])!=params:
                    raise Fault('action_id_collision',409)
                return self.store.action_view(existing)
            if db.execute('SELECT count(*) FROM actions WHERE scope=?',(p['scope'],)).fetchone()[0]>=5000:raise Fault('action_capacity',409)
            expiry=min(self.store.now()+900,session['expires'])
            bound={'id':aid,'scope':p['scope'],'actor':p['id'],'capability':'message.draft','parameters':params,'expires_at':expiry,'sources':refs,'turn':row['id']}
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)',(p['scope'],aid,p['id'],'message.draft',canonical(params),fingerprint(bound),expiry,'proposed',self.store.now(),None))
            db.execute('INSERT INTO conversation_action_sources VALUES (?,?,?,?,?)',(p['scope'],aid,sid,row['id'],json.dumps(refs)))
            self.store.log(db,p['scope'],p['id'],'action.proposed_from_conversation',aid)
            return self.store.action_view(db.execute('SELECT * FROM actions WHERE scope=? AND id=?',(p['scope'],aid)).fetchone())
