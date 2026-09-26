from io import BytesIO
import json

import pytest

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    FailureKind,
    Pose,
    PoseInteraction,
    PoseInteractionKind,
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
    ClusterObservation,
    InteractionObservation,
    JsonPipelineReporter,
    MetricObservation,
    MarkdownPipelineReporter,
    PipelineReport,
    PipelineReportBuilder,
    PipelineReporter,
    RankingObservation,
    ReportLabPipelineReporter,
    ScoreObservation,
    TaskPipelineReport,
    TextPipelineReporter,
)
from moldock.reporting.pdf import _score_value
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

    stream = BytesIO()
    assert reporter.write(report, stream) is stream
    assert stream.getvalue() == first


def test_reportlab_pdf_keeps_full_diagnostics_and_score_precision():
    value = -11.264123456789
    task = TaskPipelineReport(
        task_id="task_failed",
        ligand_id="lig_1",
        status=TaskStatus.FAILED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=FailureKind.BACKEND,
        error=("vina stderr diagnostic line\n" * 250),
        artifact_ids=("artifact_1",),
        pose_ids=("pose_1",),
        scores=(
            ScoreObservation(
                score_id="score_1",
                pose_id="pose_1",
                kind="vina_affinity",
                value=value,
                unit="kcal/mol",
                method="vina",
                method_version="1.2.7",
            ),
        ),
        rankings=(
            RankingObservation(
                ranking_id="ranking_1",
                pose_id="pose_1",
                rank=1,
                method="vina_affinity",
            ),
        ),
    )
    report = PipelineReport(
        run_id="run_failed",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        run_manifest_id="run_manifest_1",
        search_space_id="space_1",
        receptor_id="rec_1",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("lig_1", "b" * 64),),
        toolchain_snapshot=toolchain_snapshot(),
    )

    pdf = ReportLabPipelineReporter().render(report)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 5_000
    assert _score_value(value) == repr(value)



def test_reportlab_pdf_renders_recurrent_cluster_evidence():
    scores = (
        ScoreObservation(
            score_id="score_1",
            pose_id="pose_1",
            kind="vina_affinity",
            value=-10.0,
            unit="kcal/mol",
            method="vina",
            method_version="1.2.7",
        ),
        ScoreObservation(
            score_id="score_2",
            pose_id="pose_2",
            kind="vina_affinity",
            value=-9.5,
            unit="kcal/mol",
            method="vina",
            method_version="1.2.7",
        ),
    )
    rankings = (
        RankingObservation(
            ranking_id="rank_1",
            pose_id="pose_1",
            rank=1,
            method="vina_affinity",
        ),
        RankingObservation(
            ranking_id="rank_2",
            pose_id="pose_2",
            rank=2,
            method="vina_affinity",
        ),
    )
    metrics = (
        MetricObservation(
            metric_id="rmsd_1",
            pose_id="pose_1",
            kind="rmsd_to_rank1",
            value=0.0,
            unit="angstrom",
            method="pdbqt_atom_order_direct_rmsd",
            method_version="1",
        ),
        MetricObservation(
            metric_id="rmsd_2",
            pose_id="pose_2",
            kind="rmsd_to_rank1",
            value=1.0,
            unit="angstrom",
            method="pdbqt_atom_order_direct_rmsd",
            method_version="1",
        ),
    )
    clusters = (
        ClusterObservation(
            assignment_id="cluster_assignment_1",
            pose_id="pose_1",
            cluster_id="cluster_1",
            method="rank_ordered_leader_rmsd",
            method_version="1",
        ),
        ClusterObservation(
            assignment_id="cluster_assignment_2",
            pose_id="pose_2",
            cluster_id="cluster_1",
            method="rank_ordered_leader_rmsd",
            method_version="1",
        ),
    )
    interactions = tuple(
        InteractionObservation(
            interaction_id=f"{kind}_{pose_id}",
            pose_id=pose_id,
            kind=kind,
            receptor_atom_serial=10 if kind == "hydrogen_bond" else 20,
            receptor_atom_name="NZ" if kind == "hydrogen_bond" else "CD1",
            receptor_residue_name="LYS" if kind == "hydrogen_bond" else "LEU",
            receptor_chain="A",
            receptor_residue_number="271" if kind == "hydrogen_bond" else "248",
            ligand_atom_serial=1,
            ligand_atom_name="O1" if kind == "hydrogen_bond" else "C1",
            distance_angstrom=2.8 if kind == "hydrogen_bond" else 3.8,
            method="pdbqt_geometric_interactions",
            method_version="1",
        )
        for pose_id in ("pose_1", "pose_2")
        for kind in ("hydrogen_bond", "hydrophobic_contact")
    )
    task = TaskPipelineReport(
        task_id="task_1",
        ligand_id="lig_1",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error=None,
        artifact_ids=(),
        pose_ids=("pose_1", "pose_2"),
        scores=scores,
        rankings=rankings,
        metrics=metrics,
        clusters=clusters,
        interactions=interactions,
    )
    report = PipelineReport(
        run_id="run_evidence",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        receptor_id="rec_1",
    )

    pdf = ReportLabPipelineReporter().render(report)

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2_000



