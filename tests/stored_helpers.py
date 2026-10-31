"""Reading what a store keeps, in a plain or a sealed workspace (encryption step 2).

Tests that look past the API into the database, or compare a digest ALFRED returns, use
these so the same assertion holds in the ordinary run and in ``tests/sealed_suite.py``.
"""
import hashlib

from alfred import sealing


def digest(store, data, area=sealing.DEFAULT_AREA):
    """The SHA-256 of ``data`` (bytes or text) in the form the store keeps and returns: the
    plain hex digest in a plain workspace, the area's keyed fingerprint in a sealed one."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return store.sealer.fingerprint(area, hashlib.sha256(data).hexdigest())


def rows(store, table, sql, params=()):
    """The rows a query returns from a table in ``sealing.TABLES``, with sealed columns opened.
    Filter on sealed columns in Python, never in the SQL: sealed values differ every time."""
    with store.connection() as db:
        return [sealing.open_row(store.sealer, table, row) for row in db.execute(sql, params)]
