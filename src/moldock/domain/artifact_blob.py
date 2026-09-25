from __future__ import annotations

from dataclasses import dataclass

from .common import DomainValidationError


@dataclass(frozen=True, slots=True)
class StoredBlob:
    blob_id: str
    uri: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        for field in ("blob_id", "uri", "sha256"):
            if not getattr(self, field).strip():
                raise DomainValidationError(f"{field} must not be blank")
        if self.size_bytes < 0:
            raise DomainValidationError("size_bytes must be >= 0")
