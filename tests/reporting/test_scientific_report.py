import pytest

from moldock.domain import FailureKind, TaskStatus
from moldock.reporting import (
    ClusterObservation,
    MetricObservation,
    PipelineReport,
    RankingObservation,
    ScoreObservation,
    ScientificReportBuilder,
    TaskPipelineReport,
)


def _score(pose_id: str, value: float, rank: int):
    return (
        ScoreObservation(
            score_id=f"score_{rank}",
            pose_id=pose_id,
            kind="vina_affinity",
            value=value,
            unit="kcal/mol",
            method="vina",
            method_version="1.2.7",
        ),
        RankingObservation(
            ranking_id=f"ranking_{rank}",
            pose_id=pose_id,
            rank=rank,
            method="vina_affinity",
        ),
    )


def _successful_report():
    values = (-13.286, -11.329, -11.264, -11.126, -10.718)
    scores = []
    rankings = []
    poses = []
    for rank, value in enumerate(values, start=1):
        pose_id = f"pose_{rank}"
        score, ranking = _score(pose_id, value, rank)
        scores.append(score)
        rankings.append(ranking)
        poses.append(pose_id)
    metrics = []
    clusters = []
    rmsds = (0.0, 1.7, 12.4, 12.2, 2.1)
    cluster_ids = ("c1", "c1", "c2", "c3", "c4")
    for rank, pose_id in enumerate(poses, start=1):
        metrics.extend(
            [
                MetricObservation(
                    metric_id=f"rmsd_{rank}",
                    pose_id=pose_id,
                    kind="rmsd_to_rank1",
                    value=rmsds[rank - 1],
                    unit="angstrom",
                    method="pdbqt_atom_order_direct_rmsd",
                    method_version="1",
                ),
                MetricObservation(
                    metric_id=f"le_{rank}",
                    pose_id=pose_id,
                    kind="ligand_efficiency",
                    value=-values[rank - 1] / 37,
                    unit="kcal/mol/heavy_atom",
                    method="vina_affinity_per_heavy_atom",
                    method_version="1.2.7",
                ),
            ]
        )
        clusters.append(
            ClusterObservation(
                assignment_id=f"assignment_{rank}",
                pose_id=pose_id,
                cluster_id=cluster_ids[rank - 1],
                method="rank_ordered_leader_rmsd",
                method_version="1",
            )
        )
    task = TaskPipelineReport(
        task_id="task_1",
        ligand_id="STI",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error=None,
        artifact_ids=("artifact_1",),
        pose_ids=tuple(poses),
        scores=tuple(scores),
        rankings=tuple(rankings),
        metrics=tuple(metrics),
        clusters=tuple(clusters),
    )
    return PipelineReport(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        run_manifest_id="run_manifest_1",
        search_space_id="space_1",
        receptor_id="1iep",
        receptor_source_sha256="a" * 64,
        ligand_sources=(("STI", "b" * 64),),
    )


def test_scientific_report_builds_experiment_story_from_vina_results():
    report = ScientificReportBuilder().build(_successful_report())

    assert report.completed is True
    assert report.narrative.title == "Molecular Docking Study — STI / 1iep"
    assert "Evaluate docking poses" in report.narrative.objective
    assert "5 scored pose(s)" in report.narrative.outcome
    assert report.score_min == -13.286
    assert report.score_max == -10.718
    assert report.score_spread == pytest.approx(2.568)
    assert report.poses[0].rank == 1
    assert report.poses[0].score_value == -13.286
    assert any("rank 1 was -13.286 kcal/mol" in item for item in report.narrative.interpretation)
    assert any("1.957 kcal/mol" in item for item in report.narrative.interpretation)
    assert any("do not by themselves establish experimental binding affinity" in item for item in report.narrative.limitations)
    assert any("RMSD" in item for item in report.narrative.next_steps)
    assert "prioritizing rank 1 for structural follow-up" in report.narrative.conclusion
    assert report.poses[1].rmsd_to_rank1 == 1.7
    assert report.poses[0].ligand_efficiency == pytest.approx(13.286 / 37)
    assert report.poses[0].cluster_id == "c1"
    assert any("4 RMSD cluster" in item for item in report.narrative.interpretation)
    assert "shares its 2.0 Å RMSD cluster" in report.narrative.conclusion
    assert "substantial structural diversity" in report.narrative.conclusion


def test_scientific_report_limits_interpretation_for_failed_experiment():
    task = TaskPipelineReport(
        task_id="task_1",
        ligand_id="lig_1",
        status=TaskStatus.FAILED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=FailureKind.BACKEND,
        error="vina failed",
        artifact_ids=(),
        pose_ids=(),
        scores=(),
        rankings=(),
    )
    source = PipelineReport(
        run_id="run_failed",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
    )

    report = ScientificReportBuilder().build(source)

    assert report.completed is False
    assert "did not complete successfully" in report.narrative.outcome
    assert report.score_min is None
    assert report.score_max is None
    assert report.score_spread is None
    assert any("descriptive reporting only" in item for item in report.narrative.interpretation)
    assert report.narrative.next_steps[0].startswith("Resolve failed docking tasks")
    assert report.narrative.conclusion.startswith("No scientific docking conclusion")


def test_scientific_report_does_not_infer_cross_method_order():
    task = TaskPipelineReport(
        task_id="task_1",
        ligand_id="lig_1",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error=None,
        artifact_ids=(),
        pose_ids=("pose_1",),
        scores=(
            ScoreObservation(
                score_id="score_1",
                pose_id="pose_1",
                kind="custom_score",
                value=0.123456789,
                unit=None,
                method="custom",
                method_version="1",
            ),
        ),
        rankings=(
            RankingObservation(
                ranking_id="ranking_1",
                pose_id="pose_1",
                rank=1,
                method="custom_score",
            ),
        ),
    )
    source = PipelineReport(
        run_id="run_1",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        receptor_id="rec_1",
    )

    report = ScientificReportBuilder().build(source)

    assert report.completed is True
    assert report.poses[0].score_value == 0.123456789
    assert any("no cross-method ordering was inferred" in item for item in report.narrative.interpretation)
    assert "no cross-method conclusion" in report.narrative.conclusion
