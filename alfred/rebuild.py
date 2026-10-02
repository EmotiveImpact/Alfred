"""Rebuild the knowledge index from the vault without losing history (MEM-012).

The Markdown files are canonical; the note, link and anchor tables are projections of
them. The durable catalogue (revision history, identities, the vault binding) and the
reviewed memory are never rebuilt. A rebuild drops one source's projections and rescans
its vault inside the scanner's single write transaction, so the catalogue restores every
note identity and revision; if the vault cannot be read, nothing changes.

A rebuild is not a reset. Text that changed on disk since the last scan gets a new
revision and invalidates reviews that cited the old text, exactly as an ordinary scan
would, and nothing that was invalidated is revived. The reconciliation report says what,
if anything, differs from before. Offline only: the desk host must be stopped.
"""
from __future__ import annotations
from .knowledge import MarkdownVault
from .local import Fault
from .reviewed_memory import ReviewedMemory


def _state(store, owner, source):
    view = store.knowledge(owner)
    notes = {n['id']: (n['path'], n['revision'], n['sha256']) for n in view['nodes'] if n['source'] == source}
    links = sorted((l['source'], l['target'], l['line']) for l in view['links'] if l['source'] in notes)
    claims = {c['id']: c['state'] for c in ReviewedMemory(store).view(owner)['claims']}
    return notes, links, claims


def rebuild_index(store, owner_bearer, source_bearer, vault, **options):
    """Rebuild one vault source's projections and return a reconciliation report."""
    source = store.principal(source_bearer, {'source'})['id']
    store.principal(owner_bearer, {'owner'})
    notes, links, claims = _state(store, owner_bearer, source)
    health = MarkdownVault(store, source_bearer, vault, **options).scan(rebuild=True)
    if health['status'] == 'unavailable':
        # The write transaction never ran, so the earlier projections are untouched.
        raise Fault('rebuild_source_unavailable', 409)
    after_notes, after_links, after_claims = _state(store, owner_bearer, source)
    changed = sorted(i for i in notes if i in after_notes and notes[i] != after_notes[i])
    report = {
        'source': source,
        'notes': {'before': len(notes), 'after': len(after_notes),
                  'same_identity_and_revision': sum(notes[i] == after_notes.get(i) for i in notes),
                  'new_revision': [{'id': i, 'path': after_notes[i][0], 'revision_before': notes[i][1],
                                    'revision_after': after_notes[i][1]} for i in changed],
                  'no_longer_present': sorted(i for i in notes if i not in after_notes),
                  'new': sorted(i for i in after_notes if i not in notes)},
        'links': {'before': len(links), 'after': len(after_links), 'unchanged': links == after_links},
        'reviewed_statements': {'checked': len(claims),
                                'state_changed': [{'id': i, 'before': claims[i], 'after': after_claims.get(i)}
                                                  for i in sorted(claims) if claims[i] != after_claims.get(i)]},
        'status': health['status'], 'issues': len(health['errors']),
        'kept': ['revision history and identities', 'vault binding', 'reviewed statements and their lineage',
                 'tombstones, receipts and the lifecycle journal'],
        'basis': 'projections_rebuilt_from_canonical_files_and_durable_catalogue',
    }
    with store.transaction() as db:
        p = store.authenticate(db, owner_bearer, {'owner'})
        store.log(db, p['scope'], p['id'], 'knowledge.rebuilt', source)
    return report
