"""Routine routes, reached only through the guarded desk handler.

By the time this runs the request has passed the loopback Host and Origin checks, the
session cookie check and, for every POST, the CSRF check. Reads change nothing. Another
person's nomination and an unknown one both return 404 nomination_not_found.
"""
from __future__ import annotations
import re
from .local import Fault

KIND = r'(commitment-review|morning-brief)'
ROUTINE_OPERATION = re.compile(rf'/desk/routines/{KIND}/(configure|pause|run)')
NOMINATION_OPERATION = re.compile(r'/desk/routines/nominations/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/(accept|dismiss)')


def route(server, path, mutation, bearer, body):
    routines = getattr(server, 'routines', None)
    if routines is None:
        raise Fault('routines_not_configured', 409)
    if not mutation:
        if path == '/desk/routines':
            return routines.view(bearer)
        if path == '/desk/routines/nominations':
            return routines.summary(bearer)
        if path == '/desk/routines/procedures':
            return routines.procedures(bearer)
        raise Fault('not_found', 404)
    match = ROUTINE_OPERATION.fullmatch(path)
    if match:
        handler = {'configure': routines.configure, 'pause': routines.pause, 'run': routines.manual}[match[2]]
        return handler(bearer, match[1], body)
    match = NOMINATION_OPERATION.fullmatch(path)
    if match:
        return (routines.accept if match[2] == 'accept' else routines.dismiss)(bearer, match[1], body)
    raise Fault('not_found', 404)
