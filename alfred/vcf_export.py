"""Owner-selected vCard export reader (RFC 6350 version 4.0, tolerating 3.0).

Pure functions over bytes; nothing is fetched, written or executed. Reads FN, N,
ORG, TITLE, NOTE, UID, KIND and REV, and EMAIL and TEL only under their own
scopes. Photos, postal addresses, birthdays, keys, related people, positions and
X- properties are never read. A card becomes a source document about a contact:
at most a candidate for an entity the owner creates explicitly, never merged with
an entity or a namesake, never an accepted fact.
"""
from __future__ import annotations
import datetime as dt
import re
from .local import Fault
from .contentline import components, logical_lines, one_line, split_unescaped, text_block, unescape

MAX_BYTES, MAX_ITEMS = 1048576, 1000
SCOPE, EMAIL, TELEPHONE = 'contacts.read', 'contacts.email.read', 'contacts.telephone.read'
PROVENANCE = 'Imported contact card: a report of what the selected export contained; not a reviewed entity or a verified fact.'
N_PARTS = ('family name', 'given name', 'additional names', 'honorific prefix', 'honorific suffix')
N_ORDER = (3, 1, 2, 0, 4)
KINDS = {'individual': None, 'org': 'organisation', 'group': 'group', 'location': 'location'}
SINGLE = ('FN', 'N', 'ORG', 'TITLE', 'UID', 'KIND', 'REV')
AT_MOST_ONCE = ('N', 'UID', 'KIND', 'REV')
_STAMP = re.compile(r'(\d{4})-?(\d{2})-?(\d{2})(?:T(\d{2}):?(\d{2}):?(\d{2})Z)?')
_TYPE = re.compile(r'[a-z][a-z-]{0,19}')
_IGNORED_TYPES = {'internet', 'x400', 'pref'}


def _text(value, issues, limit=None):
    text, clean = unescape(value)
    if not clean:
        issues.add('invalid_text_escape')
    return one_line(text, limit) if limit else text


def _channel(params, value, issues, limit, telephone=False):
    types, preferred = set(), False
    for raw in params.get('TYPE', []):
        for part in raw.split(','):
            part = part.strip().lower()
            preferred = preferred or part == 'pref'
            if _TYPE.fullmatch(part) and part not in _IGNORED_TYPES:
                types.add(part)
    pref = (params.get('PREF') or [''])[0]
    rank = int(pref) if re.fullmatch(r'[1-9]\d?|100', pref) else (1 if preferred else 101)
    if telephone and [v.lower() for v in params.get('VALUE', [])] == ['uri']:
        value = re.sub(r'(?i)^tel:', '', value)
        text = one_line(value, limit)
    else:
        text = _text(value, issues, limit)
    return (rank, text.casefold(), text, sorted(types) + (['preferred'] if rank == 1 else [])) if text else None


def _stamp(value, issues):
    match = _STAMP.fullmatch(value.strip())
    try:
        if not match:
            raise ValueError
        parts = [int(p) for p in match.groups() if p is not None]
        moment = dt.datetime(*parts, tzinfo=dt.timezone.utc) if len(parts) == 6 else dt.datetime(*parts[:3], tzinfo=dt.timezone.utc)
        return int(moment.timestamp())
    except ValueError:
        issues.add('unreadable_rev')
        return None


