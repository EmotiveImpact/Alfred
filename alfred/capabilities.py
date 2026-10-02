"""Common capability contract for independent specialist products (OPS-002, proposal).

ALFRED does not absorb ENDSTATE, 8BALL, Noir/Black State, Loc8 or God's Eye. Each stays an
independent system that may, once its owner provides an interface, expose a manifest and
observations to ALFRED through an adapter. No real product adapter exists here: none of
those interfaces was available to this build. The synthetic adapter below only exercises
the contract, and says so in every record it produces.

The contract keeps distinct what AGENTS.md requires to stay distinct: an observation, a
source report, an analysis (assessment), a simulation or replay, and an action. Original
observation times are preserved; ALFRED records its own receipt time separately. Action
capabilities may be declared but are never enabled by this module: an effect would need
ALFRED's exact approval binding and capability-specific reconciliation first (ACT-001).
"""
from __future__ import annotations
import hashlib
import re
from .local import Fault, ident, text, timestamp

CONTRACT_VERSION = 1
MODES = ('live', 'replay', 'simulation')
OBSERVATION_KINDS = {'status': 'status.changed', 'alert': 'status.changed', 'report': 'note', 'assessment': 'note'}
BASES = ('observed', 'reported', 'derived', 'simulated')
HEALTH = ('ok', 'degraded', 'unknown')
MAX_OBSERVATIONS = 200


def _require(value, keys):
    if type(value) is not dict or set(value) != keys:
        raise Fault('contract_fields')
    return value


def validate_manifest(value):
    """Return the manifest unchanged if it satisfies the contract, else raise a Fault."""
    _require(value, {'contract_version', 'product', 'mode', 'identity', 'capabilities', 'freshness_seconds'})
    if value['contract_version'] != CONTRACT_VERSION:
        raise Fault('unsupported_contract_version')
    product = _require(value['product'], {'id', 'name', 'owner', 'independent'})
    ident(product['id']); text(product['name'], 80); text(product['owner'], 80)
    if product['independent'] is not True:
        raise Fault('product_must_remain_independent')
    if value['mode'] not in MODES:
        raise Fault('invalid_mode')
    identity = _require(value['identity'], {'record_id_scheme', 'stable'})
    text(identity['record_id_scheme'], 200)
    if identity['stable'] is not True:
        raise Fault('record_ids_must_be_stable')
    if type(value['freshness_seconds']) is not int or not 60 <= value['freshness_seconds'] <= 604800:
        raise Fault('invalid_freshness')
    capabilities = value['capabilities']
    if type(capabilities) is not list or not 1 <= len(capabilities) <= 32:
        raise Fault('invalid_capabilities')
    seen = set()
    for item in capabilities:
        _require(item, {'id', 'kind', 'description', 'effect', 'approval'})
        ident(item['id']); text(item['description'], 300)
        if item['id'] in seen:
            raise Fault('duplicate_capability')
        seen.add(item['id'])
        if item['kind'] == 'read':
            if item['effect'] != 'none' or item['approval'] != 'not_required':
                raise Fault('read_capability_cannot_have_effects')
        elif item['kind'] == 'action':
            # An action is honest about having an effect and always needs exact approval.
            if item['effect'] != 'external' or item['approval'] != 'exact_approval_required':
                raise Fault('action_capability_must_declare_effect_and_approval')
        else:
            raise Fault('invalid_capability_kind')
    return value


def validate_observation(value, manifest, now):
    _require(value, {'record_id', 'kind', 'observed_at', 'summary', 'basis', 'evidence', 'health'})
    ident(value['record_id']); text(value['summary'], 1600)
    observed = timestamp(value['observed_at'])
    if observed > now:
        raise Fault('future_observation')
    if value['kind'] not in OBSERVATION_KINDS:
        raise Fault('invalid_observation_kind')
    if value['basis'] not in BASES:
        raise Fault('invalid_basis')
    if value['health'] not in HEALTH:
        raise Fault('invalid_health')
    if manifest['mode'] != 'live' and value['basis'] != 'simulated':
        # A replay or simulation is never presented as a fresh observation or report.
        raise Fault('simulation_mislabelled_as_observation')
    if manifest['mode'] == 'live' and value['basis'] == 'simulated':
        raise Fault('live_adapter_cannot_emit_simulation')
    if value['kind'] == 'assessment' and value['basis'] not in ('derived', 'simulated'):
        # An assessment is analysis by the product, never an observation of the world.
        raise Fault('assessment_is_not_observation')
    evidence = value['evidence']
    if type(evidence) is not list or len(evidence) > 8:
        raise Fault('invalid_evidence')
    for ref in evidence:
        _require(ref, {'ref'}); text(ref['ref'], 200)
    return value


