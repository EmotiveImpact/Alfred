"""Deterministic offline retrieval evaluation for memory job M06.

Compares the existing keyword ranking with the authorised-subset FTS5 ranking in
alfred.grounded.retrieve on identical invented, support-labelled questions. The
corpus, questions and answer keys are fixed in this file; nothing is random.

Answer keys are used only for scoring after every retrieval call has finished.
They are never passed to retrieve() and never appear in a request or packet.
No model, provider, network, private vault or third_party code is used. Latency
is wall-clock time in whatever machine runs this script, not a hardware claim,
and lexical recall on a synthetic corpus is not a semantic quality claim.

    python3 tools/evaluate_retrieval.py --repeats 5 --output report.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import platform
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alfred.grounded import retrieve  # noqa: E402
from alfred.knowledge import KnowledgeStore, MarkdownVault  # noqa: E402
from alfred.policy import IdentityPolicy  # noqa: E402

SCHEMA = 'alfred.retrieval-evaluation.v1'
RANKINGS = ('keywords', 'fts5')
WORKSPACE = 'evaluation'
MAIN_SOURCE, RESTRICTED_SOURCE = 'eval-notes', 'eval-restricted'
FIXED_NOW = 1790000000
CREDENTIAL_TTL = 2592000
REQUEST_FIELDS = ('question', 'ranking', 'purpose')
ANSWER_KEY_CANARY = 'm06-answer-key-canary'
RESTRICTED_CANARY = 'm06-restricted-canary'


def _note(title, *lines, kind=None, tags=None):
    head = []
    if kind or tags:
        head.append('---')
        if kind:
            head.append('kind: ' + kind)
        if tags:
            head.append('tags: [' + ', '.join(tags) + ']')
        head.append('---')
    return '\n'.join(head + ['# ' + title, ''] + list(lines)) + '\n'


# Invented notes in the granted source. Projects, people, places and figures are
# fictional. Near-duplicates, shared names, heading-only terms, explicit links
# and personal/daily distractors are deliberate.
CORPUS = {
    'map.md': _note(
        'Map', 'Start here for current work.',
        '- [[harbour-lights]]', '- [[lantern]]', '- [[kestrel]]',
        '- [[juniper]]', '- [[orchid]]', '- [[saltmarsh]]'),
    'projects/harbour-lights/harbour-lights.md': _note(
        'Harbour Lights',
        'Community lantern festival on the quayside, planned for 12 September 2026.',
        'Producer: [[morgan-ellery]]. Sponsor: Ada Mensah.',
        '- Budget: [[budget-approved]]', '- Programme: [[programme]]',
        '- Venue decision: [[harbour-lights-venue]]',
        kind='project', tags=['festival', 'community']),
    'projects/harbour-lights/budget-draft.md': _note(
        'Harbour Lights budget (draft)',
        'Status: superseded draft, kept for history.', 'Draft total: 48,000 GBP.',
        'Largest line: staging and lighting at 19,000.', 'Prepared by Morgan Ellery on 10 February.'),
    'projects/harbour-lights/budget-approved.md': _note(
        'Harbour Lights budget (approved)',
        'Status: approved.', 'Approved total: 52,500 GBP.',
        'Largest line: staging and lighting at 21,000.', 'Approved by Priya Raman on 3 March.'),
    'projects/harbour-lights/programme.md': _note(
        'Harbour Lights programme',
        'Opening procession at 18:30 from the old ferry steps.',
        'Lantern-making workshops run in the library on the two Saturdays before.',
        'Closing fireworks were replaced by a drone display after the safety review.'),
    'projects/harbour-lights/volunteers.md': _note(
        'Harbour Lights volunteers',
        'Volunteer coordinator: Ines Duarte, on loan from client services.',
        'Target: 40 stewards; 26 confirmed as of 1 March.',
        'Briefing evening: 9 September at the sailing club.'),
    'projects/harbour-lights/risk-register.md': _note(
        'Harbour Lights risk register',
        'R1 Weather: high tide coincides with the procession; mitigation is a later start.',
        'R2 Crowd density on the pier: stewarding plan required.',
        'R3 Pyrotechnics licence: closed.'),
    'projects/lantern/lantern.md': _note(
        'Lantern CRM migration',
        'Moves client records from the legacy contact system to the new CRM.',
        'Lead engineer: [[morgan-quill]].',
        'Plan: [[cutover-plan]]. Mapping: [[data-mapping]].',
        'Kickoff notes: [[projects/lantern/kickoff]].',
        kind='project', tags=['crm', 'migration']),
    'projects/lantern/kickoff.md': _note(
        'Kickoff', 'Project: Lantern.',
        'Agreed scope: contacts, accounts and open opportunities. Historical emails stay in the archive.',
        'Sponsor: Ada Mensah.'),
    'projects/lantern/cutover-plan.md': _note(
        'Lantern cutover plan',
        'The cutover is scheduled for the weekend of 21 March.',
        'Freeze on record edits from Friday 18:00.', 'Rollback window: until Sunday 12:00.'),
    'projects/lantern/standup-2026-02-10.md': _note(
        'Lantern stand-up 10 February',
        '- Duplicate accounts found in the legacy export: 312.',
        '- Morgan Quill to write the de-duplication rule.', '- Blocker: none.'),
    'projects/lantern/standup-2026-02-11.md': _note(
        'Lantern stand-up 11 February',
        '- Duplicate accounts found in the legacy export: 312.',
        '- Morgan Quill to write the de-duplication rule.',
        '- Blocker: waiting for archive access from IT.'),
    'projects/lantern/data-mapping.md': _note(
        'Lantern data mapping',
        'Legacy field org_name maps to Account name.',
        'Legacy field owner_initials maps to Account owner via the staff directory.',
        'Unmapped: fax numbers are dropped.'),
    'projects/kestrel/kestrel.md': _note(
        'Kestrel depot programme',
        'Consolidates two vehicle depots into one site.',
        'Fleet manager: [[felix-okafor]].',
        'Steering notes: [[steering-2026-02]]. Routes: [[routes]].',
        kind='project', tags=['fleet', 'logistics']),
    'projects/kestrel/kickoff.md': _note(
        'Kickoff', 'Project: Kestrel.',
        'Agreed scope: depot consolidation and route redesign. Electric vans are out of scope this year.',
        'Sponsor: Ada Mensah.'),
    'projects/kestrel/steering-2026-02.md': _note(
        'Kestrel steering group, February',
        'Attendees: Ada Mensah, Felix Okafor, Priya Raman.',
        'The group agreed the depot recommendation. Outcome: [[northgate-yard-lease]].',
        'Next meeting in April.'),
    'projects/kestrel/fleet-inspection.md': _note(
        'Fleet inspection routine',
        'Every Monday the vans get tyre, brake and lights checks before 07:00.',
        '',
        '## Winter readiness',
        'Grit and screen wash are restocked on the first of each month from November.',
        '',
        'Defects go to the workshop log the same day.'),
    'projects/kestrel/routes.md': _note(
        'Kestrel routes',
        'Route K1 (coast) moves to the Northgate yard in May.',
        'Route K2 (city) stays at the old depot until the lease ends.'),
    'projects/juniper/juniper.md': _note(
        'Juniper office move',
        'Facilities lead: [[tomasz-wolny]].',
        'On 2 February the move committee chose the supplier; terms are in [[removals-contract]].',
        'Move date: [[juniper-move-date]]. Destination: [[new-office]].',
        kind='project', tags=['office', 'move']),
    'projects/juniper/removals-contract.md': _note(
        'Removals contract',
        'Brightvan Removals, signed 4 February.',
        'Crew of six with two lorries; crates delivered a week before.',
        'Insurance cover: 250,000.'),
    'projects/juniper/new-office.md': _note(
        'New office',
        'Address: 3 Ropewalk Yard, second floor.', 'Desks: 64. Meeting rooms: 5.',
        'Bike store in the basement.'),
    'projects/juniper/seating-plan.md': _note(
        'Seating plan',
        'Finance and client services share the east wing.',
        'Quiet zone near the library corner.', 'Hot desks: 12.'),
    'clients/orchid/orchid.md': _note(
        'Orchid Analytics account',
        'Account lead: [[ines-duarte]].', 'Contract value: 140,000 per year.',
        'Renewal terms: [[clients/orchid/renewal-terms]]. Support: [[support-tiers]].',
        kind='project', tags=['client', 'account']),
    'clients/orchid/renewal-terms.md': _note(
        'Renewal terms',
        'Renewal date: 14 March 2027.', 'Notice period: 60 days.',
        'Price review capped at 4 percent.'),
    'clients/orchid/support-tiers.md': _note(
        'Support tiers',
        'Gold: four-hour response, named engineer.', 'Silver: next business day.',
        'Orchid is on Gold until renewal.'),
    'clients/saltmarsh/saltmarsh.md': _note(
        'Saltmarsh Foods account',
        'Client contact: [[rowan-hale]].', 'Services: quarterly demand forecasting.',
        'Renewal terms: [[clients/saltmarsh/renewal-terms]]. Latest review: [[quarterly-review-2026-q1]].',
        kind='project', tags=['client', 'account']),
    'clients/saltmarsh/renewal-terms.md': _note(
        'Renewal terms',
        'Renewal date: 30 September 2026.', 'Notice period: 90 days.',
        'Price review capped at 3 percent.'),
    'clients/saltmarsh/quarterly-review-2026-q1.md': _note(
        'Saltmarsh quarterly review, Q1 2026',
        'Forecast accuracy: 91 percent against a target of 88.',
        'Rowan Hale asked for a weekly summary instead of monthly.',
        'Action: Ines Duarte to propose a weekly format by 15 April.'),
    'people/ada-mensah.md': _note(
        'Ada Mensah',
        'Programme director. Sponsors Kestrel, Lantern and Harbour Lights.',
        'Prefers decisions on one page.', kind='person'),
    'people/morgan-ellery.md': _note(
        'Morgan Ellery',
        'Producer for Harbour Lights.', 'Reports to Ada Mensah.',
        'Works from the quayside office on Tuesdays and Thursdays.', kind='person'),
    'people/morgan-quill.md': _note(
        'Morgan Quill',
        'Data engineer on the Lantern migration.', 'Reports to Priya Raman for this project.',
        'Owns the de-duplication rule.', kind='person'),
    'people/priya-raman.md': _note(
        'Priya Raman',
        'Finance lead.', 'Approves budgets above 25,000.',
        'Sits on the Kestrel steering group.', kind='person'),
    'people/tomasz-wolny.md': _note(
        'Tomasz Wolny',
        'Facilities manager. Leads the Juniper office move.',
        'Keeps the building access cards.', kind='person'),
    'people/felix-okafor.md': _note(
        'Felix Okafor',
        'Fleet manager for Kestrel.', 'Former workshop supervisor.', kind='person'),
    'people/ines-duarte.md': _note(
        'Ines Duarte',
        'Account lead for Orchid Analytics.',
        'Also coordinates Harbour Lights volunteers until September.', kind='person'),
    'people/rowan-hale.md': _note(
        'Rowan Hale',
        'Head of planning at Saltmarsh Foods.', 'Prefers written summaries over calls.',
        kind='person'),
    'decisions/harbour-lights-venue.md': _note(
        'Harbour Lights venue',
        'Decision: use the Pier Pavilion, not the Corn Exchange.',
        'Reason: step-free access and covered space if it rains.',
        'Agreed 20 January by Ada Mensah and Morgan Ellery.', kind='decision'),
    'decisions/lantern-ledger-storage.md': _note(
        'Lantern ledger storage',
        'Decision: keep migrated records on the existing relational cluster.',
        'Rejected: a separate document store, because reporting needs joins.', kind='decision'),
    'decisions/northgate-yard-lease.md': _note(
        'Northgate yard lease',
        'Decision: lease the Northgate yard for 24 months from 1 May.',
        'Rationale: nearer the ring road, with room for 30 vehicles.',
        'Agreed 17 February.', kind='decision'),
    'decisions/juniper-move-date.md': _note(
        'Juniper move date',
        'Decision: move over the weekend of 11 and 12 April.',
        'Reason: avoids the Lantern cutover weekend.', kind='decision'),
    'decisions/orchid-pricing-2027.md': _note(
        'Orchid pricing for 2027',
        'Decision: offer a 3 percent increase, below the 4 percent cap.',
        'Approver: Priya Raman.', kind='decision'),
    'decisions/hybrid-working.md': _note(
        'Hybrid working',
        'Decision: three office days a week from 1 June.',
        'Teams choose their anchor days.', kind='decision'),
    'procedures/client-support.md': _note(
        'Client support procedure',
        'Log every call in the service desk queue.',
        '',
        '## Escalation contacts',
        '- First: Ines Duarte',
        '- Second: Ada Mensah',
        '- Out of hours: the duty manager rota', kind='procedure'),
    'procedures/expense-claims.md': _note(
        'Expense claims',
        'Submit receipts within 30 days.', 'Claims above 500 need a second approver.',
        'Mileage is paid at the published rate.', kind='procedure'),
    'procedures/incident-review.md': _note(
        'Incident review',
        'Hold a blameless review within five working days.',
        'Record timeline, impact and follow-up actions.', kind='procedure'),
    'procedures/visitor-sign-in.md': _note(
        'Visitor sign-in',
        'Visitors sign in at reception and wear a badge.',
        'Contractors also show their insurance letter.', kind='procedure'),
    'personal/reading-list.md': _note(
        'Reading list',
        '- A history of lighthouses', '- Notes on decision making under uncertainty',
        '- A field guide to coastal birds'),
    'personal/running-log.md': _note(
        'Running log',
        '- 3 February: 5 km along the harbour wall.', '- 10 February: 8 km, windy.',
        '- 17 February: rest week.'),
    'personal/garden-plan.md': _note(
        'Garden plan',
        'Plant garlic in late October.', 'Move the lavender to the sunny bed.',
        'Compost bins need emptying before winter.'),
    'personal/birthday-ideas.md': _note(
        'Birthday ideas',
        'Lantern-making kit for the nephew.', 'Tickets for the coastal railway.'),
    'meetings/leadership-2026-02-05.md': _note(
        'Leadership meeting 5 February',
        '- Kestrel: steering group to decide on the depot this month.',
        '- Lantern: cutover date still open.', '- Hiring freeze continues for Q1.'),
    'meetings/leadership-2026-02-19.md': _note(
        'Leadership meeting 19 February',
        '- Kestrel: Northgate yard lease agreed.',
        '- Lantern: cutover set for the weekend of 21 March.',
        '- Hiring freeze continues for Q1.'),
}
for _day, _item in enumerate((
        'Call with the bank about the card reader.', 'Booked the dentist for March.',
        'Read two chapters of the lighthouse book.', 'Team lunch at the noodle bar.',
        'Sorted receipts for the quarterly return.', 'Walked the harbour wall at lunch.',
        'Fixed the printer queue on the second floor.', 'Bought a new kettle for the kitchen.',
        'Drafted the newsletter introduction.', 'Replied to the parish council email.',
        'Updated the family calendar.', 'Cancelled the old gym membership.'), start=2):
    CORPUS['daily/2026-02-%02d.md' % _day] = _note(
        '%d February 2026' % _day, '- Inbox cleared before 09:00.', '- ' + _item,
        "- Check tomorrow's calendar.")

# Invented notes in a second source credential in the same workspace. They match
# several questions but the evaluated reader is never granted this source.
RESTRICTED = {
    'hr/morgan-quill-compensation.md': _note(
        'Morgan Quill compensation', 'Marker: ' + RESTRICTED_CANARY + '-r1.',
        'Morgan Quill reports to Priya Raman; synthetic salary band C.'),
    'finance/harbour-lights-sponsor-terms.md': _note(
        'Harbour Lights sponsor terms', 'Marker: ' + RESTRICTED_CANARY + '-r2.',
        'The approved Harbour Lights budget total includes a 10,000 sponsor contribution.'),
    'legal/northgate-yard-lease-review.md': _note(
        'Northgate yard lease review', 'Marker: ' + RESTRICTED_CANARY + '-r3.',
        'The Kestrel steering group decision on the depot carries a break clause after 12 months.'),
    'clients/orchid-renewal-discount.md': _note(
        'Orchid renewal discount', 'Marker: ' + RESTRICTED_CANARY + '-r4.',
        'The Orchid renewal date and notice period could be relaxed for a discount.'),
    'hr/juniper-move-consultation.md': _note(
        'Juniper move consultation', 'Marker: ' + RESTRICTED_CANARY + '-r5.',
        'The Juniper committee consulted staff about the office move and the supplier.'),
    'security/lantern-access-incident.md': _note(
        'Lantern access incident', 'Marker: ' + RESTRICTED_CANARY + '-r6.',
        'The Lantern stand-up blocker was archive access, paused after an incident.'),
}

# Questions only. This tuple is the entire request context of the evaluation.
QUERIES = (
    ('Q01', 'exact', 'What replaced the closing fireworks at Harbour Lights?'),
    ('Q02', 'near_duplicate', 'What is the approved Harbour Lights budget total?'),
    ('Q03', 'near_duplicate', 'Who approved the Harbour Lights budget, and when?'),
    ('Q04', 'multi_support', 'Who coordinates the Harbour Lights volunteers?'),
    ('Q05', 'exact', 'How many stewards have confirmed?'),
    ('Q06', 'exact', 'What is the mitigation for the high tide risk?'),
    ('Q07', 'shared_title', 'What scope was agreed at the Lantern kickoff?'),
    ('Q08', 'shared_title', 'Are electric vans in scope for Kestrel?'),
    ('Q09', 'inflection', 'When will Lantern cut over?'),
    ('Q10', 'inflection', 'When does the record edit freeze start?'),
    ('Q11', 'near_duplicate', 'What blocker was raised at the Lantern stand-up?'),
    ('Q12', 'near_duplicate', 'How many duplicate accounts were found in the legacy export?'),
    ('Q13', 'exact', 'What happens to fax numbers in the migration?'),
    ('Q14', 'linked', 'What did the Kestrel steering group decide about the depot?'),
    ('Q15', 'vocabulary_mismatch', 'What vehicle maintenance happens weekly?'),
    ('Q16', 'heading_only', 'What is done for winter readiness?'),
    ('Q17', 'exact', 'Which route stays at the old depot?'),
    ('Q18', 'linked', 'Which supplier did the Juniper committee choose?'),
    ('Q19', 'multi_support', 'What is the Juniper move date and the new office address?'),
    ('Q20', 'exact', 'Why was the Juniper move date chosen?'),
    ('Q21', 'vocabulary_mismatch', 'Where will finance sit in the new office?'),
    ('Q22', 'path_only', 'When is the Orchid renewal date?'),
    ('Q23', 'path_only', 'What is the notice period for Saltmarsh?'),
    ('Q24', 'exact', 'What support tier is Orchid on?'),
    ('Q25', 'heading_only', 'Who are the escalation contacts?'),
    ('Q26', 'exact', 'What forecast accuracy did Saltmarsh achieve in Q1?'),
    ('Q27', 'exact', 'What did Rowan Hale ask for at the quarterly review?'),
    ('Q28', 'multi_support', 'Which projects does Ada Mensah sponsor?'),
    ('Q29', 'shared_name', 'Who does Morgan Quill report to?'),
    ('Q30', 'shared_name', 'Which days does Morgan work from the quayside office?'),
    ('Q31', 'exact', 'What is the approval threshold for budgets?'),
    ('Q32', 'exact', 'Who keeps the building access cards?'),
    ('Q33', 'exact', 'Why was the Pier Pavilion chosen over the Corn Exchange?'),
    ('Q34', 'exact', 'Why was a separate document store rejected for Lantern?'),
    ('Q35', 'exact', 'What price increase will Orchid be offered for 2027?'),
    ('Q36', 'exact', 'How many office days a week are expected under hybrid working?'),
    ('Q37', 'exact', 'How long do I have to submit receipts for expense claims?'),
    ('Q38', 'exact', 'What must contractors show at reception?'),
    ('Q39', 'near_duplicate', 'Is the hiring freeze still in place?'),
    ('Q40', 'personal', 'When should I plant garlic?'),
    ('U01', 'unanswerable', 'What is the Saltmarsh carbon offset target?'),
    ('U02', 'unanswerable', 'Who won the office chess tournament?'),
    ('U03', 'unanswerable', 'What is the Kestrel drone budget?'),
    ('U04', 'unanswerable', 'When is the Lantern board dinner?'),
)

# Scoring only. Each key is the set of granted-source note paths that genuinely
# support an answer. An empty set marks a question nothing in the corpus answers.
_SUPPORT = {
    'Q01': ('projects/harbour-lights/programme.md',),
    'Q02': ('projects/harbour-lights/budget-approved.md',),
    'Q03': ('projects/harbour-lights/budget-approved.md',),
    'Q04': ('projects/harbour-lights/volunteers.md', 'people/ines-duarte.md'),
    'Q05': ('projects/harbour-lights/volunteers.md',),
    'Q06': ('projects/harbour-lights/risk-register.md',),
    'Q07': ('projects/lantern/kickoff.md',),
    'Q08': ('projects/kestrel/kickoff.md',),
    'Q09': ('projects/lantern/cutover-plan.md', 'meetings/leadership-2026-02-19.md'),
    'Q10': ('projects/lantern/cutover-plan.md',),
    'Q11': ('projects/lantern/standup-2026-02-11.md',),
    'Q12': ('projects/lantern/standup-2026-02-10.md', 'projects/lantern/standup-2026-02-11.md'),
    'Q13': ('projects/lantern/data-mapping.md',),
    'Q14': ('projects/kestrel/steering-2026-02.md', 'decisions/northgate-yard-lease.md',
            'meetings/leadership-2026-02-19.md'),
    'Q15': ('projects/kestrel/fleet-inspection.md',),
    'Q16': ('projects/kestrel/fleet-inspection.md',),
    'Q17': ('projects/kestrel/routes.md',),
    'Q18': ('projects/juniper/juniper.md', 'projects/juniper/removals-contract.md'),
    'Q19': ('decisions/juniper-move-date.md', 'projects/juniper/new-office.md'),
    'Q20': ('decisions/juniper-move-date.md',),
    'Q21': ('projects/juniper/seating-plan.md',),
    'Q22': ('clients/orchid/renewal-terms.md',),
    'Q23': ('clients/saltmarsh/renewal-terms.md',),
    'Q24': ('clients/orchid/support-tiers.md',),
    'Q25': ('procedures/client-support.md',),
    'Q26': ('clients/saltmarsh/quarterly-review-2026-q1.md',),
    'Q27': ('clients/saltmarsh/quarterly-review-2026-q1.md',),
    'Q28': ('people/ada-mensah.md', 'projects/lantern/kickoff.md', 'projects/kestrel/kickoff.md',
            'projects/harbour-lights/harbour-lights.md'),
    'Q29': ('people/morgan-quill.md',),
    'Q30': ('people/morgan-ellery.md',),
    'Q31': ('people/priya-raman.md',),
    'Q32': ('people/tomasz-wolny.md',),
    'Q33': ('decisions/harbour-lights-venue.md',),
    'Q34': ('decisions/lantern-ledger-storage.md',),
    'Q35': ('decisions/orchid-pricing-2027.md',),
    'Q36': ('decisions/hybrid-working.md',),
    'Q37': ('procedures/expense-claims.md',),
    'Q38': ('procedures/visitor-sign-in.md',),
    'Q39': ('meetings/leadership-2026-02-05.md', 'meetings/leadership-2026-02-19.md'),
    'Q40': ('personal/garden-plan.md',),
    'U01': (), 'U02': (), 'U03': (), 'U04': (),
}
ANSWER_KEYS = {qid: {'label': ANSWER_KEY_CANARY + ':' + qid, 'support': support}
               for qid, support in _SUPPORT.items()}


def fts5_available():
    """Probe the running SQLite build rather than assuming FTS5 is compiled in."""
    try:
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE VIRTUAL TABLE probe USING fts5(body)')
        finally:
            db.close()
        return True
    except sqlite3.Error:
        return False


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def corpus_manifest():
    return sorted([source, path, hashlib.sha256(text.encode()).hexdigest()]
                  for source, notes in ((MAIN_SOURCE, CORPUS), (RESTRICTED_SOURCE, RESTRICTED))
                  for path, text in notes.items())


def frozen_hashes(answer_keys=None):
    keys = ANSWER_KEYS if answer_keys is None else answer_keys
    parts = {'corpus_sha256': _digest(corpus_manifest()),
             'queries_sha256': _digest([list(q) for q in QUERIES]),
             'answer_keys_sha256': _digest({k: sorted(v['support']) for k, v in keys.items()})}
    return parts | {'frozen_set_sha256': _digest(parts)}


def _write(folder, notes):
    for path, text in notes.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode())


def _percentile(values, p):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _request(store, bearer, question, ranking, log):
    """The only path to retrieve(). Records exactly what enters request context."""
    request = {'question': question, 'ranking': ranking, 'purpose': 'read'}
    log.append(dict(request))
    started = time.perf_counter()
    packet = retrieve(store, bearer, request['question'], purpose=request['purpose'], ranking=request['ranking'])
    return packet, (time.perf_counter() - started) * 1000, request


def _keys_in_requests(requests, keys):
    """True if any request carried more than the question/ranking/purpose or any key text."""
    serialised = json.dumps(requests)
    markers = {v['label'] for v in keys.values()} | {p for v in keys.values() for p in v['support']}
    return any(set(r) != set(REQUEST_FIELDS) for r in requests) or any(m in serialised for m in markers)


def _signature(packet, paths):
    return tuple((paths.get(e['note_id'], e['path']), e['retrieved_via'], paths.get(e['via_note_id']),
                  e['start_line'], e['end_line'], e['sha256']) for e in packet['evidence']) + (len(packet['memory']),)


def _retrieve_all(*, repeats, warmup, fts5):
    """Build the synthetic workspace and run every retrieval call. No answer keys here."""
    rankings = RANKINGS if fts5 else RANKINGS[:1]
    questions = [question for _, _, question in QUERIES]
    requests, phases = [], {'legacy_control': 0, 'warmup': 0, 'measured': 0}
    with tempfile.TemporaryDirectory(prefix='alfred-m06-') as tmp:
        root = Path(tmp)
        _write(root / 'vault', CORPUS)
        _write(root / 'restricted', RESTRICTED)
        store = KnowledgeStore(root / 'ledger.db', clock=lambda: FIXED_NOW)
        owner = store.provision(WORKSPACE, 'eval-owner', 'owner', ttl=CREDENTIAL_TTL)
        main = store.provision(WORKSPACE, MAIN_SOURCE, 'source', ttl=CREDENTIAL_TTL)
        hidden = store.provision(WORKSPACE, RESTRICTED_SOURCE, 'source', ttl=CREDENTIAL_TTL)
        health = {MAIN_SOURCE: MarkdownVault(store, main, root / 'vault', 'Synthetic evaluation notes').scan(),
                  RESTRICTED_SOURCE: MarkdownVault(store, hidden, root / 'restricted', 'Synthetic restricted notes').scan()}
        legacy = store.knowledge(owner)
        origin = {n['id']: n['source'] for n in legacy['nodes']}
        paths = {n['id']: n['path'] for n in legacy['nodes']}
        restricted_markers = {n['id'] for n in legacy['nodes'] if n['source'] == RESTRICTED_SOURCE}
        restricted_markers |= {n['sha256'] for n in legacy['nodes'] if n['source'] == RESTRICTED_SOURCE}
        restricted_markers.add(RESTRICTED_CANARY)
        # Positive control under the documented legacy whole-workspace policy, in
        # which the owner may read both sources. This is not leakage; it shows the
        # ungranted notes do match some questions, so a zero below is meaningful.
        control = {}
        for ranking in rankings:
            hits = []
            for question in questions:
                packet, _, _ = _request(store, owner, question, ranking, requests)
                phases['legacy_control'] += 1
                hits.append(sum(origin.get(e['note_id']) == RESTRICTED_SOURCE for e in packet['evidence']))
            control[ranking] = hits
        policy = IdentityPolicy(store)
        policy.grant(owner, MAIN_SOURCE, 'read', FIXED_NOW + 86400, policy.view(owner)['epoch'])
        view = policy.view(owner)
        granted = store.knowledge(owner)
        strict_leaks = {r: 0 for r in rankings}
        for _ in range(warmup):
            for question in questions:
                for ranking in rankings:
                    packet, _, _ = _request(store, owner, question, ranking, requests)
                    phases['warmup'] += 1
                    strict_leaks[ranking] += sum(origin.get(e['note_id']) != MAIN_SOURCE for e in packet['evidence'])
        packets = {r: [None] * len(questions) for r in rankings}
        signatures = {r: [None] * len(questions) for r in rankings}
        latency = {r: [] for r in rankings}
        sent = {r: [] for r in rankings}
        stable = {r: True for r in rankings}
        for repeat in range(repeats):
            order = rankings if repeat % 2 == 0 else tuple(reversed(rankings))
            for index, question in enumerate(questions):
                for ranking in order:
                    packet, elapsed, request = _request(store, owner, question, ranking, requests)
                    phases['measured'] += 1
                    latency[ranking].append(elapsed)
                    sent[ranking].append(request['question'])
                    strict_leaks[ranking] += sum(origin.get(e['note_id']) != MAIN_SOURCE for e in packet['evidence'])
                    signature = _signature(packet, paths)
                    if repeat == 0:
                        packets[ranking][index], signatures[ranking][index] = packet, signature
                    elif signature != signatures[ranking][index]:
                        stable[ranking] = False
    indexed = sorted([origin[n['id']], n['path'], n['sha256']] for n in legacy['nodes'])
    return {
        'rankings': rankings, 'questions': questions, 'requests': requests, 'phases': phases, 'sent': sent,
        'packets': packets, 'latency': latency, 'stable': stable, 'control': control, 'strict_leaks': strict_leaks,
        'strict_calls': {r: len(questions) * (warmup + repeats) for r in rankings},
        'origin': origin, 'paths': paths, 'restricted_markers': restricted_markers,
        'health': {k: {'status': v['status'], 'notes': v.get('notes'), 'errors': v['errors']} for k, v in health.items()},
        'indexed_matches_frozen': indexed == corpus_manifest(),
        'legacy_visible_notes': len(legacy['nodes']), 'granted_visible_notes': len(granted['nodes']),
        'granted_sources': sorted({n['source'] for n in granted['nodes']}),
        'links': len(granted['links']), 'link_issues': len(granted['issues']),
        'policy_mode': view['mode'], 'grants': [{k: g[k] for k in ('source', 'capability')} for g in view['grants']],
    }


def _score_query(packet, support, origin, markers):
    evidence = packet['evidence']
    items, relevant, characters, irrelevant_characters, leaked = [], set(), 0, 0, 0
    for e in evidence:
        from_granted = origin.get(e['note_id']) == MAIN_SOURCE
        supporting = from_granted and e['path'] in support
        leaked += not from_granted
        if supporting:
            relevant.add(e['path'])
        characters += len(e['excerpt'])
        irrelevant_characters += 0 if supporting else len(e['excerpt'])
        items.append({'path': e['path'], 'retrieved_via': e['retrieved_via'],
                      'lines': [e['start_line'], e['end_line']], 'supporting': supporting})
    serialised = json.dumps(packet, sort_keys=True)
    return {
        'evidence': items, 'evidence_items': len(evidence),
        'supporting_found': len(relevant), 'irrelevant_items': sum(not i['supporting'] for i in items),
        'recall': round(len(relevant) / len(support), 4) if support else None,
        'excerpt_characters': characters, 'irrelevant_excerpt_characters': irrelevant_characters,
        'ungranted_evidence_items': leaked,
        'ungranted_identifiers_or_text': any(m in serialised for m in markers),
        'reviewed_statements': len(packet['memory']),
    }


def _summarise(results, latency, stable, control, strict_leaks, strict_calls):
    answerable = [r for r in results if r['support_size']]
    unanswerable = [r for r in results if not r['support_size']]
    items = sum(r['evidence_items'] for r in results)
    labelled = sum(r['support_size'] for r in answerable)
    categories, routes = {}, {}
    for r in answerable:
        categories.setdefault(r['category'], []).append(r)
    for item in (i for r in results for i in r['evidence']):
        route = routes.setdefault(item['retrieved_via'], {'items': 0, 'irrelevant_items': 0})
        route['items'] += 1
        route['irrelevant_items'] += not item['supporting']
    return {
        'status': 'measured',
        'recall': {
            'answerable_queries': len(answerable),
            'mean_evidence_recall': round(sum(r['recall'] for r in answerable) / len(answerable), 4),
            'micro_evidence_recall': _ratio(sum(r['supporting_found'] for r in answerable), labelled),
            'any_hit_rate': _ratio(sum(r['supporting_found'] > 0 for r in answerable), len(answerable)),
            'full_support_rate': _ratio(sum(r['recall'] == 1 for r in answerable), len(answerable)),
            'first_item_supporting_rate': _ratio(sum(bool(r['evidence']) and r['evidence'][0]['supporting']
                                                     for r in answerable), len(answerable)),
            'by_category': {name: {'queries': len(group),
                                   'mean_evidence_recall': round(sum(r['recall'] for r in group) / len(group), 4),
                                   'any_hit_rate': _ratio(sum(r['supporting_found'] > 0 for r in group), len(group))}
                            for name, group in sorted(categories.items())},
        },
        'irrelevant_context': {
            'share_of_evidence_items': _ratio(sum(r['irrelevant_items'] for r in results), items),
            'share_of_evidence_items_answerable': _ratio(sum(r['irrelevant_items'] for r in answerable),
                                                         sum(r['evidence_items'] for r in answerable)),
            'share_of_excerpt_characters': _ratio(sum(r['irrelevant_excerpt_characters'] for r in results),
                                                  sum(r['excerpt_characters'] for r in results)),
            'mean_irrelevant_items_per_query': round(sum(r['irrelevant_items'] for r in results) / len(results), 4),
            'by_route': dict(sorted(routes.items())),
            'unanswerable_queries': len(unanswerable),
            'unanswerable_queries_returning_evidence': sum(r['evidence_items'] > 0 for r in unanswerable),
            'unanswerable_evidence_items': sum(r['evidence_items'] for r in unanswerable),
        },
        'volume': {
            'mean_evidence_items': round(items / len(results), 4),
            'max_evidence_items': max(r['evidence_items'] for r in results),
            'queries_without_evidence': sum(r['evidence_items'] == 0 for r in results),
            'mean_excerpt_characters': round(sum(r['excerpt_characters'] for r in results) / len(results), 1),
        },
        'latency_ms': {
            'samples': len(latency), 'p50': round(_percentile(latency, 50), 3),
            'p95': round(_percentile(latency, 95), 3), 'mean': round(sum(latency) / len(latency), 3),
            'min': round(min(latency), 3), 'max': round(max(latency), 3),
        },
        'permission_leakage': {
            'ungranted_evidence_items': sum(r['ungranted_evidence_items'] for r in results),
            'packets_with_ungranted_identifiers_or_text': sum(r['ungranted_identifiers_or_text'] for r in results),
            'packets_checked': len(results),
            'ungranted_evidence_items_all_strict_calls': strict_leaks,
            'strict_calls_checked': strict_calls,
        },
        'deterministic_across_repeats': stable,
        'legacy_scope_control': {
            'queries_with_ungranted_evidence': sum(h > 0 for h in control),
            'ungranted_evidence_items': sum(control),
        },
    }


def evaluate(*, repeats=5, warmup=1, fts5=None, answer_keys=None):
    """Return (report, audit). The audit holds raw requests/packets for tests only."""
    if type(repeats) is not int or not 1 <= repeats <= 100 or type(warmup) is not int or not 0 <= warmup <= 10:
        raise ValueError('repeats must be 1-100 and warmup 0-10')
    keys = ANSWER_KEYS if answer_keys is None else answer_keys
    if set(keys) != {qid for qid, _, _ in QUERIES}:
        raise ValueError('every query needs exactly one answer key')
    available = fts5_available() if fts5 is None else bool(fts5)
    run = _retrieve_all(repeats=repeats, warmup=warmup, fts5=available)
    # Scoring begins only after every retrieval call above has completed.
    per_query, by_ranking = [], {r: [] for r in run['rankings']}
    for index, (qid, category, question) in enumerate(QUERIES):
        support = set(keys[qid]['support'])
        entry = {'id': qid, 'category': category, 'question': question, 'support': sorted(support), 'results': {}}
        for ranking in run['rankings']:
            scored = _score_query(run['packets'][ranking][index], support, run['origin'], run['restricted_markers'])
            entry['results'][ranking] = scored
            by_ranking[ranking].append(scored | {'category': category, 'support_size': len(support)})
        per_query.append(entry)
    rankings = {r: _summarise(by_ranking[r], run['latency'][r], run['stable'][r], run['control'][r],
                              run['strict_leaks'][r], run['strict_calls'][r])
                for r in run['rankings']}
    if not available:
        rankings['fts5'] = {'status': 'not_measured', 'reason': 'fts5_unavailable_in_sqlite_build',
                            'sqlite': sqlite3.sqlite_version}
    comparison = None
    if available:
        pairs = [(e['results']['keywords'], e['results']['fts5'], bool(e['support'])) for e in per_query]
        answerable = [(a, b) for a, b, labelled in pairs if labelled]
        comparison = {
            'answerable_queries': len(answerable),
            'keywords_higher_recall': sum(a['recall'] > b['recall'] for a, b in answerable),
            'fts5_higher_recall': sum(b['recall'] > a['recall'] for a, b in answerable),
            'equal_recall': sum(a['recall'] == b['recall'] for a, b in answerable),
            'identical_evidence_paths': sum([i['path'] for i in a['evidence']] == [i['path'] for i in b['evidence']]
                                            for a, b, _ in pairs),
            'p50_latency_ratio_fts5_to_keywords': _ratio(rankings['fts5']['latency_ms']['p50'],
                                                          rankings['keywords']['latency_ms']['p50']),
            'basis': 'descriptive differences on this frozen synthetic set only; no significance test',
        }
    measured_questions = run['sent']
    report = {
        'schema': SCHEMA, 'job': 'M06', 'tool': 'tools/evaluate_retrieval.py',
        'model_inference': False, 'network': False,
        'answer_keys_in_request_context': _keys_in_requests(run['requests'], keys),
        'private_data': False, 'randomness': 'none in the evaluation; application identifiers are random but '
                                              'never decide ordering, scoring or hashes',
        'environment': {
            'python': platform.python_version(), 'python_implementation': platform.python_implementation(),
            'sqlite': sqlite3.sqlite_version, 'fts5_available': available,
            'platform': platform.platform(), 'machine': platform.machine(),
            'latency_basis': 'time.perf_counter around each complete retrieve() call (authorisation, '
                             'note reads, ranking, link expansion and excerpts) in the machine that ran '
                             'this script; not a measurement of any named target hardware',
        },
        'frozen_set': frozen_hashes(keys),
        'corpus': {
            'granted_source_notes': len(CORPUS), 'ungranted_source_notes': len(RESTRICTED),
            'indexed_matches_frozen': run['indexed_matches_frozen'], 'index_health': run['health'],
            'explicit_links_resolved': run['links'], 'link_issues': run['link_issues'],
        },
        'queries': {
            'count': len(QUERIES), 'answerable': sum(bool(v['support']) for v in keys.values()),
            'unanswerable': sum(not v['support'] for v in keys.values()),
            'labelled_supporting_notes': sum(len(v['support']) for v in keys.values()),
            'categories': {c: sum(q[1] == c for q in QUERIES) for c in sorted({q[1] for q in QUERIES})},
            'request_fields': sorted(REQUEST_FIELDS),
            'identical_across_rankings': len({tuple(v) for v in measured_questions.values()}) == 1
                                         and all(v == [q for _, _, q in QUERIES] * repeats
                                                 for v in measured_questions.values()),
            'sent_sha256': {r: _digest(v) for r, v in measured_questions.items()},
        },
        'policy': {
            'mode': run['policy_mode'], 'grants': run['grants'], 'purpose': 'read',
            'granted_source': MAIN_SOURCE, 'ungranted_source': RESTRICTED_SOURCE,
            'legacy_visible_notes': run['legacy_visible_notes'], 'granted_visible_notes': run['granted_visible_notes'],
            'granted_visible_sources': run['granted_sources'],
        },
        'protocol': {
            'repeats': repeats, 'warmup_passes': warmup, 'calls': run['phases'],
            'measured_calls_per_ranking': len(QUERIES) * repeats,
            'order': 'per query, rankings interleaved; ranking order alternates on each repeat',
            'quality_from': 'first measured repeat; every later repeat must return identical evidence',
            'percentile_method': 'nearest rank', 'default_ranking_unchanged': 'keywords',
            'limits': 'existing retrieve() limits: five sources and 6,000 excerpt characters',
            'route_labels': 'retrieved_via values are copied from each packet; under the fts5 ranking, '
                            'keyword_match means selected by the FTS5 ranking (packet ranking field is fts5)',
            'irrelevant_definition': 'an evidence item whose note is not in the answer key, including '
                                     'link-expanded hubs that may still be useful context',
        },
        'rankings': rankings,
        'comparison': comparison,
        'per_query': per_query,
        'limitations': [
            'Invented corpus and questions written by the evaluator; results do not transfer to private vaults.',
            'Lexical support labels measure whether supporting notes reach the packet, not answer correctness, '
            'semantic quality or entailment.',
            'Latency comes from this container and Python/SQLite build, not named target hardware.',
            'No model, provider or network call; no new model experiment is implied.',
            'Reviewed-memory statements are absent from this set, so only authored-note evidence is scored.',
            'Permission leakage is checked for one ungranted source under strict read grants only.',
        ],
    }
    audit = {'requests': run['requests'], 'packets': run['packets'], 'questions': run['questions']}
    return report, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description='Deterministic offline M06 retrieval evaluation.')
    parser.add_argument('--repeats', type=int, default=5, help='measured passes per ranking (default 5)')
    parser.add_argument('--warmup', type=int, default=1, help='unmeasured passes before timing (default 1)')
    parser.add_argument('--output', type=Path, help='also write the JSON report to this path')
    args = parser.parse_args(argv)
    report, _ = evaluate(repeats=args.repeats, warmup=args.warmup)
    text = json.dumps(report, indent=1, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    sys.stdout.write(text)
    status = 0
    if not report['environment']['fts5_available']:
        print('FTS5 is unavailable in SQLite ' + sqlite3.sqlite_version + '; the fts5 ranking was not measured.',
              file=sys.stderr)
        status = 2
    measured = [v for v in report['rankings'].values() if v.get('status') == 'measured']
    if report['answer_keys_in_request_context'] or any(
            v['permission_leakage']['ungranted_evidence_items'] or
            v['permission_leakage']['ungranted_evidence_items_all_strict_calls'] or
            v['permission_leakage']['packets_with_ungranted_identifiers_or_text'] or
            not v['deterministic_across_repeats'] for v in measured):
        print('Permission leakage, answer-key exposure or non-deterministic evidence detected.', file=sys.stderr)
        status = 1
    return status


if __name__ == '__main__':
    sys.exit(main())
