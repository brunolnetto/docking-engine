from __future__ import annotations

from dataclasses import dataclass

from moldock.domain import FailureKind, TaskStatus
from moldock.toolchain import ToolchainSnapshot


@dataclass(frozen=True, slots=True)
class ScoreObservation:
    score_id: str
    pose_id: str
    kind: str
    value: float
    unit: str | None
    method: str
    method_version: str


@dataclass(frozen=True, slots=True)
class RankingObservation:
    ranking_id: str
    pose_id: str
    rank: int
    method: str


@dataclass(frozen=True, slots=True)
class MetricObservation:
    metric_id: str
    pose_id: str
    kind: str
    value: float
    unit: str | None
    method: str
    method_version: str


@dataclass(frozen=True, slots=True)
class ClusterObservation:
    assignment_id: str
    pose_id: str
    cluster_id: str
    method: str
    method_version: str


@dataclass(frozen=True, slots=True)
class TaskPipelineReport:
    task_id: str
    ligand_id: str
    status: TaskStatus
    attempt_count: int
    final_attempt_id: str | None
    failure_kind: FailureKind | None
    error: str | None
    artifact_ids: tuple[str, ...]
    pose_ids: tuple[str, ...]
    scores: tuple[ScoreObservation, ...]
    rankings: tuple[RankingObservation, ...]
    metrics: tuple[MetricObservation, ...] = ()
    clusters: tuple[ClusterObservation, ...] = ()

    @property
    def artifact_count(self) -> int:
        return len(self.artifact_ids)

    @property
    def pose_count(self) -> int:
        return len(self.pose_ids)

    @property
    def score_count(self) -> int:
        return len(self.scores)


@dataclass(frozen=True, slots=True)
class PipelineReport:
    run_id: str
    experiment_id: str
    protocol_id: str
    manifest_id: str
    prepared_receptor_id: str
    prepared_ligand_ids: tuple[str, ...]
    tasks: tuple[TaskPipelineReport, ...]
    run_manifest_id: str | None = None
    search_space_id: str | None = None
    receptor_id: str | None = None
    receptor_source_sha256: str | None = None
    ligand_sources: tuple[tuple[str, str], ...] = ()
    toolchain_snapshot: ToolchainSnapshot | None = None

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def succeeded_count(self) -> int:
        return sum(
            task.status is TaskStatus.SUCCEEDED
            for task in self.tasks
        )

    @property
    def failed_count(self) -> int:
        return sum(
            task.status is TaskStatus.FAILED
            for task in self.tasks
        )

    @property
    def pending_count(self) -> int:
        return sum(
            task.status is TaskStatus.PENDING
            for task in self.tasks
        )

    @property
    def running_count(self) -> int:
        return sum(
            task.status is TaskStatus.RUNNING
            for task in self.tasks
        )

    @property
    def attempt_count(self) -> int:
        return sum(task.attempt_count for task in self.tasks)

    @property
    def artifact_count(self) -> int:
        return sum(task.artifact_count for task in self.tasks)

    @property
    def pose_count(self) -> int:
        return sum(task.pose_count for task in self.tasks)

    @property
    def score_count(self) -> int:
        return sum(task.score_count for task in self.tasks)
