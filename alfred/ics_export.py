"""Owner-selected iCalendar export reader (RFC 5545): VEVENT and VTODO only.

Pure functions over bytes; nothing is fetched, written or executed. Every time keeps
its stated basis: UTC, an IANA zone resolved with the system zoneinfo database,
floating local time, an all-day date, or an explicitly unresolved time zone.
Windows names and other non-IANA identifiers are never guessed, and embedded
VTIMEZONE definitions are not interpreted. Recurrence rules are kept as text and
never expanded, so a stored document depends only on the export and its revisions
reflect changes in the export. Attendee and organiser addresses are never kept;
display names only under the calendar.participants.read scope.
"""
from __future__ import annotations
import datetime as dt
import functools
import re
import zoneinfo
from .local import Fault
from .contentline import components, logical_lines, one_line, split_unescaped, text_block, unescape

MAX_BYTES, MAX_ITEMS = 1048576, 1000
SCOPES = {'VEVENT': 'calendar.events.read', 'VTODO': 'calendar.tasks.read'}
PARTICIPANTS = 'calendar.participants.read'
FOLDERS = {'VEVENT': 'event', 'VTODO': 'task'}
PROVENANCE = {
    'VEVENT': 'Imported calendar event: a report of what the selected export contained, not checked against the calendar itself.',
    'VTODO': 'Imported calendar task: a report of what the selected export contained, not checked against the calendar itself.'}
STATUS = {'VEVENT': {'TENTATIVE': 'tentative', 'CONFIRMED': 'confirmed', 'CANCELLED': 'cancelled'},
          'VTODO': {'NEEDS-ACTION': 'needs action', 'IN-PROCESS': 'in progress', 'COMPLETED': 'completed', 'CANCELLED': 'cancelled'}}
SINGLE = ('UID', 'SUMMARY', 'DESCRIPTION', 'LOCATION', 'STATUS', 'DTSTART', 'DTEND', 'DUE', 'DURATION',
          'RECURRENCE-ID', 'SEQUENCE', 'LAST-MODIFIED', 'CLASS', 'PRIORITY', 'COMPLETED', 'ORGANIZER')
MULTIPLE = ('ATTENDEE', 'CATEGORIES', 'EXDATE', 'RDATE', 'RRULE')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
DAYS = {'MO': 'Monday', 'TU': 'Tuesday', 'WE': 'Wednesday', 'TH': 'Thursday', 'FR': 'Friday', 'SA': 'Saturday', 'SU': 'Sunday'}
UNITS = {'DAILY': ('day', 'days'), 'WEEKLY': ('week', 'weeks'), 'MONTHLY': ('month', 'months'), 'YEARLY': ('year', 'years')}
_DATE = re.compile(r'(\d{4})(\d{2})(\d{2})')
_DATE_TIME = re.compile(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)')
_DURATION = re.compile(r'([+-]?)P(?:(\d{1,4})W|(\d{1,5}D)?(T(?:\d{1,6}H)?(?:\d{1,7}M)?(?:\d{1,8}S)?)?)')
_TZID = re.compile(r'[A-Za-z0-9_+-]{1,40}(?:/[A-Za-z0-9_+-]{1,40}){0,3}')
_RULE_PART = re.compile(r'[A-Z]{2,10}=[A-Za-z0-9,:+-]{1,120}')
# Host-dependent or placeholder keys that the zoneinfo path can contain. Resolving
# 'localtime' would silently adopt this computer's zone, which is a guess.
_NOT_ZONES = {'localtime', 'Factory', 'posixrules'}
UTC = dt.timezone.utc


@functools.lru_cache(maxsize=1)
def iana_zones():
    return frozenset(k for k in zoneinfo.available_timezones()
                     if k not in _NOT_ZONES and not k.startswith(('posix/', 'right/')))


def zone(tzid):
    if not isinstance(tzid, str) or not _TZID.fullmatch(tzid) or tzid not in iana_zones():
        return None
    try:
        return zoneinfo.ZoneInfo(tzid)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
        return None


