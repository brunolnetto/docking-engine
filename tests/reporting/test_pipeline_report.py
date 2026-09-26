import json

from moldock.domain import (
    DockingTask,
    FailureKind,
    Pose,
    PoseRanking,
    PoseScore,
    ScoreKind,
    TaskAttempt,
    TaskStatus,
)
from moldock.pipeline import PipelineRunResult
from moldock.repositories import (
    InMemoryArtifactRepository,
    InMemoryTaskRepository,
)
from moldock.reporting import (
    JsonPipelineReporter,
    PipelineReportBuilder,
    PipelineReporter,
    TextPipelineReporter,
)
from moldock.results import InMemoryScientificResultRepository


def test_report_preserves_score_method_and_kind_without_cross_method_ranking():
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    science = InMemoryScientificResultRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)

    result = PipelineRunResult(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(task.task_id,),
    )

    report = PipelineReportBuilder(
        task_repository=tasks,
        artifact_repository=artifacts,
        scientific_result_repository=science,
    ).build(result)

    assert report.task_count == 1
    assert report.pending_count == 1
    assert report.score_count == 0
    assert isinstance(TextPipelineReporter(), PipelineReporter)
    assert isinstance(JsonPipelineReporter(), PipelineReporter)

    payload = json.loads(JsonPipelineReporter().render(report))
    assert payload["tasks"][0]["status"] == "PENDING"


def test_text_report_includes_failure_kind_and_error():
    from datetime import datetime, timezone

    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    science = InMemoryScientificResultRepository()
    task = DockingTask(
        experiment_id="exp_1",
        receptor_id="rec_1",
        ligand_id="lig_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_id="plig_1",
        search_space_id="space_1",
    )
    tasks.register(task)
    attempt = tasks.claim_next("exp_1", "run_1", "worker_1", now)
    tasks.fail(
        attempt.attempt_id,
        now,
        "backend failed",
        FailureKind.BACKEND,
    )
    result = PipelineRunResult(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(task.task_id,),
    )

    report = PipelineReportBuilder(
        task_repository=tasks,
        artifact_repository=artifacts,
        scientific_result_repository=science,
    ).build(result)
    text = TextPipelineReporter().render(report)

    assert report.failed_count == 1
    assert "BACKEND" in text
    assert "backend failed" in text
