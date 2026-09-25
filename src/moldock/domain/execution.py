from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .common import DomainValidationError


@dataclass(frozen=True, slots=True)
class DockingOutputArtifact:
    kind: str
    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise DomainValidationError("kind must not be blank")
        if not self.media_type.strip():
            raise DomainValidationError("media_type must not be blank")
        if not isinstance(self.content, bytes):
            raise DomainValidationError("content must be bytes")


@dataclass(frozen=True, slots=True)
class DockingResult:
    artifacts: tuple[DockingOutputArtifact, ...]
    stdout: str = ""
    stderr: str = ""

    def __init__(
        self,
        artifacts: Iterable[DockingOutputArtifact] = (),
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        object.__setattr__(self, "artifacts", tuple(artifacts))
        object.__setattr__(self, "stdout", stdout)
        object.__setattr__(self, "stderr", stderr)