def read_card(card):
    issues, first, notes, emails, phones = set(), {}, [], [], []
    if card['children']:
        issues.add('nested_component_ignored')
    versions = [value.strip() for name, _, value in card['properties'] if name == 'VERSION']
    for name, params, value in card['properties']:
        if params.get('ENCODING'):
            # QUOTED-PRINTABLE and BASE64 values are not decoded or kept.
            if name in SINGLE + ('NOTE', 'EMAIL', 'TEL'):
                issues.add('unsupported_encoding')
            continue
        if name in SINGLE:
            if name in first:
                if name in AT_MOST_ONCE:
                    issues.add('repeated_' + name.lower())
                continue
            first[name] = (params, value)
        elif name == 'NOTE':
            notes.append(_text(value, issues))
        elif name == 'EMAIL':
            emails.append((params, value))
        elif name == 'TEL':
            phones.append((params, value))
    uid = _text(first['UID'][1], issues).strip() if 'UID' in first else ''
    item = {'component': 'VCARD', 'uid': uid or None, 'scope': SCOPE, 'folder': 'contact', 'skip': None}
    if not versions:
        issues.add('missing_vcard_version')
    elif versions[0] not in ('3.0', '4.0') or len(versions) > 1:
        # vCard 2.1 needs encodings and parameter forms this reader does not decode.
        return item | {'skip': 'unsupported_vcard_version', 'issues': sorted(issues)}
    n_parts = None
    if 'N' in first:
        parts = split_unescaped(first['N'][1], ';')
        if len(parts) > 5:
            issues.add('unreadable_n')
        n_parts = [', '.join(filter(None, (one_line(unescape(x)[0], 80) for x in split_unescaped(p, ',')))) for p in parts[:5]]
        n_parts += [''] * (5 - len(n_parts))
    organisation = []
    if 'ORG' in first:
        organisation = [p for p in (one_line(unescape(x)[0], 120) for x in split_unescaped(first['ORG'][1], ';')) if p]
    name = _text(first['FN'][1], issues, 160) if 'FN' in first else ''
    if not name:
        issues.add('missing_fn')
        name = one_line(' '.join(filter(None, (n_parts or [''] * 5)[1::-1])), 160) if n_parts else ''
        name = name or (organisation[0] if organisation else 'Unnamed contact')
    kind = (_text(first['KIND'][1], issues, 40).lower() if 'KIND' in first else 'individual') or 'individual'
    entries = {'emails': (emails, 254, False), 'phones': (phones, 64, True)}
    channels = {}
    for field, (found, limit, telephone) in entries.items():
        kept = sorted(filter(None, (_channel(p, v, issues, limit, telephone) for p, v in found)))
        channels[field] = [(text, types) for _, _, text, types in kept[:8]]
        channels[field + '_count'] = len(found)
    return item | {'name': name, 'n': n_parts, 'organisation': organisation,
                   'title': _text(first['TITLE'][1], issues, 120) if 'TITLE' in first else None,
                   'kind': kind, 'note': '\n\n'.join(n for n in notes if n.strip()),
                   'modified': _stamp(first['REV'][1], issues) if 'REV' in first else None,
                   **channels, 'issues': sorted(issues)}


def parse(raw):
    """Every VCARD in the file, bounded. Anything else at the top level refuses the file."""
    if not raw.strip():
        raise Fault('export_empty')
    if len(raw) > MAX_BYTES:
        raise Fault('export_too_large')
    roots = components(logical_lines(raw), bare_parameters=True)
    if not roots or any(root['name'] != 'VCARD' for root in roots):
        raise Fault('vcard_required')
    if len(roots) > MAX_ITEMS:
        raise Fault('export_item_capacity')
    return {'items': [read_card(root) for root in roots], 'ignored_components': {}}


def key(item):
    return None if item['uid'] is None else ('VCARD', item['uid'])


def origin_revision(item):
    return None, item.get('modified')


def render(item, scopes):
    kind = KINDS.get(item['kind'], 'other')
    role = ', '.join(filter(None, (item['title'], item['organisation'][0] if item['organisation'] else None)))
    lines = ['# ' + item['name'], ('Contact card' + (f' ({kind})' if kind else '')) + (': ' + role if role else '') + '.', PROVENANCE]
    if item['n'] and any(item['n']):
        lines.append('Name parts: ' + '; '.join(f'{N_PARTS[i]} {item["n"][i]}' for i in N_ORDER if item['n'][i]))
    if item['organisation']:
        lines.append('Organisation: ' + '; '.join(item['organisation']))
    if item['title']:
        lines.append('Job title: ' + item['title'])
    if kind:
        lines.append('Kind in the export: ' + (kind if kind != 'other' else one_line(item['kind'], 40)))
    for field, scope, label, noun in (('emails', EMAIL, 'Email', 'email address'), ('phones', TELEPHONE, 'Telephone', 'telephone number')):
        count = item[field + '_count']
        if scope in scopes:
            for text, types in item[field]:
                lines.append(f'{label}' + (f" ({', '.join(types)})" if types else '') + ': ' + text)
            if count > len(item[field]):
                lines.append(f"{label}: {count - len(item[field])} more not imported (limit 8)")
        elif count:
            lines.append(f"{label}: {count} {noun}{'' if count == 1 else 'es' if noun.endswith('ss') else 's'} in the export, not imported under this connector's scopes.")
    if item['modified'] is not None:
        lines.append('Origin revision: ' + dt.datetime.fromtimestamp(item['modified'], dt.timezone.utc).strftime('%Y-%m-%d %H:%M') + ' UTC')
    if item['note']:
        lines.append('Note:')
        lines.extend(text_block(item['note'], 2000, 60))
    return {'title': item['name'], 'kind': 'person' if kind is None else 'note',
            'tags': ['contact'] + ([kind] if kind else []), 'body': '\n'.join(lines) + '\n'}
