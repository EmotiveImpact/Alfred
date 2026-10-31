"""The goal hub on the local host, off unless asked for (coordination/BACKLOG.md item C2).

``desk serve --hub synthetic`` builds H1's ``BrainHub`` and H2's ``GoalHub`` over the
host's own job coordinator, so ``/desk/hub``, mandates, budgets, heartbeats, verification
and daily learning's goal evidence work end to end on the real desk. Only the deterministic
``SyntheticBrain`` is registered. The policy allows no cloud scope and no tool, the
defaults ``BrainPolicy`` already holds.

``hermes`` adds the owner's first real brain (chosen 30 October 2026): Hermes in the sealed
box (docs/HERMES_BOX.md), calling Claude through ALFRED's relay. Everything it needs comes
from the owner in a ``HermesSetup`` and nothing has a default: the build record of an image
built from this checkout's pins, the model, the price ALFRED charges per 1,000 tokens, where
the Claude key is read from, and the areas whose notes may go to the cloud. The image is
checked against the pins before anything is built, and the policy allows the cloud for
those areas only, so a company or client task is refused before a box starts unless the
owner named that area. The synthetic test brain stays registered beside it. The policy still
allows no tool: each task's excerpts are in its prompt.

Without the switch nothing is built: no hub tables, no brain worker, and ``/desk/hub``
answers ``hub_not_configured`` exactly as before.

With it, one more ALFRED-owned worker thread, ``local-brain``, is enrolled for brain tasks
only. It runs brains in this process through the hub's backend, which asks the hub again
before a brain starts. The local subprocess worker never takes brain tasks. The host's own
supervisor loop runs ``GoalHub.cycle`` (accounting results, then heartbeats); the hub has
no thread of its own.
"""
from __future__ import annotations
from dataclasses import dataclass
import threading

from .local import Fault

CHOICES = ('off', 'synthetic', 'hermes')
# What ``desk serve --hub`` offers. ``hermes`` joins once its key can be read from the
# keychain or a server secret, which reuses the readers encryption step 1 adds.
SERVE_CHOICES = ('off', 'synthetic')
WORKER = 'local-brain'
LABELS = {'synthetic': 'This computer (brain tasks, synthetic test brain)',
          'hermes': 'This computer (brain tasks: Hermes in a sealed box, and the synthetic test brain)'}


@dataclass(frozen=True)
class HermesSetup:
    """What the owner gives ``--hub hermes``. ``record`` is what tools/build_hermes_box.py
    wrote; ``price`` is pence per 1,000 tokens, charged on input and output alike, so set it
    from the model's output price, rounded up; ``key_source`` is an
    ``alfred.anthropic_provider.KeySource``; ``cloud_areas`` are the scope classes whose
    notes may go to Claude."""
    record: dict
    model: str
    price: int
    key_source: object
    cloud_areas: frozenset

    def __post_init__(self):
        from .brain import SCOPE_CLASSES
        if type(self.cloud_areas) is not frozenset or not self.cloud_areas <= set(SCOPE_CLASSES):
            raise Fault('invalid_cloud_scopes')


def hermes_brain(setup: HermesSetup, *, docker='docker', inspect=None, launch=None, connect=None):
    """The Hermes brain for ``setup``, after its image is checked against this checkout's pins.
    ``inspect``, ``launch`` and ``connect`` stand in for Docker and the network in tests."""
    from .anthropic_provider import AnthropicProvider
    from .hermes_box import HermesBrain, inspect_image, load_box
    image, pin = load_box(setup.record, docker=docker, inspect=inspect or inspect_image)
    provider = AnthropicProvider(setup.key_source, connect=connect)
    return HermesBrain(image_id=image, pin=pin, provider=provider, model=setup.model, tools=frozenset({'file.read'}),
                       pence_per_1k_tokens=setup.price, docker=docker, launch=launch)


def start_goal_hub(store, jobs, owner, choice, *, hermes: HermesSetup | None = None, make_hermes=hermes_brain,
                   poll_seconds=0.2):
    """``(hub, halt)``: the goal hub (``None`` when off) and a function that stops its worker
    and says whether it stopped. Refuses an unknown choice, or ``hermes`` without its setup or
    with an image that does not match the pins, before building anything."""
    if choice not in CHOICES:
        raise Fault('invalid_hub_brain')
    if choice == 'off':
        return None, lambda: True
    if (choice == 'hermes') != (hermes is not None):
        raise Fault('hermes_setup_missing' if choice == 'hermes' else 'hermes_setup_unused')
    from .brain import BrainHub, BrainPolicy, BrainRegistry, SyntheticBrain
    from .hub_goals import GoalHub
    from .jobs import JobWorker
    registry = BrainRegistry()
    registry.register(SyntheticBrain())
    policy = BrainPolicy()
    if hermes is not None:
        registry.register(make_hermes(hermes))
        policy = BrainPolicy(cloud_scopes=hermes.cloud_areas)
    hub = GoalHub(store, BrainHub(store, jobs, registry, policy), owner)
    if not any(w['id'] == WORKER for w in jobs.workers(owner)):
        jobs.enrol_worker(owner, WORKER, LABELS[choice], ['brain_task'])
    worker = JobWorker(jobs, hub.backend(), owner, WORKER, poll_seconds=poll_seconds)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,), kwargs={'idle_seconds': max(poll_seconds, 0.05) * 4},
                              name='alfred-local-brain', daemon=True)
    thread.start()

    def halt():
        stop.set()
        thread.join(10)
        return not thread.is_alive()
    return hub, halt
