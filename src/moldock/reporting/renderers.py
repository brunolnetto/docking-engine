from __future__ import annotations

from dataclasses import asdict
import json
from typing import Protocol, runtime_checkable

from .model import PipelineReport


@runtime_checkable
class PipelineReporter(Protocol):
    def render(self, report: PipelineReport) -> str: ...


class JsonPipelineReporter:
    def render(self, report: PipelineReport) -> str:
        payload = {
            "run_id": report.run_id,
            "experiment_id": report.experiment_id,
            "protocol_id": report.protocol_id,
            "manifest_id": report.manifest_id,
            "prepared_receptor_id": report.prepared_receptor_id,
            "prepared_ligand_ids": list(
                report.prepared_ligand_ids
            ),
            "task_count": report.task_count,
            "succeeded_count": report.succeeded_count,
            "failed_count": report.failed_count,
            "pending_count": report.pending_count,
            "running_count": report.running_count,
            "attempt_count": report.attempt_count,
            "artifact_count": report.artifact_count,
            "pose_count": report.pose_count,
            "score_count": report.score_count,
            "tasks": [
                {
                    "task_id": task.task_id,
                    "ligand_id": task.ligand_id,
                    "status": task.status.value,
                    "attempt_count": task.attempt_count,
                    "final_attempt_id": task.final_attempt_id,
                    "failure_kind": (
                        task.failure_kind.value
                        if task.failure_kind is not None
                        else None
                    ),
                    "error": task.error,
                    "artifact_ids": list(task.artifact_ids),
                    "pose_ids": list(task.pose_ids),
                    "scores": [
                        asdict(score)
                        for score in task.scores
                    ],
                    "rankings": [
                        asdict(ranking)
                        for ranking in task.rankings
                    ],
                }
                for task in report.tasks
            ],
        }
        return json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )


class TextPipelineReporter:
    def render(self, report: PipelineReport) -> str:
        lines = [
            f"run={report.run_id}",
            (
                "tasks="
                f"{report.task_count} "
                f"succeeded={report.succeeded_count} "
                f"failed={report.failed_count} "
                f"pending={report.pending_count} "
                f"running={report.running_count}"
            ),
            (
                "artifacts="
                f"{report.artifact_count} "
                f"poses={report.pose_count} "
                f"scores={report.score_count}"
            ),
        ]

        for task in report.tasks:
            line = (
                f"- task={task.task_id} "
                f"ligand={task.ligand_id} "
                f"status={task.status.value} "
                f"attempts={task.attempt_count}"
            )
            if task.failure_kind is not None:
                line += (
                    f" failure={task.failure_kind.value}"
                )
            if task.error is not None:
                line += f" error={task.error}"
            lines.append(line)

            for score in task.scores:
                unit = f" {score.unit}" if score.unit else ""
                lines.append(
                    "  score "
                    f"{score.kind}={score.value}{unit} "
                    f"method={score.method}@{score.method_version} "
                    f"pose={score.pose_id}"
                )

        return "\n".join(lines)
