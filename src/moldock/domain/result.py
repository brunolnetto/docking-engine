from __future__ import annotations

from dataclasses import dataclass

from .common import DomainValidationError, content_id


@dataclass(frozen=True, slots=True)
class DockingPose:
    task_id: str
    attempt_id: str
    rank: int
    score: float
    pose_artifact_uri: str

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise DomainValidationError("task_id must not be blank")
        if not self.attempt_id.strip():
            raise DomainValidationError("attempt_id must not be blank")
        if self.rank < 1:
            raise DomainValidationError("rank must be >= 1")
        if not self.pose_artifact_uri.strip():
            raise DomainValidationError("pose_artifact_uri must not be blank")

    @property
    def pose_id(self) -> str:
        return content_id(
            "pose",
            {
                "task_id": self.task_id,
                "attempt_id": self.attempt_id,
                "rank": self.rank,
                "score": self.score,
                "pose_artifact_uri": self.pose_artifact_uri,
            },
        )
