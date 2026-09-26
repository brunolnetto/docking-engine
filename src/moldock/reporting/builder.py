from __future__ import annotations

from moldock.domain import DomainValidationError, TaskStatus
from moldock.pipeline import PipelineRunResult, RunManifest
from moldock.repositories import (
    ArtifactRepository,
    RunManifestRepository,
    TaskRepository,
)
from moldock.results import ScientificResultRepository

from .model import (
    PipelineReport,
    RankingObservation,
    ScoreObservation,
    TaskPipelineReport,
)


class PipelineReportBuilder:
    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        artifact_repository: ArtifactRepository,
        scientific_result_repository: ScientificResultRepository,
    ) -> None:
        self._tasks = task_repository
        self._artifacts = artifact_repository
        self._science = scientific_result_repository

    def build(self, result: PipelineRunResult) -> PipelineReport:
        return self._build(result, manifest=None)

    def build_from_manifest(
        self,
        manifest: RunManifest,
    ) -> PipelineReport:
        return self._build(
            manifest.to_pipeline_result(),
            manifest=manifest,
        )

    def build_for_run(
        self,
        run_id: str,
        *,
        run_manifest_repository: RunManifestRepository,
    ) -> PipelineReport:
        manifest = run_manifest_repository.get(run_id)
        if manifest is None:
            raise DomainValidationError(
                f"run manifest not found: {run_id}"
            )
        return self.build_from_manifest(manifest)

    def _build(
        self,
        result: PipelineRunResult,
        *,
        manifest: RunManifest | None,
    ) -> PipelineReport:
        task_reports = tuple(
            self._build_task(result, task_id)
            for task_id in result.task_ids
        )
        return PipelineReport(
            run_id=result.run_id,
            experiment_id=result.experiment_id,
            protocol_id=result.protocol_id,
            manifest_id=result.manifest_id,
            prepared_receptor_id=result.prepared_receptor_id,
            prepared_ligand_ids=result.prepared_ligand_ids,
            tasks=task_reports,
            run_manifest_id=(
                manifest.run_manifest_id
                if manifest is not None
                else None
            ),
            search_space_id=(
                manifest.search_space_id
                if manifest is not None
                else None
            ),
            receptor_id=(
                manifest.receptor_id
                if manifest is not None
                else None
            ),
            receptor_source_sha256=(
                manifest.receptor_source_sha256
                if manifest is not None
                else None
            ),
            ligand_sources=(
                manifest.ligand_sources
                if manifest is not None
                else ()
            ),
            toolchain_snapshot=(
                manifest.toolchain_snapshot
                if manifest is not None
                else result.toolchain_snapshot
            ),
        )

    def _build_task(
        self,
        result: PipelineRunResult,
        task_id: str,
    ) -> TaskPipelineReport:
        task = self._tasks.get(task_id)
        if task is None:
            raise DomainValidationError(
                f"report task not found: {task_id}"
            )

        attempts = self._tasks.attempts_for(
            task_id,
            result.run_id,
        )
        final = attempts[-1] if attempts else None
        status = (
            final.status
            if final is not None
            else TaskStatus.PENDING
        )

        artifact_ids: list[str] = []
        pose_ids: list[str] = []
        scores: list[ScoreObservation] = []
        rankings: list[RankingObservation] = []

        for attempt in attempts:
            artifact_ids.extend(
                artifact.artifact_id
                for artifact in self._artifacts.list_for_attempt(
                    attempt.attempt_id
                )
            )
            poses = self._science.list_poses_for_attempt(
                attempt.attempt_id
            )
            for pose in poses:
                pose_ids.append(pose.pose_id)
                for score in self._science.list_scores_for_pose(
                    pose.pose_id
                ):
                    scores.append(
                        ScoreObservation(
                            score_id=score.score_id,
                            pose_id=score.pose_id,
                            kind=score.kind.value,
                            value=score.value,
                            unit=score.unit,
                            method=score.method,
                            method_version=score.method_version,
                        )
                    )
                for ranking in self._science.list_rankings_for_pose(
                    pose.pose_id
                ):
                    rankings.append(
                        RankingObservation(
                            ranking_id=ranking.ranking_id,
                            pose_id=ranking.pose_id,
                            rank=ranking.rank,
                            method=ranking.method,
                        )
                    )

        return TaskPipelineReport(
            task_id=task.task_id,
            ligand_id=task.ligand_id,
            status=status,
            attempt_count=len(attempts),
            final_attempt_id=(
                final.attempt_id if final is not None else None
            ),
            failure_kind=(
                final.failure_kind if final is not None else None
            ),
            error=final.error if final is not None else None,
            artifact_ids=tuple(sorted(set(artifact_ids))),
            pose_ids=tuple(sorted(set(pose_ids))),
            scores=tuple(
                sorted(
                    scores,
                    key=lambda item: (
                        item.pose_id,
                        item.kind,
                        item.method,
                        item.score_id,
                    ),
                )
            ),
            rankings=tuple(
                sorted(
                    rankings,
                    key=lambda item: (
                        item.pose_id,
                        item.method,
                        item.rank,
                        item.ranking_id,
                    ),
                )
            ),
        )