def read_time(value, params, issues, field):
    """One DATE or DATE-TIME with its stated basis, or None (reported) when unreadable."""
    value = value.strip()
    kind = (params.get('VALUE') or [''])[0].upper()
    tzid = (params.get('TZID') or [None])[0]
    try:
        if kind == 'DATE' or (not kind and _DATE.fullmatch(value)):
            match = _DATE.fullmatch(value)
            if not match:
                raise ValueError
            return {'basis': 'date', 'date': dt.date(int(match[1]), int(match[2]), int(match[3]))}
        match = _DATE_TIME.fullmatch(value)
        if not match or kind not in ('', 'DATE-TIME'):
            raise ValueError
        naive = dt.datetime(*(int(part) for part in match.groups()[:6]))
    except ValueError:
        issues.add('unreadable_' + field)
        return None
    if match[7]:
        if tzid is not None:
            issues.add('utc_time_with_tzid')
        return {'basis': 'utc', 'utc': naive.replace(tzinfo=UTC)}
    if tzid is None:
        return {'basis': 'floating', 'local': naive}
    found = zone(tzid)
    if found is None:
        issues.add('unresolved_timezone')
        return {'basis': 'unresolved_timezone', 'tzid': one_line(tzid, 64), 'local': naive}
    first, second = naive.replace(tzinfo=found, fold=0), naive.replace(tzinfo=found, fold=1)
    note = None
    if first.utcoffset() != second.utcoffset():
        # RFC 5545 3.3.5: a skipped local time uses the offset before the gap and a
        # repeated one its first occurrence. Python's fold=0 does both; say so.
        back = first.astimezone(UTC).astimezone(found).replace(tzinfo=None)
        note = 'nonexistent_local_time' if back != naive else 'ambiguous_local_time'
        issues.add(note)
    return {'basis': 'zoned', 'tzid': tzid, 'local': naive, 'utc': first.astimezone(UTC), 'note': note}


def read_duration(value):
    match = _DURATION.fullmatch(value.strip())
    if not match or match[1] == '-' or not any(match.groups()[1:]) or match[4] == 'T':
        return None
    clock = match[4] or ''
    def number(unit, text):
        found = re.search(r'(\d+)' + unit, text)
        return int(found[1]) if found else 0
    return {'days': int(match[2] or 0) * 7 + number('D', match[3] or ''),
            'seconds': number('H', clock) * 3600 + number('M', clock) * 60 + number('S', clock)}


def add_duration(start, duration, issues):
    """Nominal days move the local date; hours, minutes and seconds are exact (RFC 5545 3.3.6)."""
    days, seconds = dt.timedelta(days=duration['days']), dt.timedelta(seconds=duration['seconds'])
    try:
        if start['basis'] == 'date':
            if duration['seconds']:
                issues.add('duration_not_whole_days')
                return None
            return {'basis': 'date', 'date': start['date'] + days}
        if start['basis'] == 'utc':
            return {'basis': 'utc', 'utc': start['utc'] + days + seconds}
        if start['basis'] != 'zoned':
            return {**start, 'local': start['local'] + days + seconds}
        found = zone(start['tzid'])
        instant = (start['local'] + days).replace(tzinfo=found, fold=0).astimezone(UTC) + seconds
        return {'basis': 'zoned', 'tzid': start['tzid'], 'local': instant.astimezone(found).replace(tzinfo=None),
                'utc': instant, 'note': None}
    except OverflowError:
        issues.add('unreadable_duration')
        return None


def _ordinal(value):
    if value is None:
        return None
    if value['basis'] in ('utc', 'zoned'):
        return ('instant', value['utc'])
    if value['basis'] == 'date':
        return ('date', value['date'])
    return (value['basis'], value.get('tzid'), value['local'])


def _clock(value):
    return value.strftime('%Y-%m-%d %H:%M:%S' if value.second else '%Y-%m-%d %H:%M')


