"""Score ALFRED's search against a set of questions the owner writes.

A question set is a JSON file (schema alfred.question-set.v1) of questions, each with a
category (fact, connected, time, preference or refuse), the note paths a good answer must
bring up (expect) and, optionally, note paths that must not come up (avoid). Three
commands:

    python3 tools/question_set.py validate QUESTIONS
    python3 tools/question_set.py run QUESTIONS --vault FOLDER --output REPORT [--ranking keywords|fts5|both]
    python3 tools/question_set.py compare OLD_REPORT NEW_REPORT

`run` builds a throwaway ALFRED store in a temporary folder, scans the Markdown vault
read-only, asks every question through alfred.grounded.retrieve and scores which note
paths came back. The temporary store is deleted when the run ends, also on error.

What the scores are: plain arithmetic over returned note paths. Recall counts how many
expected notes came up, a leak is any avoid note that came up, a refuse question passes
only when nothing came up, and excerpt words count the words of excerpt text returned.
What they are not: lexical recall on one vault is not a quality claim, a returned note is
not proof that it answers the question, and no model, provider or network is used.

Privacy guards. Real questions and their results stay on the owner's computer, so `run`
refuses a questions file, vault or report path inside this repository unless --synthetic
is given for invented test data. The report never overwrites the questions file or
anything that is not an earlier report, and never goes inside the vault. Reports hold
question ids, note paths from the vault, counts and scores; never excerpt text, never the
free `note` fields, and question text only with --include-text.

Exit codes: 0 success; 1 refused or invalid input (one line on stderr); 2 command line
usage; 3 the run finished and wrote its report but an avoid note came up (a leak).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alfred.grounded import MAX_CHARACTERS, MAX_SOURCES, question_terms, retrieve  # noqa: E402
from alfred.knowledge import KnowledgeStore, MarkdownVault, safe_path  # noqa: E402
from alfred.local import Fault  # noqa: E402
from alfred.policy import IdentityPolicy  # noqa: E402

SCHEMA = 'alfred.question-set.v1'
REPORT_SCHEMA = 'alfred.question-set-report.v1'
CATEGORIES = ('fact', 'connected', 'time', 'preference', 'refuse')
RANKINGS = ('keywords', 'fts5')
TOP_FIELDS = ('schema', 'questions', 'note')
QUESTION_FIELDS = ('id', 'category', 'question', 'expect', 'avoid', 'note')
ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
MAX_FILE_BYTES = 2_000_000
MAX_REPORT_BYTES = 50_000_000
MAX_QUESTIONS = 1000
MAX_PATHS = 20
MAX_NOTE = 2000
EXIT_OK, EXIT_ERROR, EXIT_LEAK = 0, 1, 3
WORKSPACE = 'question-set'
SOURCE = 'question-set-vault'
FIXED_NOW = 1790000000
CREDENTIAL_TTL = 2592000
BASIS = (
    'Scores count which note paths alfred.grounded.retrieve returned. They are plain arithmetic: '
    'no model, provider or network is used.',
    'Recall is lexical retrieval on this vault only. It is not a quality claim, and a returned note '
    'is not proof that it answers the question.',
    'Excerpt words count the words of excerpt text returned. The text itself is never stored in this report.',
    'The temporary ALFRED store built for this run was deleted before this report was written.',
)


class QuestionSetError(ValueError):
    """A refusal with a stable code and a one-line message that never repeats question text."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _field_name(value):
    text = str(value)
    return repr(text[:40] + ('...' if len(text) > 40 else ''))