def test_pipeline_report_builder_rejects_missing_task_reference():
    result = PipelineRunResult(
        run_id="run_missing",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=(),
        task_ids=("missing_task",),
    )

    with pytest.raises(DomainValidationError, match="report task not found"):
        PipelineReportBuilder(
            task_repository=InMemoryTaskRepository(),
            artifact_repository=InMemoryArtifactRepository(),
            scientific_result_repository=InMemoryScientificResultRepository(),
        ).build(result)


def test_pipeline_report_builder_rebuilds_interactions():
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
    pose = Pose(
        task_id=task.task_id,
        attempt_id=attempt.attempt_id,
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )
    science.register_pose(pose)
    interaction = PoseInteraction(
        pose_id=pose.pose_id,
        kind=PoseInteractionKind.CONTACT,
        receptor_atom_serial=1,
        receptor_atom_name="CA",
        receptor_residue_name="ALA",
        receptor_chain="A",
        receptor_residue_number="10",
        ligand_atom_serial=2,
        ligand_atom_name="C1",
        distance_angstrom=3.0,
        method="test",
        method_version="1",
    )
    science.register_interaction(interaction)
    tasks.succeed(attempt.attempt_id, now)

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

    assert len(report.tasks[0].interactions) == 1
    assert report.tasks[0].interactions[0].interaction_id == interaction.interaction_id


def test_text_and_markdown_render_optional_score_unit_and_unclassified_error():
    task = TaskPipelineReport(
        task_id="task_1|pipe",
        ligand_id="lig\n1",
        status=TaskStatus.FAILED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error="plain error",
        artifact_ids=(),
        pose_ids=("pose_1",),
        scores=(
            ScoreObservation(
                score_id="score_1",
                pose_id="pose_1",
                kind="custom",
                value=1.25,
                unit=None,
                method="method",
                method_version="1",
            ),
        ),
        rankings=(),
    )
    report = PipelineReport(
        run_id="run",
        experiment_id="exp",
        protocol_id="protocol",
        manifest_id="manifest",
        prepared_receptor_id="prec",
        prepared_ligand_ids=(),
        tasks=(task,),
    )

    text_report = TextPipelineReporter().render(report)
    markdown = MarkdownPipelineReporter().render(report)

    assert "custom=1.25 method=method@1" in text_report
    assert "plain error" in markdown
    assert "task_1\\|pipe" in markdown
    assert "lig 1" in markdown
    assert "| lig 1 | pose_1 | custom | 1.25 |  | method | 1 |" in markdown


def test_reportlab_pdf_requires_reportlab_dependency(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    report = PipelineReport(
        run_id="run",
        experiment_id="exp",
        protocol_id="protocol",
        manifest_id="manifest",
        prepared_receptor_id="prec",
        prepared_ligand_ids=(),
        tasks=(),
    )

    with pytest.raises(RuntimeError, match="PDF reporting requires"):
        ReportLabPipelineReporter().render(report)


def test_reportlab_pdf_handles_multiple_score_families_without_score_chart():
    task = TaskPipelineReport(
        task_id="task_1",
        ligand_id="lig_1",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error=None,
        artifact_ids=(),
        pose_ids=("pose_1", "pose_2"),
        scores=(
            ScoreObservation(
                score_id="score_1",
                pose_id="pose_1",
                kind="vina_affinity",
                value=-8.0,
                unit="kcal/mol",
                method="vina",
                method_version="1.2.7",
                attempt_id="attempt_1",
            ),
            ScoreObservation(
                score_id="score_2",
                pose_id="pose_2",
                kind="vina_affinity",
                value=-7.0,
                unit="kcal/mol",
                method="vina",
                method_version="1.2.8",
                attempt_id="attempt_1",
            ),
        ),
        rankings=(
            RankingObservation(
                ranking_id="rank_1",
                pose_id="pose_1",
                rank=1,
                method="vina_affinity",
            ),
            RankingObservation(
                ranking_id="rank_2",
                pose_id="pose_2",
                rank=1,
                method="vina_affinity",
            ),
        ),
    )
    report = PipelineReport(
        run_id="run",
        experiment_id="exp",
        protocol_id="protocol",
        manifest_id="manifest",
        prepared_receptor_id="prec",
        prepared_ligand_ids=("plig",),
        tasks=(task,),
        receptor_id="rec",
    )

    pdf = ReportLabPipelineReporter().render(report)

    assert pdf.startswith(b"%PDF-")