def describe(value):
    if value is None:
        return 'not readable in the export'
    basis = value['basis']
    if basis == 'date':
        return value['date'].isoformat() + ' (all day)'
    if basis == 'utc':
        return _clock(value['utc']) + ' UTC'
    if basis == 'floating':
        return _clock(value['local']) + ' floating local time (no time zone stated)'
    if basis == 'unresolved_timezone':
        return f"{_clock(value['local'])} in time zone \"{value['tzid']}\", which was not resolved, so not converted"
    text = f"{_clock(value['local'])} {value['tzid']} ({_clock(value['utc'])} UTC)"
    if value['note'] == 'nonexistent_local_time':
        text += '; this local time does not exist on that date because of a clock change, so the offset before the change was used'
    elif value['note'] == 'ambiguous_local_time':
        text += '; this local time occurs twice on that date, so the first occurrence was used'
    return text


def _day(value):
    return f'{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]} {value.year}'


def _wall(value):
    # The time as the export stated it: UTC for UTC values, otherwise the local wall time.
    return value['utc'] if value['basis'] == 'utc' else value['local']


def _brief(value, end=None):
    """Short form for the first summary line: the stated time and its basis."""
    if value['basis'] == 'date':
        return _day(value['date'])
    moment = _wall(value)
    span = moment.strftime('%H:%M')
    if end is not None and end['basis'] == value['basis'] and end.get('tzid') == value.get('tzid'):
        finish = _wall(end)
        if finish.date() == moment.date() and finish >= moment:
            span += ' to ' + finish.strftime('%H:%M')
    zone_text = {'utc': 'UTC', 'floating': 'floating local time', 'zoned': value.get('tzid'),
                 'unresolved_timezone': f"unresolved time zone \"{value.get('tzid')}\""}[value['basis']]
    return f'{_day(moment)}, {span} ({zone_text})'


def recurrence_key(value, params, issues):
    """Stable identity for RECURRENCE-ID: the same instant written differently is the same key."""
    time = read_time(value, params, issues, 'recurrence_id')
    if time is None:
        key = 'raw:' + one_line(value, 80)
    elif time['basis'] in ('utc', 'zoned'):
        key = 'utc:' + time['utc'].strftime('%Y%m%dT%H%M%SZ')
    elif time['basis'] == 'date':
        key = 'date:' + time['date'].isoformat()
    elif time['basis'] == 'floating':
        key = 'floating:' + time['local'].isoformat()
    else:
        key = 'tz:' + time['tzid'] + ':' + time['local'].isoformat()
    if [r.upper() for r in params.get('RANGE', [])] == ['THISANDFUTURE']:
        key += ';thisandfuture'
    return key, time


def describe_rule(rule):
    """Plain words for simple rules only; anything else is left uninterpreted."""
    segments = rule.split(';')
    if not all(_RULE_PART.fullmatch(segment) for segment in segments):
        return None
    parts = dict(segment.split('=', 1) for segment in segments)
    if len(parts) != len(segments) or set(parts) - {'FREQ', 'INTERVAL', 'COUNT', 'UNTIL', 'BYDAY', 'WKST'} or parts.get('FREQ') not in UNITS:
        return None
    if ('COUNT' in parts and 'UNTIL' in parts) or not re.fullmatch(r'[1-9]\d{0,2}', parts.get('INTERVAL', '1')):
        return None
    interval = int(parts.get('INTERVAL', '1'))
    single, plural = UNITS[parts['FREQ']]
    text = 'every ' + (single if interval == 1 else f'{interval} {plural}')
    if 'BYDAY' in parts:
        days = parts['BYDAY'].split(',')
        if parts['FREQ'] != 'WEEKLY' or not all(d in DAYS for d in days):
            return None
        names = [DAYS[d] for d in days]
        text += ' on ' + (names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1])
    if 'COUNT' in parts:
        if not re.fullmatch(r'[1-9]\d{0,5}', parts['COUNT']):
            return None
        text += ', once' if parts['COUNT'] == '1' else f", {parts['COUNT']} times"
    if 'UNTIL' in parts:
        until = read_time(parts['UNTIL'], {}, set(), 'until')
        if until is None or until['basis'] not in ('date', 'utc', 'floating'):
            return None
        text += ', until ' + describe(until).replace(' (all day)', '')
    return text