def _unique_pairs(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise QuestionSetError('duplicate_field', 'the field ' + _field_name(key) + ' appears twice in one object.')
        seen[key] = value
    return seen


def _note_path(value):
    """A vault-relative Markdown path the scanner could index, in the form reports use."""
    if not isinstance(value, str) or not value.lower().endswith('.md'):
        return False
    try:
        safe_path(value)
    except Fault:
        return False
    return not any(part.startswith('.') for part in value.split('/'))


def _paths(value, field, where, *, required):
    if type(value) is not list:
        raise QuestionSetError('wrong_type', where + ': ' + field + ' must be a list of note paths.')
    if required and not value:
        raise QuestionSetError('empty_expect', where + ': expect must list at least one note path.')
    if len(value) > MAX_PATHS:
        raise QuestionSetError('too_many_paths', where + ': ' + field + ' lists more than ' + str(MAX_PATHS) + ' notes.')
    for path in value:
        if not _note_path(path):
            raise QuestionSetError('invalid_path', where + ': each ' + field + ' entry must be a note path inside the '
                                   'vault with forward slashes, such as "people/example.md".')
    if len(set(value)) != len(value):
        raise QuestionSetError('duplicate_path', where + ': ' + field + ' names the same note twice.')
    return list(value)


def _optional_note(container, where):
    if 'note' not in container:
        return
    if not isinstance(container['note'], str):
        raise QuestionSetError('wrong_type', where + ': note must be text.')
    if len(container['note']) > MAX_NOTE:
        raise QuestionSetError('note_too_long', where + ': note is longer than ' + str(MAX_NOTE) + ' characters.')


def _question(item, index, seen):
    where = 'question ' + str(index)
    if not isinstance(item, dict):
        raise QuestionSetError('question_not_object', where + ' must be a JSON object.')
    qid = item.get('id')
    if not isinstance(qid, str) or not ID_PATTERN.fullmatch(qid):
        raise QuestionSetError('invalid_id', where + ': id must be 1 to 64 letters, digits, dots, dashes or '
                               'underscores, starting with a letter or digit.')
    where += ' (' + qid + ')'
    if qid in seen:
        raise QuestionSetError('duplicate_id', where + ': the id is already used by question ' + str(seen[qid]) + '.')
    seen[qid] = index
    unknown = sorted(set(item) - set(QUESTION_FIELDS))
    if unknown:
        raise QuestionSetError('unknown_field', where + ': unknown field ' + _field_name(unknown[0]) + '.')
    category = item.get('category')
    if not isinstance(category, str) or category not in CATEGORIES:
        raise QuestionSetError('invalid_category', where + ': category must be one of fact, connected, time, '
                               'preference or refuse.')
    text = item.get('question')
    if not isinstance(text, str):
        raise QuestionSetError('wrong_type', where + ': question must be text.')
    if not text.strip():
        raise QuestionSetError('empty_question', where + ': question is empty.')
    try:
        question_terms(text)
    except Fault as exc:
        raise QuestionSetError('question_not_askable', where + ': ALFRED cannot ask this question as written ('
                               + exc.code + '); keep it on one line, 3 to 500 characters, with at most 32 '
                               'distinct search words.') from None
    if category == 'refuse':
        if 'expect' in item:
            raise QuestionSetError('expect_on_refuse', where + ': a refuse question must not have expect, because '
                                   'a good answer brings up nothing.')
        expect = []
    else:
        if 'expect' not in item:
            raise QuestionSetError('missing_expect', where + ': expect must list at least one note path.')
        expect = _paths(item['expect'], 'expect', where, required=True)
    avoid = _paths(item.get('avoid', []), 'avoid', where, required=False)
    if set(expect) & set(avoid):
        raise QuestionSetError('expect_avoid_overlap', where + ': a note cannot be in both expect and avoid.')
    _optional_note(item, where)
    return {'id': qid, 'category': category, 'question': text, 'expect': expect, 'avoid': avoid}


def validate_question_set(data):
    """Return the questions in file order, normalised, or raise QuestionSetError."""
    if not isinstance(data, dict):
        raise QuestionSetError('not_an_object', 'the file must hold one JSON object with schema and questions.')
    unknown = sorted(set(data) - set(TOP_FIELDS))
    if unknown:
        raise QuestionSetError('unknown_field', 'unknown top-level field ' + _field_name(unknown[0]) + '.')
    if data.get('schema') != SCHEMA:
        raise QuestionSetError('wrong_schema', 'the schema field must be "' + SCHEMA + '".')
    _optional_note(data, 'the file')
    questions = data.get('questions')
    if type(questions) is not list:
        raise QuestionSetError('questions_not_list', 'questions must be a list.')
    if not questions:
        raise QuestionSetError('no_questions', 'the file has no questions.')
    if len(questions) > MAX_QUESTIONS:
        raise QuestionSetError('too_many_questions', 'the file has more than ' + str(MAX_QUESTIONS) + ' questions.')
    seen = {}
    return [_question(item, index, seen) for index, item in enumerate(questions, 1)]


def parse_question_set(raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise QuestionSetError('questions_not_utf8', 'the questions file is not UTF-8 text.') from None
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as exc:
        raise QuestionSetError('questions_not_json', 'the questions file is not valid JSON (line ' + str(exc.lineno)
                               + ', column ' + str(exc.colno) + ').') from None
    except RecursionError:
        raise QuestionSetError('questions_not_json', 'the questions file is nested too deeply.') from None
    return validate_question_set(data)


def load_question_set(path):
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise QuestionSetError('questions_unreadable', 'the questions file could not be read.') from None
    if len(raw) > MAX_FILE_BYTES:
        raise QuestionSetError('questions_too_large', 'the questions file is larger than '
                               + str(MAX_FILE_BYTES) + ' bytes.')
    return parse_question_set(raw)


def category_counts(questions):
    return {c: sum(q['category'] == c for q in questions) for c in CATEGORIES}


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


def check_inputs(questions, vault, synthetic):
    """Resolve the inputs, following links, and keep real files out of the repository."""
    try:
        questions = Path(questions).resolve(strict=True)
    except (OSError, RuntimeError):
        raise QuestionSetError('questions_unreadable', 'the questions file could not be read.') from None
    if not questions.is_file():
        raise QuestionSetError('questions_unreadable', 'the questions file could not be read.')
    try:
        vault = Path(vault).resolve(strict=True)
    except (OSError, RuntimeError):
        raise QuestionSetError('vault_not_a_folder', 'the vault must be an existing folder.') from None
    if not vault.is_dir():
        raise QuestionSetError('vault_not_a_folder', 'the vault must be an existing folder.')
    if not synthetic:
        if questions.is_relative_to(ROOT):
            raise QuestionSetError('questions_inside_repository', 'the questions file is inside the ALFRED '
                                   'repository; keep real questions outside it, or pass --synthetic for invented data.')
        if vault.is_relative_to(ROOT):
            raise QuestionSetError('vault_inside_repository', 'the vault is inside the ALFRED repository; use a '
                                   'vault outside it, or pass --synthetic for invented data.')
    return questions, vault


def load_report(path):
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError:
        raise QuestionSetError('report_unreadable', 'the report file could not be read.') from None
    if len(raw) > MAX_REPORT_BYTES:
        raise QuestionSetError('not_a_report', 'the file is too large to be a question set report.')
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise QuestionSetError('not_a_report', 'the file is not a question set report.') from None
    if not isinstance(data, dict) or data.get('schema') != REPORT_SCHEMA:
        raise QuestionSetError('not_a_report', 'the file is not a question set report.')
    rankings = data.get('rankings')
    malformed = QuestionSetError('report_malformed', 'the report is incomplete or has been edited.')
    if not isinstance(rankings, dict) or not rankings:
        raise malformed
    for ranking in rankings.values():
        if not (isinstance(ranking, dict) and isinstance(ranking.get('overall'), dict)
                and isinstance(ranking.get('categories'), dict) and type(ranking.get('questions')) is list):
            raise malformed
        if not all(isinstance(q, dict) and isinstance(q.get('id'), str) for q in ranking['questions']):
            raise malformed
    return data


def check_output(output, questions, vault, synthetic):
    """The report path: outside the repository and the vault, and never over another file."""
    try:
        target = Path(output).resolve()
    except (OSError, RuntimeError):
        raise QuestionSetError('output_unusable', 'the report path cannot be used.') from None
    if target.is_dir():
        raise QuestionSetError('output_is_directory', 'the report path is a folder; name a file such as report.json.')
    if not target.parent.is_dir():
        raise QuestionSetError('output_folder_missing', 'the folder for the report does not exist.')
    if not synthetic and target.is_relative_to(ROOT):
        raise QuestionSetError('output_inside_repository', 'the report path is inside the ALFRED repository; write '
                               'real results outside it, or pass --synthetic for invented data.')
    if target == questions or (target.exists() and os.path.samefile(target, questions)):
        raise QuestionSetError('output_is_questions', 'the report path is the questions file; choose another name.')
    if target.is_relative_to(vault):
        raise QuestionSetError('output_inside_vault', 'the report path is inside the vault; keep results out of '
                               'your notes.')
    if target.exists():
        try:
            load_report(target)
        except QuestionSetError:
            raise QuestionSetError('output_not_a_report', 'a file that is not an earlier report already has that '
                                   'name; choose another.') from None
    return target


def _rankings(rankings):
    rankings = tuple(rankings)
    if not rankings or any(r not in RANKINGS for r in rankings) or len(set(rankings)) != len(rankings):
        raise QuestionSetError('unsupported_ranking', 'rankings must be keywords, fts5 or both.')
    if 'fts5' in rankings and not fts5_available():
        raise QuestionSetError('fts5_unavailable', 'this SQLite build has no FTS5, so the fts5 ranking cannot run; '
                               'use --ranking keywords.')
    return rankings


def score_question(question, packet, indexed, include_text=False):
    """Score one retrieval packet. Keeps paths and counts; the excerpt text is only counted."""
    evidence = packet['evidence']
    returned = [e['path'] for e in evidence]
    came_up = set(returned)
    expect, avoid = question['expect'], question['avoid']
    found = sum(path in came_up for path in expect)
    leaked = sorted(path for path in avoid if path in came_up)
    nothing = not returned
    answered = nothing if question['category'] == 'refuse' else found == len(expect)
    entry = {
        'id': question['id'], 'category': question['category'],
        'returned': returned, 'sources': len(returned),
        'expected': len(expect), 'found': found,
        'recall': round(found / len(expect), 4) if expect else None,
        'missed': sorted(path for path in expect if path not in came_up),
        'leaked': leaked, 'leak': bool(leaked), 'returned_nothing': nothing,
        'passed': answered and not leaked,
        'excerpt_words': sum(len(e['excerpt'].split()) for e in evidence),
        'not_in_vault': sorted(path for path in expect + avoid if path not in indexed),
    }
    if include_text:
        entry['question'] = question['question']
    return entry


def _bucket(entries):
    expected = sum(e['expected'] for e in entries)
    found = sum(e['found'] for e in entries)
    refuse = [e for e in entries if e['category'] == 'refuse']
    return {
        'questions': len(entries), 'expected': expected, 'found': found,
        'recall': round(found / expected, 4) if expected else None,
        'complete': sum(e['category'] != 'refuse' and e['found'] == e['expected'] for e in entries),
        'refuse_questions': len(refuse), 'refused': sum(e['returned_nothing'] for e in refuse),
        'leaks': sum(e['leak'] for e in entries), 'leaked_notes': sum(len(e['leaked']) for e in entries),
        'passed': sum(e['passed'] for e in entries),
        'sources': sum(e['sources'] for e in entries), 'excerpt_words': sum(e['excerpt_words'] for e in entries),
    }


def summarise(entries):
    return {'overall': _bucket(entries),
            'categories': {c: _bucket([e for e in entries if e['category'] == c]) for c in CATEGORIES}}


def run_question_set(questions_path, vault, *, rankings=('keywords',), synthetic=False, include_text=False):
    """Ask every question under each ranking against a temporary store built from the vault."""
    questions_path, vault = check_inputs(questions_path, vault, synthetic)
    rankings = _rankings(rankings)
    questions = load_question_set(questions_path)
    with tempfile.TemporaryDirectory(prefix='alfred-question-set-') as tmp:
        store = KnowledgeStore(Path(tmp) / 'ledger.db', clock=lambda: FIXED_NOW)
        owner = store.provision(WORKSPACE, 'question-set-owner', 'owner', ttl=CREDENTIAL_TTL)
        source = store.provision(WORKSPACE, SOURCE, 'source', ttl=CREDENTIAL_TTL)
        try:
            health = MarkdownVault(store, source, vault, 'Question set vault').scan()
        except Fault as exc:
            health = {'status': 'unavailable', 'errors': [{'code': exc.code}]}
        if health['status'] == 'unavailable':
            code = health['errors'][0]['code'] if health['errors'] else 'vault_unavailable'
            raise QuestionSetError('vault_unavailable', 'the vault could not be read (' + code + ').')
        # Workspaces are strict by default: the owner reads the vault only through this grant.
        policy = IdentityPolicy(store)
        policy.grant(owner, SOURCE, 'read', FIXED_NOW + 86400, policy.view(owner)['epoch'])
        indexed = {node['path'] for node in store.knowledge(owner)['nodes']}
        if not indexed:
            raise QuestionSetError('vault_empty', 'the vault has no Markdown notes ALFRED could read.')
        results = {}
        for ranking in rankings:
            entries = []
            for index, question in enumerate(questions, 1):
                try:
                    packet = retrieve(store, owner, question['question'], purpose='read', ranking=ranking)
                except Fault as exc:
                    raise QuestionSetError('retrieval_failed', 'question ' + str(index) + ' (' + question['id']
                                           + ') could not be asked under the ' + ranking + ' ranking ('
                                           + exc.code + ').') from None
                entries.append(score_question(question, packet, indexed, include_text))
            results[ranking] = summarise(entries) | {'questions': entries}
    # Issue codes only, never their paths. The scan keeps at most its first 32 issues.
    issues = {}
    for error in health['errors']:
        issues[error['code']] = issues.get(error['code'], 0) + 1
    named = {path for q in questions for path in q['expect'] + q['avoid']}
    return {
        'schema': REPORT_SCHEMA, 'question_set_schema': SCHEMA,
        'synthetic': bool(synthetic), 'question_text_included': bool(include_text),
        'environment': {'sqlite_version': sqlite3.sqlite_version, 'fts5_available': fts5_available()},
        'limits': {'sources': MAX_SOURCES, 'excerpt_characters': MAX_CHARACTERS},
        'vault': {'status': health['status'], 'notes': len(indexed), 'issues': dict(sorted(issues.items())),
                  'paths_not_in_vault': len(named - indexed)},
        'questions': {'total': len(questions), 'categories': category_counts(questions)},
        'rankings': results,
        'basis': list(BASIS),
    }


def render_report(report):
    return json.dumps(report, indent=1, ensure_ascii=False) + '\n'


def write_report(target, text):
    """Write beside the target and rename over it, so a failed write leaves no half report."""
    handle, temporary = tempfile.mkstemp(prefix='.question-set-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary:
            os.unlink(temporary)


def _plural(count, word):
    return str(count) + ' ' + word + ('' if count == 1 else 's')


def _number(value):
    return 'n/a' if value is None else str(value)


def _change(old, new):
    text = _number(old) + ' -> ' + _number(new)
    if old is not None and new is not None and old != new:
        delta = round(new - old, 4)
        text += ' (' + (format(delta, '+d') if isinstance(delta, int) else
                        format(delta, '+.4f').rstrip('0').rstrip('.')) + ')'
    return text


def _ratio(numerator, denominator):
    return str(numerator) + '/' + str(denominator)


def _line(old, new, kind):
    parts = []
    if kind in ('overall', 'answer'):
        parts.append('recall ' + _change(old['recall'], new['recall']))
        parts.append('complete ' + _ratio(old['complete'], old['questions'] - old['refuse_questions']) + ' -> '
                     + _ratio(new['complete'], new['questions'] - new['refuse_questions']))
    if kind in ('overall', 'refuse'):
        parts.append('refused ' + _ratio(old['refused'], old['refuse_questions']) + ' -> '
                     + _ratio(new['refused'], new['refuse_questions']))
    parts.append('leaks ' + str(old['leaks']) + ' -> ' + str(new['leaks']))
    parts.append('passed ' + _ratio(old['passed'], old['questions']) + ' -> ' + _ratio(new['passed'], new['questions']))
    parts.append('excerpt words ' + _change(old['excerpt_words'], new['excerpt_words']))
    return ', '.join(parts)


def _compare_pair(old_report, new_report, old_name, new_name):
    old, new = old_report['rankings'][old_name], new_report['rankings'][new_name]
    old_ids = [q['id'] for q in old['questions']]
    old_id_set = set(old_ids)
    new_by_id = {q['id']: q for q in new['questions']}
    lines = ['Comparing old ' + old_name + ' with new ' + new_name + '.']
    if old_id_set != set(new_by_id):
        lines.append('Note: the two reports cover different questions, so totals are not like for like.')
    lines.append('vault notes: ' + str(old_report['vault']['notes']) + ' -> ' + str(new_report['vault']['notes']))
    lines.append('overall: ' + _line(old['overall'], new['overall'], 'overall'))
    for category in CATEGORIES:
        a, b = old['categories'][category], new['categories'][category]
        if a['questions'] or b['questions']:
            lines.append(category + ': ' + _line(a, b, 'refuse' if category == 'refuse' else 'answer'))
    changed = []
    for q in old['questions']:
        other = new_by_id.get(q['id'])
        if other is None:
            continue
        parts = []
        if q['category'] != other['category']:
            parts.append('category ' + q['category'] + ' -> ' + other['category'])
        if q['recall'] != other['recall']:
            parts.append('recall ' + _number(q['recall']) + ' -> ' + _number(other['recall']))
        if q['leak'] != other['leak']:
            parts.append('leak appeared' if other['leak'] else 'leak gone')
        if q['category'] == other['category'] == 'refuse' and q['returned_nothing'] != other['returned_nothing']:
            parts.append('now refused' if other['returned_nothing'] else 'no longer refused')
        if parts:
            changed.append('  ' + q['id'] + ': ' + '; '.join(parts))
    lines.append('changed questions:' if changed else 'changed questions: none')
    lines.extend(changed)
    only_old = [i for i in old_ids if i not in new_by_id]
    only_new = [q['id'] for q in new['questions'] if q['id'] not in old_id_set]
    if only_old:
        lines.append('only in old: ' + ', '.join(only_old))
    if only_new:
        lines.append('only in new: ' + ', '.join(only_new))
    return lines


def compare_reports(old, new, old_ranking=None, new_ranking=None):
    """Lines describing the change from one report to another: ids, counts and scores only."""
    if old_ranking is None and new_ranking is None:
        pairs = [(r, r) for r in old['rankings'] if r in new['rankings']]
        if not pairs:
            raise QuestionSetError('no_common_ranking', 'the reports share no ranking; name one from each with '
                                   '--old-ranking and --new-ranking.')
    else:
        old_ranking, new_ranking = old_ranking or new_ranking, new_ranking or old_ranking
        for side, report, name in (('old', old, old_ranking), ('new', new, new_ranking)):
            if name not in report['rankings']:
                raise QuestionSetError('ranking_not_in_report', 'the ' + side + ' report has no ranking named '
                                       + _field_name(name) + '.')
        pairs = [(old_ranking, new_ranking)]
    lines = []
    try:
        for old_name, new_name in pairs:
            if lines:
                lines.append('')
            lines.extend(_compare_pair(old, new, old_name, new_name))
    except (KeyError, TypeError, AttributeError):
        raise QuestionSetError('report_malformed', 'the report is incomplete or has been edited.') from None
    return lines


def _validate_command(args):
    questions = load_question_set(args.questions)
    print('Valid ' + SCHEMA + ' file with ' + _plural(len(questions), 'question') + ':')
    for category, count in category_counts(questions).items():
        print('  ' + category + ' ' + str(count))
    return EXIT_OK


def _run_command(args):
    questions, vault = check_inputs(args.questions, args.vault, args.synthetic)
    target = check_output(args.output, questions, vault, args.synthetic)
    rankings = RANKINGS if args.ranking == 'both' else (args.ranking,)
    report = run_question_set(questions, vault, rankings=rankings, synthetic=args.synthetic,
                              include_text=args.include_text)
    write_report(target, render_report(report))
    vault_health = report['vault']
    print('Report written for ' + _plural(report['questions']['total'], 'question') + ' (vault: '
          + _plural(vault_health['notes'], 'note') + ', status ' + vault_health['status'] + ').')
    for ranking, result in report['rankings'].items():
        o = result['overall']
        print(ranking + ': recall ' + _number(o['recall']) + ' (' + str(o['found']) + ' of ' + str(o['expected'])
              + ' expected notes), complete ' + _ratio(o['complete'], o['questions'] - o['refuse_questions'])
              + ', refused ' + _ratio(o['refused'], o['refuse_questions']) + ', leaks ' + str(o['leaks'])
              + ', passed ' + _ratio(o['passed'], o['questions']) + ', excerpt words ' + str(o['excerpt_words']))
    missing = vault_health['paths_not_in_vault']
    if missing:
        print('warning: ' + _plural(missing, 'note path') + ' named in expect or avoid ' + ('is' if missing == 1 else 'are')
              + ' not in the vault; see not_in_vault in the report.', file=sys.stderr)
    leaked = False
    for ranking, result in report['rankings'].items():
        for entry in result['questions']:
            if entry['leak']:
                leaked = True
                print('LEAK: ' + entry['id'] + ' brought up ' + _plural(len(entry['leaked']), 'note')
                      + ' it must avoid (' + ranking + ').', file=sys.stderr)
    return EXIT_LEAK if leaked else EXIT_OK


def _compare_command(args):
    old, new = load_report(args.old), load_report(args.new)
    print('\n'.join(compare_reports(old, new, args.old_ranking, args.new_ranking)))
    return EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(description='Score ALFRED search against a question set. Offline; '
                                     'reports hold ids and scores, not note or question text.')
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate', help='check a questions file and count its categories')
    validate.add_argument('questions', type=Path)
    run = commands.add_parser('run', help='ask every question against a vault and write a report')
    run.add_argument('questions', type=Path)
    run.add_argument('--vault', type=Path, required=True, help='the Markdown folder to search (read only)')
    run.add_argument('--output', type=Path, required=True, help='where to write the JSON report')
    run.add_argument('--ranking', choices=RANKINGS + ('both',), default='keywords',
                     help='which search ranking to score (default keywords, the current default)')
    run.add_argument('--synthetic', action='store_true',
                     help='allow paths inside the repository, for invented test data only')
    run.add_argument('--include-text', action='store_true', help='also store each question text in the report')
    compare = commands.add_parser('compare', help='show what changed between two reports')
    compare.add_argument('old', type=Path)
    compare.add_argument('new', type=Path)
    compare.add_argument('--old-ranking', help='ranking to read from the old report')
    compare.add_argument('--new-ranking', help='ranking to read from the new report')
    args = parser.parse_args(argv)
    handler = {'validate': _validate_command, 'run': _run_command, 'compare': _compare_command}[args.command]
    try:
        return handler(args)
    except QuestionSetError as exc:
        print('error (' + exc.code + '): ' + str(exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
