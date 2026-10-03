"""Opt-in synthetic file contract. No provider, mount, listener or background job.

This deliberately small model wraps ALFRED's existing bounded cache and policy
callback. The catalogue and 'remote' bytes are in memory. It cannot read a user
path, import an account or synchronise SQLite. It is not runtime storage.
"""
from dataclasses import dataclass
import hashlib
from alfred.jobs import BoundedCache
from alfred.local import Fault


@dataclass(frozen=True)
class Revision:
    number: int
    sha256: str
    size: int
    removed: bool = False


class SyntheticFileTier:
    def __init__(self, cache: BoundedCache, authority, *, synthetic=False):
        if synthetic is not True:
            raise Fault('synthetic_opt_in_required')
        self.cache, self.authority = cache, authority
        self.catalogue, self.objects, self.lineage = {}, {}, []
        self.read_requests = 0

    def _bytes(self, data):
        if type(data) is not bytes or not data.startswith(b'synthetic:') or len(data) > 4096:
            raise Fault('bounded_synthetic_bytes_required')

    def publish(self, file_id, data, *, expected_revision=0):
        self._bytes(data); before = self.authority('write')
        current = self.catalogue.get(file_id)
        if (current.number if current else 0) != expected_revision:
            raise Fault('file_revision_conflict', 409)
        if current and current.removed:
            raise Fault('file_tombstoned', 409)
        digest = hashlib.sha256(data).hexdigest()
        if self.authority('write') != before:
            raise Fault('file_authority_changed', 409)
        revision = Revision(expected_revision + 1, digest, len(data))
        self.objects[digest] = data; self.catalogue[file_id] = revision
        self.lineage.append((file_id, revision))
        return revision

    def read(self, file_id, *, pin=False, offline=False, after_fetch=None):
        # A local cached copy and an offline pin confer no permission.
        before = self.authority('read'); current = self.catalogue.get(file_id)
        if not current or current.removed:
            raise Fault('file_unavailable', 404)
        data = self.cache.get(current.sha256)
        if data is None:
            if offline:
                raise Fault('offline_copy_missing', 409)
            self.read_requests += 1; data = self.objects[current.sha256]
            if after_fetch:
                after_fetch()  # deterministic revocation/revision-race injection
            if self.catalogue[file_id] != current:
                raise Fault('file_revision_changed', 409)
            if self.authority('read') != before:
                raise Fault('file_authority_changed', 409)
            self.cache.put(data, pin=pin)
        if self.authority('read') != before or self.catalogue[file_id] != current:
            raise Fault('file_authority_changed', 409)
        if pin:
            self.cache.pin(current.sha256)
        return current, data

    def delete(self, file_id, *, expected_revision):
        before = self.authority('write'); current = self.catalogue.get(file_id)
        if not current or current.number != expected_revision:
            raise Fault('file_revision_conflict', 409)
        if self.authority('write') != before:
            raise Fault('file_authority_changed', 409)
        tombstone = Revision(current.number + 1, current.sha256, 0, True)
        self.catalogue[file_id] = tombstone; self.lineage.append((file_id, tombstone))
        digests = {rev.sha256 for identity, rev in self.lineage if identity == file_id}
        for digest in digests:
            self.cache.discard(digest)
            # Keep objects referenced by other live files; their reads still require authority.
            if not any(r.sha256 == digest and not r.removed for r in self.catalogue.values()):
                self.objects.pop(digest, None)
        return {'tombstone_revision': tombstone.number, 'cache_revisions_removed': len(digests),
                'lineage': 'identifiers, revisions and digests retained; copied files not recalled'}