def _text(entry, issues, limit=None):
    if entry is None:
        return None
    value, clean = unescape(entry[1])
    if not clean:
        issues.add('invalid_text_escape')
    return one_line(value, limit) if limit else value


def _name(params):
    # Display names only. A CN that is itself an address is dropped, not kept.
    name = one_line((params.get('CN') or [''])[0], 80)
    return name if name and '@' not in name and ':' not in name else None


def read_item(component):
    issues, single, multiple = set(), {}, {name: [] for name in MULTIPLE}
    for name, params, value in component['properties']:
        if name in SINGLE:
            if name in single:
                issues.add('repeated_' + name.lower().replace('-', '_'))
                continue
            single[name] = (params, value)
        elif name in MULTIPLE:
            multiple[name].append((params, value))
    kind = component['name']
    uid = _text(single.get('UID'), issues)
    uid = uid if uid and uid.strip() else None
    recurrence, recurrence_time = None, None
    if 'RECURRENCE-ID' in single:
        recurrence, recurrence_time = recurrence_key(single['RECURRENCE-ID'][1], single['RECURRENCE-ID'][0], issues)
    times = {}
    for field in ('DTSTART', 'DTEND', 'DUE', 'COMPLETED'):
        if field in single:
            times[field] = read_time(single[field][1], single[field][0], issues, field.lower())
    end_field, from_duration = ('DTEND' if kind == 'VEVENT' else 'DUE'), False
    if 'DURATION' in single:
        duration = read_duration(single['DURATION'][1])
        if duration is None:
            issues.add('unreadable_duration')
        elif end_field in single:
            issues.add('duration_and_end_both_stated')
        elif times.get('DTSTART'):
            times[end_field], from_duration = add_duration(times['DTSTART'], duration, issues), True
    first, last = _ordinal(times.get('DTSTART')), _ordinal(times.get(end_field))
    if first and last and first[0] == last[0] and first[:-1] == last[:-1] and last[-1] < first[-1]:
        issues.add('end_before_start')
    status = (_text(single.get('STATUS'), issues, 40) or '').upper() or None
    if status is not None and status not in STATUS[kind]:
        issues.add('unrecognised_status')
    sequence = None
    if 'SEQUENCE' in single:
        raw = single['SEQUENCE'][1].strip()
        if re.fullmatch(r'\d{1,9}', raw):
            sequence = int(raw)
        else:
            issues.add('unreadable_sequence')
    modified = None
    if 'LAST-MODIFIED' in single:
        stamp = read_time(single['LAST-MODIFIED'][1], single['LAST-MODIFIED'][0], issues, 'last_modified')
        if stamp is not None and stamp['basis'] == 'utc':
            modified = int(stamp['utc'].timestamp())
        elif stamp is not None:
            issues.add('last_modified_not_utc')
    rules = [one_line(value, 300) for _, value in multiple['RRULE']]
    for rule in rules:
        if 'FREQ' not in [p.split('=', 1)[0] for p in rule.split(';')] or not all(_RULE_PART.fullmatch(p) for p in rule.split(';')):
            issues.add('unreadable_recurrence_rule')
    if len(rules) > 1:
        issues.add('repeated_rrule')
    dates = {}
    for field in ('EXDATE', 'RDATE'):
        found, count = [], 0
        for params, value in multiple[field]:
            if (params.get('VALUE') or [''])[0].upper() == 'PERIOD':
                count += len(value.split(','))
                issues.add('rdate_period_not_interpreted')
                continue
            for part in value.split(','):
                count += 1
                if len(found) < 8:
                    found.append(describe(read_time(part, params, issues, field.lower())))
        dates[field] = (count, found)
    names, unnamed = [], 0
    for params, _ in multiple['ATTENDEE']:
        name = _name(params)
        if name:
            names.append(name)
        else:
            unnamed += 1
    categories = []
    for params, value in multiple['CATEGORIES']:
        for part in split_unescaped(value, ','):
            label = one_line(unescape(part)[0], 40)
            if label and label not in categories and len(categories) < 8:
                categories.append(label)
    priority = None
    if 'PRIORITY' in single:
        raw = single['PRIORITY'][1].strip()
        priority = int(raw) if re.fullmatch(r'[0-9]', raw) else None
        if priority is None:
            issues.add('unreadable_priority')
    classification = (_text(single.get('CLASS'), issues, 40) or '').upper() or None
    return {'component': kind, 'uid': uid, 'recurrence': recurrence, 'recurrence_time': recurrence_time,
            'scope': SCOPES[kind], 'folder': FOLDERS[kind], 'times': times, 'end_field': end_field,
            'end_from_duration': from_duration,
            'summary': _text(single.get('SUMMARY'), issues, 160),
            'location': _text(single.get('LOCATION'), issues, 200),
            'description': _text(single.get('DESCRIPTION'), issues),
            'status': status, 'sequence': sequence, 'modified': modified, 'rules': rules[:2], 'dates': dates,
            'organiser': _name(single['ORGANIZER'][0]) if 'ORGANIZER' in single else None,
            'organiser_stated': 'ORGANIZER' in single,
            'attendees': sorted(set(names), key=lambda n: (n.casefold(), n)), 'unnamed_attendees': unnamed,
            'attendee_count': len(multiple['ATTENDEE']), 'categories': categories,
            'priority': priority, 'classification': classification, 'issues': sorted(issues)}