class SpecialistBridge:
    """Feeds one independent product's observations into ALFRED's existing evidence pipeline.

    The product writes only through its own source credential, named
    ``specialist-<product id>``, so one adapter cannot speak as another product. Events
    keep the original observation time; LocalCore.ingest applies freshness, ordering,
    duplicate and simulation-workspace rules unchanged.
    """

    def __init__(self, store, source_bearer, adapter):
        self.store, self.bearer, self.adapter = store, source_bearer, adapter
        self.manifest = validate_manifest(adapter.manifest())
        principal = store.principal(source_bearer, {'source'})
        if principal['id'] != 'specialist-' + self.manifest['product']['id']:
            raise Fault('adapter_credential_mismatch', 403)
        self.health = {'last_sync': None, 'accepted': 0, 'rejected': 0, 'last_rejection': None}

    def capabilities(self):
        return [{**c, 'state': 'available_read_only' if c['kind'] == 'read' else 'declared_not_enabled'}
                for c in self.manifest['capabilities']]

    def invoke(self, capability_id, parameters):
        """Actions are never executed through this bridge. Reads happen through sync()."""
        match = next((c for c in self.manifest['capabilities'] if c['id'] == capability_id), None)
        if match is None:
            raise Fault('unknown_capability', 404)
        raise Fault('action_not_enabled' if match['kind'] == 'action' else 'reads_use_sync', 403)

    def _event(self, obs):
        product, mode = self.manifest['product'], self.manifest['mode']
        digest = hashlib.sha256(f"{obs['record_id']}|{obs['observed_at']}|{obs['kind']}".encode()).hexdigest()[:16]
        label = {'live': '', 'replay': ' · replay', 'simulation': ' · simulation'}[mode]
        refs = '; '.join(r['ref'] for r in obs['evidence'])
        summary = f"[{product['name']}{label} · {obs['kind']} · {obs['basis']} · health {obs['health']}] {obs['summary']}"
        if refs:
            summary += f" Evidence: {refs}"
        return {'id': re.sub(r'[^A-Za-z0-9_.-]', '-', f"{product['id']}-{digest}")[:80],
                'subject': obs['record_id'], 'kind': OBSERVATION_KINDS[obs['kind']], 'basis': obs['basis'],
                'observed_at': obs['observed_at'], 'expires_at': obs['observed_at'] + self.manifest['freshness_seconds'],
                'summary': summary[:2048]}

    def sync(self):
        """Read once, validate every observation and ingest the valid ones. Returns per-item outcomes."""
        now = self.store.now()
        observations = list(self.adapter.read())[:MAX_OBSERVATIONS + 1]
        if len(observations) > MAX_OBSERVATIONS:
            raise Fault('too_many_observations', 413)
        outcomes = []
        for obs in observations:
            try:
                validate_observation(obs, self.manifest, now)
                result = self.store.ingest(self.bearer, self._event(obs))
                outcomes.append({'record_id': obs['record_id'], 'accepted': True, 'route': result['route'], 'reason': result['reason']})
                self.health['accepted'] += 1
            except Fault as exc:
                outcomes.append({'record_id': obs.get('record_id') if isinstance(obs, dict) else None, 'accepted': False, 'reason': exc.code})
                self.health['rejected'] += 1
                self.health['last_rejection'] = exc.code
        self.health['last_sync'] = now
        return outcomes


class SyntheticExerciseAdapter:
    """A clearly fictional, simulation-mode feed used only to exercise the contract.

    It is not ENDSTATE, Noir, 8BALL, Loc8 or God's Eye, and it imitates none of them.
    """

    def __init__(self, now, *, observations=None, mode='simulation'):
        self.now, self.mode = now, mode
        base = now - 600
        self.observations = observations if observations is not None else [
            {'record_id': 'exercise-site-a', 'kind': 'status', 'observed_at': base, 'basis': 'simulated', 'health': 'ok',
             'summary': 'Fictional exercise: site A reports normal status.', 'evidence': [{'ref': 'synthetic script step 1'}]},
            {'record_id': 'exercise-site-b', 'kind': 'alert', 'observed_at': base + 120, 'basis': 'simulated', 'health': 'degraded',
             'summary': 'Fictional exercise: site B reports a delayed check-in.', 'evidence': [{'ref': 'synthetic script step 2'}]},
            {'record_id': 'exercise-review', 'kind': 'assessment', 'observed_at': base + 240, 'basis': 'simulated', 'health': 'unknown',
             'summary': 'Fictional exercise: the scripted assessment suggests checking site B again.', 'evidence': []},
        ]

    def manifest(self):
        return {'contract_version': CONTRACT_VERSION,
                'product': {'id': 'synthetic-exercise', 'name': 'Synthetic exercise feed', 'owner': 'ALFRED test fixture', 'independent': True},
                'mode': self.mode,
                'identity': {'record_id_scheme': 'exercise-<site or step>, stable within the script', 'stable': True},
                'capabilities': [
                    {'id': 'read_status', 'kind': 'read', 'description': 'Scripted site statuses and alerts.', 'effect': 'none', 'approval': 'not_required'},
                    {'id': 'request_check', 'kind': 'action', 'description': 'Ask a site to check in. Declared only; ALFRED never enables it here.',
                     'effect': 'external', 'approval': 'exact_approval_required'}],
                'freshness_seconds': 3600}

    def read(self):
        return list(self.observations)
