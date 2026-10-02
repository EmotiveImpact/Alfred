"""Bounded reader for RFC 5545 and RFC 6350 content lines. Text in, data out.

Shared by the iCalendar and vCard export readers. Folded lines are joined at the
byte level, so a producer that splits a multi-byte character across a fold still
decodes; the joined line must then be strict UTF-8. Every structural limit refuses
the whole file rather than truncating it. Nothing here treats a value as an
instruction, a link or a path.
"""
from __future__ import annotations
import re
from .local import Fault

MAX_LINE_BYTES = 65536
MAX_LINES = 50000
MAX_PARAMS, MAX_PARAM_VALUES = 32, 32
MAX_DEPTH, MAX_COMPONENTS, MAX_PROPERTIES = 6, 5000, 2048
_BREAK = re.compile(rb'\r\n|\r|\n')
_NAME = re.compile(r'(?:[A-Za-z0-9-]{1,64}\.)?([A-Za-z0-9-]{1,64})')
_PARAM = re.compile(r'([A-Za-z0-9-]{1,64})')
_CONTROL = re.compile('[\x00-\x08\x0a-\x1f\x7f-\x9f]')
_SEPARATOR = re.compile('[  ]')
_CARET = {'^': '^', 'n': '\n', "'": '"'}


def logical_lines(raw):
    """Physical lines end in CRLF, LF or a lone CR. A leading space or tab continues one."""
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    chunks, blank = [], False
    for line in _BREAK.split(raw):
        if line[:1] in (b' ', b'\t'):
            if not chunks or blank:
                raise Fault('export_malformed_fold')
            chunks[-1].append(line[1:])
        elif line:
            if len(chunks) >= MAX_LINES:
                raise Fault('export_line_capacity')
            chunks.append([line])
        blank = not line
    lines = []
    for parts in chunks:
        joined = b''.join(parts)
        if len(joined) > MAX_LINE_BYTES:
            raise Fault('export_line_too_long')
        try:
            value = joined.decode('utf-8')
        except UnicodeError:
            raise Fault('export_not_utf8') from None
        if _CONTROL.search(value):
            raise Fault('export_control_character')
        lines.append(value)
    return lines


def _caret(value):
    # RFC 6868 parameter encoding: ^^, ^n and ^' only; anything else stays literal.
    return re.sub(r"\^([\^n'])", lambda m: _CARET[m[1]], value) if '^' in value else value


def _values(line, position):
    values = []
    while True:
        if position < len(line) and line[position] == '"':
            end = line.find('"', position + 1)
            if end < 0:
                raise Fault('export_malformed_parameter')
            values.append(_caret(line[position + 1:end]))
            position = end + 1
        else:
            end = position
            while end < len(line) and line[end] not in ',;:"':
                end += 1
            values.append(_caret(line[position:end]))
            position = end
        if position < len(line) and line[position] == ',':
            position += 1
            continue
        return values, position


def parse_line(line, *, bare_parameters=False):
    """name *(;param=value) : value. Names and parameter names are case-insensitive.

    vCard 3.0 producers still emit TEL;WORK: for TYPE=WORK; bare_parameters accepts that.
    An optional vCard group prefix (item1.) is dropped.
    """
    match = _NAME.match(line)
    if not match:
        raise Fault('export_malformed_line')
    name, position, params = match[1].upper(), match.end(), {}
    while position < len(line) and line[position] == ';':
        found = _PARAM.match(line, position + 1)
        if not found:
            raise Fault('export_malformed_parameter')
        key, position = found[1].upper(), found.end()
        if position < len(line) and line[position] == '=':
            values, position = _values(line, position + 1)
        elif bare_parameters:
            key, values = 'TYPE', [found[1]]
        else:
            raise Fault('export_malformed_parameter')
        params.setdefault(key, []).extend(values)
        if len(params) > MAX_PARAMS or len(params[key]) > MAX_PARAM_VALUES:
            raise Fault('export_parameter_capacity')
    if position >= len(line) or line[position] != ':':
        raise Fault('export_malformed_line')
    return name, params, line[position + 1:]


