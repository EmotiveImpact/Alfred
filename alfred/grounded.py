"""Bounded source-first questions. Models cannot execute or grant authority.

Default mode returns labelled excerpts, not a simulated AI answer. Optional model
interpretations must cite actual lines in the supplied packet. Citation validation
proves reference integrity, NOT semantic entailment or real-world truth.
"""
from __future__ import annotations
import re
import html
from urllib.parse import quote
from .local import Fault, exact
from .knowledge import safe_text

STOP = frozenset('a an and are as at be been but by can could did do does for from give had has have how i in into is it its me my of on or our please should show tell that the their them there these they this to us was we were what when where which who why will with would you your about'.split())
MAX_SOURCES, MAX_CHARACTERS = 5, 6000


def question_terms(question):
    safe_text(question, 500)
    if len(question.strip()) < 3:
        raise Fault('question_required')
    terms = list(dict.fromkeys(t for t in re.findall(r'\w+', question.casefold()) if len(t) > 1 and t not in STOP))
    if len(terms) > 32:
        raise Fault('question_too_complex')
    return terms


def excerpt(note, terms, remaining):
    lines = note['body'].splitlines()
    if not lines:
        return None
    body_start = 0
    if lines[0].strip() == '---':
        body_start = next((i + 1 for i in range(1, min(len(lines), 81)) if lines[i].strip() == '---'), 0)
    candidates = range(body_start, len(lines))
    candidates = [i for i in candidates if lines[i].strip() and len(lines[i]) <= min(1200, remaining)]
    if not candidates:
        return None
    anchor = max(candidates, key=lambda i: (sum(t in lines[i].casefold() for t in terms), -i))
    start = max(body_start, anchor - 1)
    if len(lines[start]) > min(1200, remaining):
        start = anchor
    chosen = []
    for line in lines[start:start + 8]:
        if len('\n'.join(chosen + [line])) > min(1400, remaining):
            break
        chosen.append(line)
    if not chosen or not '\n'.join(chosen).strip():
        return None
    return {'start_line': start + 1, 'end_line': start + len(chosen), 'excerpt': '\n'.join(chosen)}


def retrieve(store, bearer, question):
    terms = question_terms(question)
    graph = store.knowledge(bearer)
    ranked, notes, skipped = [], {}, []
    for meta in graph['nodes']:
        try:
            note = store.knowledge_note(bearer, meta['id'])
        except Fault:
            skipped.append({'note_id': meta['id'], 'reason': 'source_unavailable'})
            continue
        if note['sha256'] != meta['sha256']:
            skipped.append({'note_id': meta['id'], 'reason': 'source_changed'})
            continue
        notes[meta['id']] = (meta, note)
        title = (meta['title'] + ' ' + meta['path'] + ' ' + ' '.join(meta['tags'])).casefold()
        body = note['body'].casefold()
        matched = sum(t in body or t in title for t in terms)
        score = matched * 4 + sum(t in title for t in terms) * 3
        if matched:
            ranked.append((score, meta['path'], meta['id']))
    ranked.sort(key=lambda x: (-x[0], x[1], x[2]))
    seeds = [r[2] for r in ranked[:3]]
    selection = [(identity, 'keyword_match', None) for identity in seeds]
    # Follow only explicit graph edges from retrieved notes. A link supplies context,
    # not evidence that the target is true or that it entails the answer.
    candidates = []
    for link in graph['links']:
        if link['source'] in seeds and link['target'] in notes and link['target'] not in seeds:
            candidates.append((notes[link['target']][0]['path'], link['target'], link['source']))
    for _, identity, origin in sorted(candidates):
        if identity not in {s[0] for s in selection} and len(selection) < MAX_SOURCES:
            selection.append((identity, 'explicit_link_from_match', origin))
    for _, _, identity in ranked[3:]:
        if len(selection) >= MAX_SOURCES:
            break
        if identity not in {s[0] for s in selection}:
            selection.append((identity, 'keyword_match', None))
    evidence, remaining = [], MAX_CHARACTERS
    for identity, reason, origin in selection:
        meta, note = notes[identity]
        part = excerpt(note, terms, remaining)
        if part is None:
            continue
        remaining -= len(part['excerpt'])
        evidence.append({'source_id': 'S' + str(len(evidence) + 1), 'note_id': identity,
                         'title': note['title'], 'path': note['path'], 'kind': note['kind'],
                         'sha256': note['sha256'], 'revision': note['revision'], 'indexed': note['indexed'],
                         'retrieved_via': reason, 'via_note_id': origin,
                         'basis': 'authored_note_not_verified_fact', **part})
    return {'question': question.strip(), 'scope': graph['scope'], 'indexed_at': graph['now'],
            'terms': terms, 'evidence': evidence, 'skipped': skipped[:32],
            'retrieval': 'bounded_keywords_plus_explicit_one_hop_links', 'indexed_snapshot_only': True,
            'limits': {'sources': MAX_SOURCES, 'excerpt_characters': MAX_CHARACTERS}}