def parse(raw):
    """All VEVENT and VTODO components of every VCALENDAR in the file, bounded."""
    if not raw.strip():
        raise Fault('export_empty')
    if len(raw) > MAX_BYTES:
        raise Fault('export_too_large')
    roots = components(logical_lines(raw))
    if not roots or any(root['name'] != 'VCALENDAR' for root in roots):
        raise Fault('ics_calendar_required')
    items, ignored = [], {}
    for calendar in roots:
        versions = [value.strip() for name, _, value in calendar['properties'] if name == 'VERSION']
        if versions != ['2.0']:
            raise Fault('ics_version_unsupported')
        # An export publishes a calendar. A scheduling message (an invitation, reply or
        # cancellation) is not a complete snapshot, so importing it could remove everything else.
        if any(value.strip().upper() != 'PUBLISH' for name, _, value in calendar['properties'] if name == 'METHOD'):
            raise Fault('ics_scheduling_message_not_an_export')
        for child in calendar['children']:
            if child['name'] in SCOPES:
                if len(items) >= MAX_ITEMS:
                    raise Fault('export_item_capacity')
                items.append(read_item(child))
            else:
                ignored[child['name']] = ignored.get(child['name'], 0) + 1
    return {'items': items, 'ignored_components': dict(sorted(ignored.items()))}


def key(item):
    """UID plus RECURRENCE-ID within one component type; None when the export gave no UID."""
    return None if item['uid'] is None else (item['component'], item['uid'], item['recurrence'] or '')


def origin_revision(item):
    return item['sequence'], item['modified']


def _summary_line(item):
    event = item['component'] == 'VEVENT'
    status = STATUS[item['component']].get(item['status'] or '')
    start, end = item['times'].get('DTSTART'), item['times'].get(item['end_field'])
    if event:
        if start is None:
            text = 'Event with no readable start time'
        elif start['basis'] == 'date':
            # DTEND of an all-day event is exclusive.
            last = end['date'] - dt.timedelta(days=1) if end and end['basis'] == 'date' else None
            text = 'All-day event on ' + _day(start['date']) if not last or last <= start['date'] else (
                f"All-day event from {_day(start['date'])} to {_day(last)}")
        else:
            text = 'Event on ' + _brief(start, end)
    else:
        due = item['times'].get('DUE')
        text = ('Task due ' + _brief(due)) if due else (
            'Task with an unreadable due date' if 'DUE' in item['times'] else 'Task with no due date')
    if item['rules'] or item['recurrence']:
        text += '; part of a repeating series'
    if status:
        text = (status.capitalize() + '. ' + text) if status == 'cancelled' else text + '; ' + status
    return text + '.'


