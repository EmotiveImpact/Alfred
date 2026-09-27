"""Bounded, opt-in local routines. No prompts, shell commands or external effects.

History is a historical report, not a current-state assertion. The existing foreground
supervisor owns execution. This module does not install an OS service or run off-device.
"""
from __future__ import annotations
import hashlib
import json
from .local import Fault, exact, ident

ROUTINES = {
    'memory-health': ('Memory check', 'Check indexed notes, broken links and map coverage.', 900),
    'briefing-refresh': ('Briefing refresh', 'Count current reports and outstanding local decisions.', 3600),
}
INTERVALS = {60, 300, 900, 3600, 86400}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS pulse_meta(version INTEGER NOT NULL);
INSERT INTO pulse_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM pulse_meta);
CREATE TABLE IF NOT EXISTS pulse_routines(
 scope TEXT NOT NULL, id TEXT NOT NULL, actor TEXT NOT NULL, enabled INTEGER NOT NULL,
 interval_seconds INTEGER NOT NULL, next_due INTEGER NOT NULL, last_error TEXT,
 PRIMARY KEY(scope,id));
CREATE TABLE IF NOT EXISTS pulse_runs(
 scope TEXT NOT NULL, id TEXT NOT NULL, routine TEXT NOT NULL, actor TEXT NOT NULL,
 started INTEGER NOT NULL, finished INTEGER, status TEXT NOT NULL, summary TEXT,
 PRIMARY KEY(scope,id));