def components(lines, *, bare_parameters=False):
    """Nest BEGIN/END blocks. Unbalanced or out-of-component content refuses the file."""
    roots, stack, total = [], [], 0
    for line in lines:
        name, params, value = parse_line(line, bare_parameters=bare_parameters)
        if name == 'BEGIN':
            kind = value.strip().upper()
            if not re.fullmatch(r'[A-Z0-9-]{1,64}', kind):
                raise Fault('export_malformed_component')
            total += 1
            if total > MAX_COMPONENTS:
                raise Fault('export_component_capacity')
            if len(stack) >= MAX_DEPTH:
                raise Fault('export_component_depth')
            item = {'name': kind, 'properties': [], 'children': []}
            (stack[-1]['children'] if stack else roots).append(item)
            stack.append(item)
        elif name == 'END':
            if not stack or stack[-1]['name'] != value.strip().upper():
                raise Fault('export_unbalanced_components')
            stack.pop()
        else:
            if not stack:
                raise Fault('export_content_outside_component')
            if len(stack[-1]['properties']) >= MAX_PROPERTIES:
                raise Fault('export_property_capacity')
            stack[-1]['properties'].append((name, params, value))
    if stack:
        raise Fault('export_unbalanced_components')
    return roots


def unescape(value):
    """RFC 5545 3.3.11 and RFC 6350 3.4 TEXT. Returns (text, clean).

    Unknown escapes are kept literally and reported, never reinterpreted.
    """
    if '\\' not in value:
        return value, True
    out, i, clean = [], 0, True
    while i < len(value):
        if value[i] == '\\':
            following = value[i + 1:i + 2]
            if following in ('n', 'N'):
                out.append('\n')
            elif following in ('\\', ';', ','):
                out.append(following)
            else:
                out.append('\\' + following)
                clean = False
            i += 2
        else:
            out.append(value[i])
            i += 1
    return ''.join(out), clean


def split_unescaped(value, separator):
    """Split on separators that are not escaped. Parts stay escaped for unescape()."""
    parts, current, i = [], [], 0
    while i < len(value):
        if value[i] == '\\':
            current.append(value[i:i + 2])
            i += 2
        elif value[i] == separator:
            parts.append(''.join(current))
            current = []
            i += 1
        else:
            current.append(value[i])
            i += 1
    parts.append(''.join(current))
    return parts


def one_line(value, limit):
    """Collapse all whitespace, including escaped newlines, to single spaces. Bounded."""
    value = ' '.join(_SEPARATOR.sub(' ', value).split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def _wrap(line, width):
    # Deterministic: break at the last space before the width, else hard. Keeps
    # long paragraphs within what an excerpt or a reviewed quotation can cite.
    pieces = []
    while len(line) > width:
        cut = line.rfind(' ', 0, width + 1)
        cut = cut if cut > 0 else width
        pieces.append(line[:cut].rstrip())
        line = line[cut:].lstrip()
    pieces.append(line)
    return pieces


def text_block(value, limit_characters, limit_lines, width=200):
    """Multi-line text as lines. Bounded, with an explicit note of what was left out."""
    lines = []
    for line in _SEPARATOR.sub('\n', value).split('\n'):
        lines.extend(_wrap(line.rstrip(), width))
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    kept, used = [], 0
    for index, line in enumerate(lines):
        room = limit_characters - used
        if len(kept) >= limit_lines or len(line) > room:
            if len(kept) < limit_lines and room > 0:
                kept.append(line[:room])
                line = line[room:]
            left = len(line) + sum(len(rest) for rest in lines[index + 1:])
            kept.append(f'[Truncated on import: {left} more character(s) not imported.]')
            break
        kept.append(line)
        used += len(line)
    return kept
