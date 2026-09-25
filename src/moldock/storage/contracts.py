from __future__ import annotations

from typing import Protocol, runtime_checkable

from moldock.domain import StoredBlob


@runtime_checkable
class ArtifactStore(Protocol):
    def put(self, content: bytes) -> StoredBlob: ...

    def get(self, blob_id: str) -> bytes: ...
