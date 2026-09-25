from __future__ import annotations

from dataclasses import dataclass
import re

from .common import DomainValidationError


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    artifact_id: str
    uri: str
    sha256: str
    size_bytes: int
    media_type: str
    kind: str
    producer_attempt_id: str

    def __post_init__(self) -> None:
        for field in (
            "artifact_id",
            "uri",
            "sha256",
            "media_type",
            "kind",
            "producer_attempt_id",
        ):
            if not getattr(self, field).strip():
                raise DomainValidationError(f"{field} must not be blank")

        if not _SHA256.fullmatch(self.sha256):
            raise DomainValidationError("sha256 must contain exactly 64 hexadecimal characters")
if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise DomainValidationError("size_bytes must be a non-negative integer")

        object.__setattr__(self, "sha256", self.sha256.lower())
