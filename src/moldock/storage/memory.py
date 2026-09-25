from __future__ import annotations

import hashlib
from threading import RLock

from moldock.domain import DomainValidationError, StoredBlob


class MemoryArtifactStore:
    def __init__(self) -> None:
        self._content: dict[str, bytes] = {}
        self._lock = RLock()

    @property
    def blob_count(self) -> int:
        with self._lock:
            return len(self._content)

    def put(self, content: bytes) -> StoredBlob:
        if not isinstance(content, bytes):
            raise DomainValidationError("artifact content must be bytes")

        sha256 = hashlib.sha256(content).hexdigest()
        blob_id = f"blob_{sha256}"
        with self._lock:
            self._content.setdefault(blob_id, content)

        return StoredBlob(
            blob_id=blob_id,
            uri=f"memory://blobs/{blob_id}",
            sha256=sha256,
            size_bytes=len(content),
        )

    def get(self, blob_id: str) -> bytes:
        with self._lock:
            try:
                return self._content[blob_id]
            except KeyError as exc:
                raise DomainValidationError(f"unknown blob: {blob_id}") from exc
