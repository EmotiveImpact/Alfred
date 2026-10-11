"""First-party LiveLens gateway, bound to ALFRED policy by alfred.livelens.

Captured text is returned as untrusted data. It cannot choose a tool, extend a
source grant, grant model egress, or become accepted memory through this adapter.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
try:
    from .livelens_client import LiveLensClient
except ImportError:
    from livelens_client import LiveLensClient


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise ValueError('invalid_identifier')
    return value


class LiveLensGateway:
    """A configured workspace/source binding with a fresh dispatch policy check.

    ``grant_check`` receives {subject, workspace, sourceIds, permission} and must
    return exactly True. ``token_provider`` is called on every operation, so
    rotation needs no adapter restart and secrets never enter tool parameters.
    """
    def __init__(self, base_url, workspace, sources, token_provider, grant_check,
                 *, timeout=10, max_duration_seconds=7200, receipt_sink=None):
        self.workspace = identifier(workspace)
        if not callable(token_provider) or not callable(grant_check):
            raise ValueError('explicit_policy_and_token_provider_required')
        if not isinstance(max_duration_seconds, int) or not 2 <= max_duration_seconds <= 7200:
            raise ValueError('invalid_duration_limit')
        self.base_url, self.token_provider, self.grant_check = base_url, token_provider, grant_check
        self.timeout, self.max_duration_seconds, self.receipt_sink = timeout, max_duration_seconds, receipt_sink
        self.sources = {}
        for source in sources:
            if set(source) - {'id', 'sessionIds', 'recorderSourceId'}:
                raise ValueError('unknown_source_field')
            source_id = identifier(source['id'])
            sessions = source.get('sessionIds', [])
            if not sessions or len(sessions) > 1000 or len(set(sessions)) != len(sessions):
                raise ValueError('explicit_source_sessions_required')
            if source_id in self.sources:
                raise ValueError('duplicate_source')
            self.sources[source_id] = {'id': source_id, 'sessionIds': [identifier(s) for s in sessions],
                                       'recorderSourceId': identifier(source['recorderSourceId']) if source.get('recorderSourceId') else None}
        if not self.sources or len(self.sources) > 100:
            raise ValueError('explicit_sources_required')

    def manifest(self):
        return {'schemaVersion': 1, 'id': 'livelens-policy-http-tools', 'workspace': self.workspace,
                'registeredInAlfred': False, 'registration': 'adapter-ready; independent ALFRED policy integration required',
                'sourceIds': sorted(self.sources), 'credentials': 'private runtime token provider',
                'tools': ['sessions', 'search', 'evidence', 'context', 'report', 'start_recording', 'job', 'stop_recording'],
                'permissions': {'read': 'source:read', 'collection': 'collection:control', 'modelEgress': 'model:egress'},
                'maxDurationSeconds': self.max_duration_seconds, 'memoryWrite': False, 'automaticMonitoring': False}

    def _grant(self, subject, source_ids, permission):
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 100:
            raise ValueError('invalid_subject')
        request = {'subject': subject, 'workspace': self.workspace, 'sourceIds': sorted(set(source_ids)), 'permission': permission}
        if self.grant_check(request) is not True:
            raise PermissionError('livelens_grant_denied')

    def _source(self, source_id):
        source = self.sources.get(identifier(source_id))
        if not source:
            raise PermissionError('livelens_source_denied')
        return source

    def _client(self):
        client = LiveLensClient(self.base_url, self.token_provider(), self.timeout)
        capabilities = client.capabilities()
        if capabilities.get('workspace') != self.workspace:
            raise PermissionError('livelens_workspace_mismatch')
        return client

    def _checked_sessions(self, source, result):
        session_ids = source['sessionIds']
        evidence = result.get('evidence', []) if isinstance(result, dict) else []
        if isinstance(evidence, dict):
            evidence = [evidence]
        for event in evidence:
            if event.get('sessionId') not in session_ids:
                raise PermissionError('livelens_source_response_denied')
        if isinstance(result, dict) and result.get('sessionId') is not None and result['sessionId'] not in session_ids:
            raise PermissionError('livelens_source_response_denied')
        if isinstance(result, dict) and 'sessions' in result and any(s.get('id') not in session_ids for s in result['sessions']):
            raise PermissionError('livelens_source_response_denied')
        if isinstance(result, dict):
            for field in ('event', 'before', 'after'):
                events = result.get(field, [])
                if isinstance(events, dict):
                    events = [events]
                for event in events:
                    if event.get('sessionId') not in session_ids:
                        raise PermissionError('livelens_source_response_denied')
            if isinstance(result.get('session'), dict) and result['session'].get('id') not in session_ids:
                raise PermissionError('livelens_source_response_denied')

    def dispatch(self, subject, operation, parameters):
        if not isinstance(parameters, dict):
            raise ValueError('parameters_required')
        fields = {'sessions': {'sourceId'}, 'search': {'sourceId', 'sessionId', 'query', 'account', 'limit'},
                  'evidence': {'sourceId', 'evidenceId'}, 'context': {'sourceId', 'evidenceId', 'limit'},
                  'report': {'sourceId', 'caseId'}, 'start_recording': {'sourceId', 'sessionId', 'jobId', 'maxDurationSeconds', 'segmentSeconds'},
                  'job': {'sourceId', 'jobId'}, 'stop_recording': {'sourceId', 'jobId'}}
        if operation not in fields:
            raise ValueError('unknown_tool')
        if set(parameters) - fields[operation]:
            raise ValueError('unknown_tool_parameter')
        source = self._source(parameters.get('sourceId'))
        permission = 'collection:control' if operation in ('start_recording', 'stop_recording') else 'source:read'
        self._grant(subject, [source['id']], permission)
        client = self._client()
        limit = parameters.get('limit', 100)
        if not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError('invalid_limit')
        if operation == 'sessions':
            result = {'sessions': [s for s in client.sessions()['sessions'] if s['id'] in source['sessionIds']]}
        elif operation == 'search':
            session_id = identifier(parameters.get('sessionId'))
            if session_id not in source['sessionIds']:
                raise PermissionError('livelens_session_denied')
            result = client.search(parameters.get('query', ''), parameters.get('account'), session_id, limit)
        elif operation in ('evidence', 'context'):
            evidence_id = identifier(parameters.get('evidenceId'))
            result = client.evidence(evidence_id) if operation == 'evidence' else client.context(evidence_id, limit)
        elif operation == 'report':
            result = client.report(identifier(parameters.get('caseId')))
        elif operation == 'start_recording':
            seconds = parameters.get('maxDurationSeconds')
            segment = parameters.get('segmentSeconds', 5)
            if not isinstance(seconds, int) or not 2 <= seconds <= self.max_duration_seconds:
                raise ValueError('explicit_duration_required')
            if not isinstance(segment, int) or not 2 <= segment <= min(30, seconds):
                raise ValueError('invalid_segment_bound')
            session_id = identifier(parameters.get('sessionId'))
            if session_id not in source['sessionIds'] or not source['recorderSourceId']:
                raise PermissionError('livelens_collection_source_denied')
            self._grant(subject, [source['id']], 'collection:control')
            result = client.create_job({'id': identifier(parameters.get('jobId')), 'sourceId': source['recorderSourceId'],
                                        'sessionId': session_id, 'maxDurationSeconds': seconds, 'segmentSeconds': segment})
        else:
            job_id = identifier(parameters.get('jobId'))
            job = client.job(job_id)
            if job.get('sessionId') not in source['sessionIds'] or job.get('sourceId') != source['recorderSourceId']:
                raise PermissionError('livelens_job_source_denied')
            if operation == 'stop_recording':
                self._grant(subject, [source['id']], 'collection:control')
                result = client.stop_job(job_id)
            else:
                result = job
        self._checked_sessions(source, result)
        # A grant revoked during a read prevents delivery. A request already
        # accepted by the service has its own bounded job receipt and stop action.
        self._grant(subject, [source['id']], permission)
        receipt = {'schemaVersion': 1, 'id': str(uuid.uuid4()), 'workspace': self.workspace, 'subject': subject,
                   'sourceIds': [source['id']], 'operation': operation, 'receivedAtMs': int(time.time() * 1000),
                   'trust': 'untrusted-source-data', 'instructionsAccepted': False, 'memoryAccepted': False,
                   'modelEgress': False, 'result': result}
        receipt['resultSha256'] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if self.receipt_sink:
            self.receipt_sink(receipt)
        return receipt

    def model_payload(self, subject, receipt):
        """Return data only after a separate current model-egress grant, never send it."""
        if receipt.get('workspace') != self.workspace or receipt.get('subject') != subject:
            raise PermissionError('livelens_receipt_binding_denied')
        source_ids = receipt.get('sourceIds', [])
        if not source_ids or any(s not in self.sources for s in source_ids):
            raise PermissionError('livelens_source_denied')
        self._grant(subject, source_ids, 'source:read')
        self._grant(subject, source_ids, 'model:egress')
        content_hash = hashlib.sha256(json.dumps(receipt['result'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if receipt.get('resultSha256') != content_hash:
            raise ValueError('livelens_receipt_changed')
        return {'trust': 'untrusted-source-data', 'instructionAuthority': 'none', 'workspace': self.workspace,
                'sourceIds': source_ids, 'resultSha256': content_hash, 'data': receipt['result']}
