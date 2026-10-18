"""The goal hub on the local host, off unless asked for (coordination/BACKLOG.md item C2).

``desk serve --hub synthetic`` builds H1's ``BrainHub`` and H2's ``GoalHub`` over the
host's own job coordinator, so ``/desk/hub``, mandates, budgets, heartbeats, verification
and daily learning's goal evidence work end to end on the real desk. Only the deterministic
``SyntheticBrain`` is registered: which real brain comes first is the owner's choice
(AGENT_HUB.md, integration plan decision 4), so no real brain is offered here. The policy
allows no cloud scope and no tool, the defaults ``BrainPolicy`` already holds.

Without the switch nothing is built: no hub tables, no brain worker, and ``/desk/hub``
answers ``hub_not_configured`` exactly as before.

With it, one more ALFRED-owned worker thread, ``local-brain``, is enrolled for brain tasks
only. It runs brains in this process through the hub's backend, which asks the hub again
before a brain starts. The local subprocess worker never takes brain tasks. The host's own
supervisor loop runs ``GoalHub.cycle`` (accounting results, then heartbeats); the hub has
no thread of its own.
"""
from __future__ import annotations
import threading

from .local import Fault

CHOICES = ('off', 'synthetic')
WORKER = 'local-brain'


def start_goal_hub(store, jobs, owner, choice, *, poll_seconds=0.2):
    """``(hub, halt)``: the goal hub (``None`` when off) and a function that stops its worker
    and says whether it stopped. Refuses an unknown choice before building anything."""
    if choice not in CHOICES:
        raise Fault('invalid_hub_brain')
    if choice == 'off':
        return None, lambda: True
    from .brain import BrainHub, BrainPolicy, BrainRegistry, SyntheticBrain
    from .hub_goals import GoalHub
    from .jobs import JobWorker
    registry = BrainRegistry()
    registry.register(SyntheticBrain())
    hub = GoalHub(store, BrainHub(store, jobs, registry, BrainPolicy()), owner)
    if not any(w['id'] == WORKER for w in jobs.workers(owner)):
        jobs.enrol_worker(owner, WORKER, 'This computer (brain tasks, synthetic test brain)', ['brain_task'])
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
