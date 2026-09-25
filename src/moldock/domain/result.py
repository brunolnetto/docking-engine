from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Mapping

from .common import DomainValidationError, content_id, deep_freeze


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class ScoreKind(str, Enum):
    VINA_AFFINITY = "vina_affinity"


@dataclass(frozen=True, slots=True)
class Pose:
    task_id: str
    attempt_id: str
    source_artifact_id: str
    model_index: int
    geometry_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("task_id", "attempt_id", "source_artifact_id"):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(f"{field_name} must not be blank")
        if self.model_index < 1:
            raise DomainValidationError("model_index must be >= 1")
        if not _SHA256.fullmatch(self.geometry_sha256):
            raise DomainValidationError(
                "geometry_sha256 must contain exactly 64 hexadecimal characters"
            )
        object.__setattr__(self, "geometry_sha256", self.geometry_sha256.lower())

    @property
    def pose_id(self) -> str:
        return content_id(
            "pose",
            {
                "task_id": self.task_id,
                "attempt_id": self.attempt_id,
                "source_artifact_id": self.source_artifact_id,
                "model_index": self.model_index,
                "geometry_sha256": self.geometry_sha256,
            },
        )


@dataclass(frozen=True, slots=True)
class PoseScore:
    pose_id: str
    kind: ScoreKind
    value: float
    unit: str | None
    method: str
    method_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pose_id.strip():
            raise DomainValidationError("pose_id must not be blank")
        if not math.isfinite(self.value):
            raise DomainValidationError("score value must be finite")
        if self.unit is not None and not self.unit.strip():
            raise DomainValidationError("unit must not be blank when provided")
        if not self.method.strip():
            raise DomainValidationError("method must not be blank")
        if not self.method_version.strip():
            raise DomainValidationError("method_version must not be blank")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def score_id(self) -> str:
        return content_id(
            "score",
            {
                "pose_id": self.pose_id,
                "kind": self.kind,
                "value": self.value,
                "unit": self.unit,
                "method": self.method,
                "method_version": self.method_version,
                "metadata": self.metadata,
            },
        )


@dataclass(frozen=True, slots=True)
class PoseRanking:
    pose_id: str
    rank: int
    method: str

    def __post_init__(self) -> None:
        if not self.pose_id.strip():
            raise DomainValidationError("pose_id must not be blank")
        if self.rank < 1:
            raise DomainValidationError("rank must be >= 1")
        if not self.method.strip():
            raise DomainValidationError("method must not be blank")

    @property
    def ranking_id(self) -> str:
        return content_id(
            "ranking",
            {
                "pose_id": self.pose_id,
                "rank": self.rank,
                "method": self.method,
            },
        )