CREATE INDEX IF NOT EXISTS pulse_run_time ON pulse_runs(scope,started);
'''


class Pulse:
    """Two fixed read-only reports with durable due slots, limits and run records."""
    def __init__(self, store, supervisor):
        self.store, self.supervisor = store, supervisor
        self.scope = supervisor.scope
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM pulse_meta')] != [1]:
                raise Fault('unsupported_pulse_version')
        with store.transaction() as db:
            p = store.authenticate(db, supervisor.owner, {'owner'})
            for routine, (_, _, interval) in ROUTINES.items():
                db.execute('INSERT OR IGNORE INTO pulse_routines VALUES (?,?,?,?,?,?,?)',
                           (self.scope, routine, p['id'], 0, interval, 0, None))

    def _principal(self, bearer, roles={'owner'}):
        p = self.store.principal(bearer, roles)
        if p['scope'] != self.scope:
            raise Fault('pulse_not_configured', 409)
        return p

    @staticmethod
    def _routine(identity):
        if identity not in ROUTINES:
            raise Fault('unknown_routine', 404)

    def configure(self, bearer, identity, body):
        self._routine(identity)
        exact(body, {'enabled', 'interval_seconds'})
        if type(body['enabled']) is not bool or type(body['interval_seconds']) is not int or body['interval_seconds'] not in INTERVALS:
            raise Fault('invalid_routine_configuration')
        with self.supervisor.lock, self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            if p['scope'] != self.scope: raise Fault('pulse_not_configured', 409)
            # The running node only has its provisioned owner credential. Do not
            # claim it can run under a different device/user's bearer.
            if p['id'] != self.supervisor.principal['id']:
                raise Fault('routine_owner_not_hosted', 403)
            next_due = self.store.now() + body['interval_seconds'] if body['enabled'] else 0
            db.execute('UPDATE pulse_routines SET enabled=?,interval_seconds=?,next_due=?,actor=?,last_error=NULL WHERE scope=? AND id=?',
                       (int(body['enabled']),body['interval_seconds'],next_due,p['id'],self.scope,identity))
            self.store.log(db,self.scope,p['id'],'pulse.configured',identity)
        return self.view(bearer)

    def view(self, bearer):
        p = self.store.principal(bearer, {'owner', 'reader'})
        if p['scope'] != self.scope:
            return {'configured':False,'routines':[],'runs':[], 'scope':p['scope']}
        with self.store.connection() as db:
            routines=[]
            for r in db.execute('SELECT * FROM pulse_routines WHERE scope=? ORDER BY id',(self.scope,)):
                title, description, _ = ROUTINES[r['id']]
                credential = db.execute('SELECT revoked,expires FROM credentials WHERE id=? AND scope=?',(r['actor'], self.scope)).fetchone()
                available = bool(credential and not credential['revoked'] and credential['expires'] > self.store.now())
                routines.append({'id':r['id'],'name':title,'description':description,'enabled':bool(r['enabled']),
                                 'interval_seconds':r['interval_seconds'],'next_due':r['next_due'],
                                 'authority_available':available,'last_error':r['last_error']})
            runs = []
            for r in db.execute('SELECT id,routine,started,finished,status,summary FROM pulse_runs WHERE scope=? ORDER BY started DESC,rowid DESC LIMIT 40',(self.scope,)):
                v=dict(r);v['summary']=json.loads(v['summary']) if v['summary'] else None
                # A stopped process leaves a record, never a false success.
                if v['status']=='running' and v['started'] < self.store.now()-30:
                    v['status']='interrupted'
                v['historical']=True;runs.append(v)
        return {'configured':True,'scope':self.scope,'paused':self.store.paused(self.scope),
                'routines':routines,'runs':runs,'now':self.store.now(),
                'limits':{'retained_runs':512,'runs_per_utc_day':96,'runs_per_minute':6},
                'foreground_process_required':True,'external_effects':False,'model_used':False}

    def manual(self, bearer, identity, body):
        self._routine(identity);exact(body,{'request_id'});ident(body['request_id'])
        return self._run(bearer,identity,'manual:'+body['request_id'])

    def cycle(self):
        """Called by the existing supervisor, no additional execution thread."""
        with self.supervisor.lock:
            if self.store.paused(self.scope): return
            self._principal(self.supervisor.owner)
            with self.store.connection() as db:
                due=[dict(r) for r in db.execute('SELECT * FROM pulse_routines WHERE scope=? AND enabled=1 AND next_due<=? ORDER BY next_due,id LIMIT 2', (self.scope,self.store.now()))]
            for r in due:
                try:self._run(self.supervisor.owner,r['id'],'due:'+str(r['next_due']),r['next_due'])
                except Fault as exc:
                    # Back off to the next interval. Never spin through all missed
                    # intervals after downtime or hide the failed run as success.
                    with self.store.transaction() as db:
                        db.execute('UPDATE pulse_routines SET next_due=?,last_error=? WHERE scope=? AND id=? AND next_due=?',
                                   (self.store.now()+r['interval_seconds'],exc.code,self.scope,r['id'],r['next_due']))

    def _run(self,bearer,identity,slot,due=None):
        with self.supervisor.lock:
            p=self._principal(bearer)
            now=self.store.now()
            run_id=hashlib.sha256((self.scope+'\0'+identity+'\0'+p['id']+'\0'+slot).encode()).hexdigest()[:32]
            with self.store.transaction() as db:
                p=self.store.authenticate(db,bearer,{'owner'})
                existing=db.execute('SELECT status,summary FROM pulse_runs WHERE scope=? AND id=?',(self.scope,run_id)).fetchone()
                if existing:
                    return {'id':run_id,'state':existing['status'],'duplicate':True}
                if self.store.paused(self.scope): raise Fault('processing_paused',409)
                r=db.execute('SELECT * FROM pulse_routines WHERE scope=? AND id=?',(self.scope,identity)).fetchone()
                if due is not None and (not r['enabled'] or r['next_due']!=due or due>now or r['actor']!=p['id']):
                    raise Fault('routine_slot_changed',409)
                counts=db.execute('SELECT count(*),sum(started>=?),sum(started>?) FROM pulse_runs WHERE scope=?',
                                  ((now//86400)*86400,now-60,self.scope)).fetchone()
                if counts[0]>=512:raise Fault('pulse_history_capacity',429)
                if (counts[1] or 0)>=96 or (counts[2] or 0)>=6:raise Fault('pulse_run_limit',429)
                db.execute('INSERT INTO pulse_runs VALUES (?,?,?,?,?,?,?,?)',(self.scope,run_id,identity,p['id'],now,None,'running',None))
                if due is not None:
                    db.execute('UPDATE pulse_routines SET next_due=? WHERE scope=? AND id=?',(now+r['interval_seconds'],self.scope,identity))
                self.store.log(db,self.scope,p['id'],'pulse.started',identity)
            try:
                if identity=='memory-health':
                    data=self.store.knowledge(bearer)
                    summary={'notes':data['counts']['notes'],'links_to_review':data['counts']['issues'],
                             'outside_map':len(data['map_health']['outside_two_hops']),
                             'missing_maps':len(data['map_health']['missing_map_sources']),
                             'source_statuses':[s['status'] for s in data['sources']],
                             'sources':len(data['sources']),'basis':'indexed_snapshot'}
                    status='attention' if (not data['sources'] or summary['links_to_review'] or summary['outside_map'] or summary['missing_maps'] or any(s['status']!='ready' for s in data['sources'])) else 'completed'
                else:
                    data=self.store.desk_state(bearer)
                    summary={'current_updates_in_latest_page':sum(e['status']=='current' for e in data['events']),
                             'unacknowledged_in_latest_page':sum(e['status']=='current' and not e['acknowledged'] for e in data['events']),
                             'proposed_in_latest_actions':sum(a['state']=='proposed' for a in data['actions']),
                             'local_drafts':data['counts']['drafts'],'basis':'latest_bounded_workspace_view'}
                    status='completed'
                with self.store.transaction() as db:
                    self.store.authenticate(db,bearer,{'owner'})
                    if self.store.paused(self.scope): raise Fault('processing_paused',409)
                    # Persist counts, not transcripts, source bodies or credentials.
                    db.execute('UPDATE pulse_runs SET finished=?,status=?,summary=? WHERE scope=? AND id=?',
                               (self.store.now(),status,json.dumps(summary),self.scope,run_id))
                    self.store.log(db,self.scope,p['id'],'pulse.finished',identity)
            except Exception as exc:
                code=exc.code if isinstance(exc,Fault) else 'report_failed'
                with self.store.transaction() as db:
                    db.execute('UPDATE pulse_runs SET finished=?,status=\'failed\',summary=? WHERE scope=? AND id=?',
                               (self.store.now(),json.dumps({'error':code}),self.scope,run_id))
                if isinstance(exc,Fault): raise
                raise Fault('pulse_report_failed',503) from None
            return {'id':run_id,'state':status,'summary':summary,'historical':True,'external_effects':False}
