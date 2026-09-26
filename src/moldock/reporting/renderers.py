from __future__ import annotations

from dataclasses import asdict
import json
from typing import Protocol, runtime_checkable

from .model import PipelineReport


@runtime_checkable
class PipelineReporter(Protocol):
    def render(self, report: PipelineReport) -> str: ...


def _toolchain_payload(report: PipelineReport):
    snapshot = report.toolchain_snapshot
    if snapshot is None:
        return None
    return {
        "snapshot_id": snapshot.snapshot_id,
        "vina": asdict(snapshot.vina),
        "meeko_ligand": asdict(snapshot.meeko_ligand),
        "meeko_receptor": asdict(snapshot.meeko_receptor),
    }


def _provenance_payload(report: PipelineReport) -> dict[str, object]:
    return {
        "run_manifest_id": report.run_manifest_id,
        "search_space_id": report.search_space_id,
        "receptor_id": report.receptor_id,
        "receptor_source_sha256": report.receptor_source_sha256,
        "ligand_sources": [
            {"ligand_id": ligand_id, "source_sha256": source_sha256}
            for ligand_id, source_sha256 in report.ligand_sources
        ],
        "toolchain": _toolchain_payload(report),
    }


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
            "provenance": _provenance_payload(report),
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
                    "metrics": [
                        asdict(metric)
                        for metric in task.metrics
                    ],
                    "clusters": [
                        asdict(cluster)
                        for cluster in task.clusters
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


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


class MarkdownPipelineReporter:
    def render(self, report: PipelineReport) -> str:
        lines = [
            "# Molecular Docking Report",
            "",
            "## Provenance",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Run ID | {_cell(report.run_id)} |",
            f"| Run manifest ID | {_cell(report.run_manifest_id or 'n/a')} |",
            f"| Experiment ID | {_cell(report.experiment_id)} |",
            f"| Protocol ID | {_cell(report.protocol_id)} |",
            f"| Task manifest ID | {_cell(report.manifest_id)} |",
            f"| Search space ID | {_cell(report.search_space_id or 'n/a')} |",
            f"| Receptor ID | {_cell(report.receptor_id or 'n/a')} |",
            (
                "| Receptor source SHA-256 | "
                f"{_cell(report.receptor_source_sha256 or 'n/a')} |"
            ),
        ]

        for ligand_id, source_sha256 in report.ligand_sources:
            lines.append(
                f"| Ligand source ({_cell(ligand_id)}) | "
                f"{_cell(source_sha256)} |"
            )

        snapshot = report.toolchain_snapshot
        if snapshot is not None:
            lines.extend(
                [
                    "",
                    "### Toolchain",
                    "",
                    "| Tool | Version | Executable |",
                    "| --- | --- | --- |",
                    (
                        f"| Vina | {_cell(snapshot.vina.version)} | "
                        f"{_cell(snapshot.vina.resolved_path)} |"
                    ),
                    (
                        f"| Meeko ligand | "
                        f"{_cell(snapshot.meeko_ligand.version)} | "
                        f"{_cell(snapshot.meeko_ligand.resolved_path)} |"
                    ),
                    (
                        f"| Meeko receptor | "
                        f"{_cell(snapshot.meeko_receptor.version)} | "
                        f"{_cell(snapshot.meeko_receptor.resolved_path)} |"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                "## Task Summary",
                "",
                "| Metric | Count |",
                "| --- | ---: |",
                f"| Tasks | {report.task_count} |",
                f"| Succeeded | {report.succeeded_count} |",
                f"| Failed | {report.failed_count} |",
                f"| Pending | {report.pending_count} |",
                f"| Running | {report.running_count} |",
                f"| Attempts | {report.attempt_count} |",
                f"| Artifacts | {report.artifact_count} |",
                f"| Poses | {report.pose_count} |",
                f"| Scores | {report.score_count} |",
                "",
                "## Tasks",
                "",
                "| Task | Ligand | Status | Attempts | Failure |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )

        for task in report.tasks:
            failure = (
                task.failure_kind.value
                if task.failure_kind is not None
                else ""
            )
            if task.error:
                failure = (
                    f"{failure}: {task.error}"
                    if failure
                    else task.error
                )
            lines.append(
                f"| {_cell(task.task_id)} | "
                f"{_cell(task.ligand_id)} | "
                f"{_cell(task.status.value)} | "
                f"{task.attempt_count} | {_cell(failure)} |"
            )

        lines.extend(
            [
                "",
                "## Scores",
                "",
                "| Ligand | Pose | Kind | Value | Unit | Method | Version |",
                "| --- | --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for task in report.tasks:
            for score in task.scores:
                lines.append(
                    f"| {_cell(task.ligand_id)} | "
                    f"{_cell(score.pose_id)} | "
                    f"{_cell(score.kind)} | "
                    f"{score.value} | "
                    f"{_cell(score.unit or '')} | "
                    f"{_cell(score.method)} | "
                    f"{_cell(score.method_version)} |"
                )

        return "\n".join(lines) + "\n"
