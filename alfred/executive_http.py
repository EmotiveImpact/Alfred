"""Executive workflow routes, reached only through the guarded desk handler.

By the time this runs the request has passed the loopback Host/Origin checks, the
session cookie check and, for every POST, the CSRF check. A brief is a GET because it
is computed on request and changes nothing.
"""
from __future__ import annotations
import re
from .local import Fault

RECORD_OPERATION = re.compile(r'/desk/executive/records/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/(brief|options|decide|reopen|progress)')


def route(executive, path, mutation, bearer, body):
    match = RECORD_OPERATION.fullmatch(path)
    if not match:
        raise Fault('not_found', 404)
    identity, operation = match[1], match[2]
    if operation == 'brief':
        if mutation:
            raise Fault('not_found', 404)
        return executive.brief(bearer, identity)
    if not mutation:
        raise Fault('not_found', 404)
    handler = {'options': executive.set_options, 'decide': executive.decide,
               'reopen': executive.reopen, 'progress': executive.add_progress}[operation]
    return handler(bearer, identity, body)
