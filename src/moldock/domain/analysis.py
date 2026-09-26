from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping

from .common import DomainValidationError, content_id, deep_freeze


class PoseMetricKind(str, Enum):
    RMSD_TO_RANK1 = "rmsd_to_rank1"
    LIGAND_EFFICIENCY = "ligand_efficiency"


@dataclass(frozen=True, slots=True)
class PoseMetric:
    pose_id: str
    kind: PoseMetricKind
    value: float
    unit: str | None
    method: str
    method_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pose_id.strip():
            raise DomainValidationError("pose_id must not be blank")
        if not isinstance(self.kind, PoseMetricKind):
            raise DomainValidationError("kind must be a PoseMetricKind")
        if not math.isfinite(self.value):
            raise DomainValidationError("metric value must be finite")
        if self.unit is not None and not self.unit.strip():
            raise DomainValidationError("unit must not be blank when provided")
        if not self.method.strip():
            raise DomainValidationError("method must not be blank")
        if not self.method_version.strip():
            raise DomainValidationError("method_version must not be blank")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def metric_id(self) -> str:
        return content_id(
            "pose_metric",
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
class PoseClusterAssignment:
    pose_id: str
    cluster_id: str
    method: str
    method_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("pose_id", "cluster_id", "method", "method_version"):
            if not getattr(self, name).strip():
                raise DomainValidationError(f"{name} must not be blank")
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    @property
    def assignment_id(self) -> str:
        return content_id(
            "pose_cluster_assignment",
            {
                "pose_id": self.pose_id,
                "cluster_id": self.cluster_id,
                "method": self.method,
                "method_version": self.method_version,
                "metadata": self.metadata,
            },
        )