def check_sources(store, bearer, references):
    store.principal(bearer, {'owner', 'reader'})
    if type(references) is not list or len(references) > MAX_SOURCES:
        raise Fault('invalid_source_references')
    problems = []
    for ref in references:
        exact(ref, {'note_id', 'sha256', 'revision'})
        if type(ref['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', ref['sha256']):
            raise Fault('invalid_source_hash')
        if type(ref['revision']) is not int or ref['revision'] < 1:
            raise Fault('invalid_source_revision')
        try:
            note = store.knowledge_note(bearer, ref['note_id'])
        except Fault as exc:
            if exc.status == 401 or exc.code in {'unauthorised', 'forbidden'}:
                raise
            problems.append({'note_id': ref['note_id'], 'reason': 'source_unavailable'})
            continue
        if note['sha256'] != ref['sha256'] or note['revision'] != ref['revision']:
            problems.append({'note_id': ref['note_id'], 'reason': 'source_changed'})
    return {'current_index_match': not problems, 'problems': problems, 'indexed_snapshot_only': True}


def references(packet):
    return [{k: s[k] for k in ('note_id', 'sha256', 'revision')} for s in packet['evidence']]


def validate_interpretation(value, packet):
    if type(value) is not dict:
        raise Fault('invalid_model_answer')
    exact(value, {'answerable', 'claims'})
    if type(value['answerable']) is not bool or type(value['claims']) is not list or len(value['claims']) > 6:
        raise Fault('invalid_model_answer')
    if value['answerable'] != bool(value['claims']):
        raise Fault('inconsistent_model_answer')
    available = {s['source_id']: s for s in packet['evidence']}
    claims = []
    for claim in value['claims']:
        exact(claim, {'text', 'citations'})
        safe_text(claim['text'], 700)
        if not claim['text'].strip() or type(claim['citations']) is not list or not 1 <= len(claim['citations']) <= 3:
            raise Fault('invalid_model_claim')
        checked = []
        for citation in claim['citations']:
            exact(citation, {'source_id', 'start_line', 'end_line'})
            sid = citation['source_id']
            if type(sid) is not str or sid not in available:
                raise Fault('unknown_model_citation')
            source = available[sid]
            first, last = citation['start_line'], citation['end_line']
            if type(first) is not int or type(last) is not int or not source['start_line'] <= first <= last <= source['end_line']:
                raise Fault('invalid_model_citation_range')
            lines = source['excerpt'].split('\n')
            text = '\n'.join(lines[first - source['start_line']:last - source['start_line'] + 1])
            if not text.strip():
                raise Fault('empty_model_citation')
            checked.append({**citation, 'quote': text, 'note_id': source['note_id'], 'sha256': source['sha256']})
        claims.append({'text': claim['text'], 'citations': checked, 'basis': 'model_interpretation_not_verified_fact'})
    return claims


def export_markdown(result):
    # Render source bodies as literal fenced text: a note cannot inject an active
    # HTML element or an image/link into a conventional Markdown preview.
    def label(value):
        escaped = html.escape(value, quote=False)
        return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", escaped)
    out = ['# ALFRED evidence packet', '', '> Indexed source excerpts. This export does not change a vault or grant authority.', '',
           '**Question:** ' + label(result['packet']['question']), '', '**Mode:** ' + label(result['mode']), '',
           '**Status:** ' + label(result['status']), '']
    for source in result['packet']['evidence']:
        path = quote(source['path'], safe='/')
        out += ['## ' + label(source['source_id'] + ': ' + source['title']), '',
                '[' + source['source_id'] + ' source note](' + path + ')', '',
                'Lines ' + str(source['start_line']) + ' to ' + str(source['end_line']) + '; revision ' + str(source['revision']) + '.', '',
                'SHA-256: `' + source['sha256'] + '`', '']
        runs = re.findall(r'`+', source['excerpt'])
        fence = '`' * max(3, 1 + max((len(run) for run in runs), default=0))
        out += [fence + 'text', source['excerpt'], fence, '']
    out += ['---', 'This is a portable evidence packet, not a verified answer. Relative links need the original vault context.',
            'Model interpretations are intentionally not included in this source export.', '']
    return '\n'.join(out)


def ask(store, bearer, body, provider=None, provider_scope=None):
    exact(body, {'question', 'mode'})
    if body['mode'] not in ('sources', 'local_model'):
        raise Fault('invalid_answer_mode')
    principal = store.principal(bearer, {'owner', 'reader'})
    question_terms(body['question'])
    use_model = body['mode'] == 'local_model'
    if use_model:
        if provider is None:
            raise Fault('local_model_not_configured', 409)
        if principal['role'] != 'owner' or principal['scope'] != provider_scope:
            raise Fault('model_workspace_not_authorised', 403)
        if store.paused(principal['scope']):
            raise Fault('model_processing_paused', 409)
    packet = retrieve(store, bearer, body['question'])
    result = {'packet': packet, 'mode': body['mode'], 'status': 'sources_found' if packet['evidence'] else 'no_sources',
              'claims': [], 'model_used': False, 'content_sent_to_model': False, 'model': None,
              'citation_integrity': 'indexed_source_lines_and_hashes', 'semantic_entailment_verified': False,
              'actions_executed': False, 'stored_in_browser': False}
    if use_model and packet['evidence']:
        # Recheck right at egress. Local endpoint credentials are never model input.
        store.principal(bearer, {'owner'})
        if not check_sources(store, bearer, references(packet))['current_index_match']:
            raise Fault('sources_changed_during_question', 409)
        if store.paused(principal['scope']):
            raise Fault('model_processing_paused', 409)
        result['content_sent_to_model'] = True
        try:
            value = provider.generate(packet)
            claims = validate_interpretation(value, packet)
            result.update(claims=claims, status='model_interpretation' if claims else 'model_abstained',
                          model_used=True, model=provider.model)
        except Exception:
            # Never expose unvalidated response text or provider exceptions/secrets.
            result['status'] = 'model_unavailable_or_invalid'
    current = store.principal(bearer, {'owner', 'reader'})
    if current['scope'] != principal['scope'] or (use_model and store.paused(current['scope'])):
        raise Fault('question_context_changed', 409)
    if not check_sources(store, bearer, references(packet))['current_index_match']:
        raise Fault('sources_changed_during_question', 409)
    result['export_markdown'] = export_markdown(result)
    return result
