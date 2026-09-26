import json

import pytest

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    FailureKind,
    Pose,
    PoseRanking,
    PoseScore,
    ScoreKind,
    TaskAttempt,
    TaskStatus,
)
from moldock.pipeline import PipelineRunResult, RunManifest
from moldock.repositories import (
    InMemoryArtifactRepository,
    InMemoryTaskRepository,
)
from moldock.reporting import (
    JsonPipelineReporter,
    MarkdownPipelineReporter,
    PipelineReportBuilder,
    PipelineReporter,
    ReportLabPipelineReporter,
    TextPipelineReporter,
)
from moldock.results import InMemoryScientificResultRepository
from moldock.toolchain import ExecutableInfo, ToolchainSnapshot


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


class ManifestRepository:
    def __init__(self, manifest):
        self.manifest = manifest

    def get(self, run_id):
        if run_id == self.manifest.run_id:
            return self.manifest
        return None


def toolchain_snapshot():
    return ToolchainSnapshot(
        vina=ExecutableInfo(
            name="vina",
            executable="vina",
            resolved_path="/opt/vina",
            version="1.2.7",
        ),
        meeko_ligand=ExecutableInfo(
            name="meeko_ligand",
            executable="mk_prepare_ligand.py",
            resolved_path="/opt/mk_prepare_ligand.py",
            version="0.8.0",
        ),
        meeko_receptor=ExecutableInfo(
            name="meeko_receptor",
            executable="mk_prepare_receptor.py",
            resolved_path="/opt/mk_prepare_receptor.py",
            version="0.8.0",
        ),
    )


def test_report_can_be_rebuilt_from_durable_run_manifest():
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
    manifest = RunManifest(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        task_manifest_id="manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(task.task_id,),
        toolchain_snapshot=toolchain_snapshot(),
    )

    report = PipelineReportBuilder(
        task_repository=tasks,
        artifact_repository=artifacts,
        scientific_result_repository=science,
    ).build_for_run(
        "run_1",
        run_manifest_repository=ManifestRepository(manifest),
    )

    assert report.run_manifest_id == manifest.run_manifest_id
    assert report.search_space_id == "space_1"
    assert report.receptor_source_sha256 == "a" * 64
    assert report.ligand_sources == (("lig_1", "b" * 64),)
    assert report.toolchain_snapshot == toolchain_snapshot()


def test_build_for_run_rejects_unknown_run():
    tasks = InMemoryTaskRepository()
    artifacts = InMemoryArtifactRepository()
    science = InMemoryScientificResultRepository()
    manifest = RunManifest(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        task_manifest_id="manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(),
    )

    with pytest.raises(DomainValidationError, match="run manifest"):
        PipelineReportBuilder(
            task_repository=tasks,
            artifact_repository=artifacts,
            scientific_result_repository=science,
        ).build_for_run(
            "missing",
            run_manifest_repository=ManifestRepository(manifest),
        )


def test_markdown_report_contains_provenance_summary_and_score_table():
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

    manifest = RunManifest(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        task_manifest_id="manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(task.task_id,),
        toolchain_snapshot=toolchain_snapshot(),
    )
    report = PipelineReportBuilder(
        task_repository=tasks,
        artifact_repository=artifacts,
        scientific_result_repository=science,
    ).build_from_manifest(manifest)

    markdown = MarkdownPipelineReporter().render(report)
    payload = json.loads(JsonPipelineReporter().render(report))

    assert "# Molecular Docking Report" in markdown
    assert "## Provenance" in markdown
    assert "Vina" in markdown
    assert "1.2.7" in markdown
    assert "Meeko" in markdown
    assert "0.8.0" in markdown
    assert "## Task Summary" in markdown
    assert "## Scores" in markdown
    assert manifest.run_manifest_id in markdown
    assert payload["provenance"]["run_manifest_id"] == manifest.run_manifest_id
    assert payload["provenance"]["toolchain"]["vina"]["version"] == "1.2.7"


def test_reportlab_pdf_is_deterministic_and_writable(tmp_path):
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
    manifest = RunManifest(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        task_manifest_id="manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        task_ids=(task.task_id,),
        toolchain_snapshot=toolchain_snapshot(),
    )
    report = PipelineReportBuilder(
        task_repository=tasks,
        artifact_repository=artifacts,
        scientific_result_repository=science,
    ).build_from_manifest(manifest)

    reporter = ReportLabPipelineReporter()
    first = reporter.render(report)
    second = reporter.render(report)

    assert first.startswith(b"%PDF-")
    assert first == second
    assert len(first) > 1_000

    output = tmp_path / "report.pdf"
    assert reporter.write(report, output) == output
    assert output.read_bytes() == first