def render(item, scopes):
    """A deterministic, labelled text document for the existing note pipeline."""
    event = item['component'] == 'VEVENT'
    title = item['summary'] or ('Untitled event' if event else 'Untitled task')
    lines = ['# ' + title, _summary_line(item), PROVENANCE[item['component']]]
    status = STATUS[item['component']].get(item['status'] or '')
    lines.append('Status: ' + (status or ('not stated' if item['status'] is None else 'not recognised')))
    fields = (('DTSTART', 'Starts'), ('DTEND', 'Ends')) if event else (('DTSTART', 'Starts'), ('DUE', 'Due'), ('COMPLETED', 'Completed'))
    if event and 'DTSTART' not in item['times']:
        lines.append('Starts: not stated in the export')
    for field, label in fields:
        if field in item['times']:
            value = item['times'][field]
            derived = ' (calculated from the stated duration)' if field == item['end_field'] and item['end_from_duration'] else ''
            if event and field == 'DTEND' and value and value['basis'] == 'date':
                # An all-day DTEND is exclusive (RFC 5545 3.6.1).
                derived += f"; exclusive, so the last day is {_day(value['date'] - dt.timedelta(days=1))}"
            lines.append(f'{label}: ' + describe(value) + derived)
    if not event and item['priority']:
        lines.append(f"Priority: {item['priority']} (1 is highest)")
    if item['recurrence']:
        lines.append('Recurrence instance: changes the occurrence originally at ' + describe(item['recurrence_time'])
                     + ('; and every later occurrence' if item['recurrence'].endswith(';thisandfuture') else ''))
    for rule in item['rules']:
        words = describe_rule(rule) if 'unreadable_recurrence_rule' not in item['issues'] else None
        lines.append(f'Repeats: {words}. Rule as exported: {rule}. Occurrences are not expanded.' if words
                     else f'Repeats: rule as exported, not interpreted: {rule}. Occurrences are not expanded.')
    for field, label in (('EXDATE', 'Excluded occurrences'), ('RDATE', 'Added occurrences')):
        count, shown = item['dates'][field]
        if count:
            lines.append(f'{label} ({count})' + (': ' + '; '.join(shown) if shown else '') + ('; more not listed' if count > len(shown) else ''))
    if item['location']:
        lines.append('Location: ' + item['location'])
    if PARTICIPANTS in scopes:
        if item['organiser_stated']:
            lines.append('Organiser: ' + (item['organiser'] or 'stated without a display name'))
        if item['attendee_count']:
            named = '; names: ' + ', '.join(item['attendees']) if item['attendees'] else ''
            lines.append(f"Attendees: {item['attendee_count']}{named}" + (f"; {item['unnamed_attendees']} without a display name" if item['unnamed_attendees'] and item['attendees'] else ''))
    elif item['attendee_count'] or item['organiser_stated']:
        counted = f"{item['attendee_count']} attendee(s)" if item['attendee_count'] else 'an organiser only'
        lines.append(f"Participants: {counted}; names are not imported under this connector's scopes.")
    if item['categories']:
        lines.append('Categories: ' + ', '.join(item['categories']))
    if item['classification'] in ('PRIVATE', 'CONFIDENTIAL'):
        lines.append('Classification in the export: ' + item['classification'].lower())
    revision = [f"sequence {item['sequence']}"] if item['sequence'] is not None else []
    if item['modified'] is not None:
        revision.append('last modified ' + _clock(dt.datetime.fromtimestamp(item['modified'], UTC)) + ' UTC')
    if revision:
        lines.append('Origin revision: ' + '; '.join(revision))
    if item['description'] and item['description'].strip():
        lines.append('Description:')
        lines.extend(text_block(item['description'], 4000, 120))
    tags = ['calendar-event' if event else 'calendar-task']
    if item['status'] == 'CANCELLED':
        tags.append('cancelled')
    if item['rules'] or item['recurrence']:
        tags.append('recurring')
    tags += [c for c in item['categories'] if c not in tags]
    return {'title': title, 'kind': 'note', 'tags': tags, 'body': '\n'.join(lines) + '\n'}
