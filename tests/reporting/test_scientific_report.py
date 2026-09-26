import pytest

from moldock.domain import FailureKind, TaskStatus
from moldock.reporting import (
    ClusterObservation,
    InteractionObservation,
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
    interactions = (
        InteractionObservation(
            interaction_id="hb_1",
            pose_id="pose_1",
            kind="hydrogen_bond",
            receptor_atom_serial=100,
            receptor_atom_name="NZ",
            receptor_residue_name="LYS",
            receptor_chain="A",
            receptor_residue_number="271",
            ligand_atom_serial=10,
            ligand_atom_name="O1",
            distance_angstrom=2.8,
            method="pdbqt_geometric_interactions",
            method_version="1",
        ),
        InteractionObservation(
            interaction_id="hydro_1",
            pose_id="pose_1",
            kind="hydrophobic_contact",
            receptor_atom_serial=101,
            receptor_atom_name="CD1",
            receptor_residue_name="LEU",
            receptor_chain="A",
            receptor_residue_number="248",
            ligand_atom_serial=11,
            ligand_atom_name="C1",
            distance_angstrom=3.6,
            method="pdbqt_geometric_interactions",
            method_version="1",
        ),
        InteractionObservation(
            interaction_id="hb_2",
            pose_id="pose_2",
            kind="hydrogen_bond",
            receptor_atom_serial=100,
            receptor_atom_name="NZ",
            receptor_residue_name="LYS",
            receptor_chain="A",
            receptor_residue_number="271",
            ligand_atom_serial=10,
            ligand_atom_name="O1",
            distance_angstrom=3.0,
            method="pdbqt_geometric_interactions",
            method_version="1",
        ),
        InteractionObservation(
            interaction_id="hydro_2",
            pose_id="pose_2",
            kind="hydrophobic_contact",
            receptor_atom_serial=101,
            receptor_atom_name="CD1",
            receptor_residue_name="LEU",
            receptor_chain="A",
            receptor_residue_number="248",
            ligand_atom_serial=11,
            ligand_atom_name="C1",
            distance_angstrom=3.9,
            method="pdbqt_geometric_interactions",
            method_version="1",
        ),
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
        interactions=interactions,
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
    assert report.poses[0].hydrogen_bond_count == 1
    assert report.poses[0].hydrophobic_contact_count == 1
    assert report.poses[0].hydrogen_bond_residues == ("A:LYS271",)
    assert report.poses[0].hydrophobic_residues == ("A:LEU248",)
    assert any(
        "Rank 1 has" in item and "hydrogen bond" in item
        for item in report.narrative.interpretation
    )
    assert len(report.evidence) == 5
    top_evidence = report.evidence[0]
    assert top_evidence.rank == 1
    assert top_evidence.delta_to_rank1 == 0.0
    assert top_evidence.cluster_size == 2
    assert top_evidence.rmsd_to_rank1 == 0.0
    assert top_evidence.ligand_efficiency == pytest.approx(13.286 / 37)
    assert top_evidence.cluster_hydrogen_bond_support[0].residue_label == (
        "A:LYS271"
    )
    assert top_evidence.cluster_hydrogen_bond_support[0].pose_count == 2
    assert top_evidence.cluster_hydrogen_bond_support[0].cluster_size == 2
    assert top_evidence.cluster_hydrogen_bond_support[0].fraction == 1.0
    assert top_evidence.cluster_hydrophobic_support[0].residue_label == (
        "A:LEU248"
    )
    assert top_evidence.cluster_hydrophobic_support[0].pose_count == 2
    assert report.evidence[1].delta_to_rank1 == pytest.approx(1.957)
    assert any(
        "A:LYS271 (2/2 poses)" in item
        for item in report.narrative.interpretation
    )
    assert any(
        "A:LEU248 (2/2 poses)" in item
        for item in report.narrative.interpretation
    )
    assert "recurring residue-level interactions" in report.narrative.conclusion
    assert any(
        "not dynamic occupancy" in item
        for item in report.narrative.limitations
    )


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



def test_pose_evidence_does_not_create_composite_ranking():
    report = ScientificReportBuilder().build(_successful_report())

    assert not hasattr(report.evidence[0], "score")
    assert not hasattr(report.evidence[0], "evidence_score")
    assert [item.rank for item in report.evidence] == [1, 2, 3, 4, 5]


def test_pose_evidence_cluster_support_is_scoped_to_pose_family():
    source = _successful_report()
    first_task = source.tasks[0]
    second_score, second_ranking = _score("other_pose", -7.0, 1)
    second_task = TaskPipelineReport(
        task_id="task_2",
        ligand_id="OTHER",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_2",
        failure_kind=None,
        error=None,
        artifact_ids=("artifact_2",),
        pose_ids=("other_pose",),
        scores=(second_score,),
        rankings=(second_ranking,),
        metrics=(),
        clusters=(
            ClusterObservation(
                assignment_id="other_assignment",
                pose_id="other_pose",
                cluster_id="c1",
                method="rank_ordered_leader_rmsd",
                method_version="1",
            ),
        ),
        interactions=(),
    )
    combined = PipelineReport(
        run_id=source.run_id,
        experiment_id=source.experiment_id,
        protocol_id=source.protocol_id,
        manifest_id=source.manifest_id,
        prepared_receptor_id=source.prepared_receptor_id,
        prepared_ligand_ids=source.prepared_ligand_ids + ("other",),
        tasks=(first_task, second_task),
        receptor_id=source.receptor_id,
    )

    report = ScientificReportBuilder().build(combined)

    sti_rank1 = next(
        item
        for item in report.evidence
        if item.ligand_id == "STI" and item.rank == 1
    )
    other_rank1 = next(
        item
        for item in report.evidence
        if item.ligand_id == "OTHER" and item.rank == 1
    )
    assert sti_rank1.cluster_size == 2
    assert other_rank1.cluster_size == 1
    assert other_rank1.cluster_hydrogen_bond_support == ()



def test_pose_evidence_uses_only_final_successful_attempt_when_provenance_exists():
    stale_score, stale_ranking = _score("stale_pose", -12.0, 1)
    final_score, final_ranking = _score("final_pose", -10.0, 1)
    stale_score = ScoreObservation(
        score_id=stale_score.score_id,
        pose_id=stale_score.pose_id,
        kind=stale_score.kind,
        value=stale_score.value,
        unit=stale_score.unit,
        method=stale_score.method,
        method_version=stale_score.method_version,
        attempt_id="attempt_1",
    )
    final_score = ScoreObservation(
        score_id=final_score.score_id,
        pose_id=final_score.pose_id,
        kind=final_score.kind,
        value=final_score.value,
        unit=final_score.unit,
        method=final_score.method,
        method_version=final_score.method_version,
        attempt_id="attempt_2",
    )
    task = TaskPipelineReport(
        task_id="task_retry",
        ligand_id="LIG",
        status=TaskStatus.SUCCEEDED,
        attempt_count=2,
        final_attempt_id="attempt_2",
        failure_kind=None,
        error=None,
        artifact_ids=("artifact_stale", "artifact_final"),
        pose_ids=("stale_pose", "final_pose"),
        scores=(stale_score, final_score),
        rankings=(stale_ranking, final_ranking),
    )
    source = PipelineReport(
        run_id="run_retry",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        receptor_id="rec_1",
    )

    report = ScientificReportBuilder().build(source)

    assert [pose.pose_id for pose in report.poses] == ["final_pose"]
    assert report.poses[0].attempt_id == "attempt_2"
    assert len(report.evidence) == 1
    assert report.evidence[0].pose_id == "final_pose"
    assert report.evidence[0].delta_to_rank1 == 0.0


def test_pose_evidence_separates_scoring_method_versions():
    scores = (
        ScoreObservation(
            score_id="score_v1",
            pose_id="pose_v1",
            kind="custom_score",
            value=1.0,
            unit="arb",
            method="custom",
            method_version="1",
            attempt_id="attempt_1",
        ),
        ScoreObservation(
            score_id="score_v2",
            pose_id="pose_v2",
            kind="custom_score",
            value=100.0,
            unit="arb",
            method="custom",
            method_version="2",
            attempt_id="attempt_1",
        ),
    )
    rankings = (
        RankingObservation(
            ranking_id="rank_v1",
            pose_id="pose_v1",
            rank=1,
            method="custom_score",
        ),
        RankingObservation(
            ranking_id="rank_v2",
            pose_id="pose_v2",
            rank=1,
            method="custom_score",
        ),
    )
    task = TaskPipelineReport(
        task_id="task_versions",
        ligand_id="LIG",
        status=TaskStatus.SUCCEEDED,
        attempt_count=1,
        final_attempt_id="attempt_1",
        failure_kind=None,
        error=None,
        artifact_ids=(),
        pose_ids=("pose_v1", "pose_v2"),
        scores=scores,
        rankings=rankings,
    )
    source = PipelineReport(
        run_id="run_versions",
        experiment_id="exp_1",
        protocol_id="protocol_1",
        manifest_id="manifest_1",
        prepared_receptor_id="prec_1",
        prepared_ligand_ids=("plig_1",),
        tasks=(task,),
        receptor_id="rec_1",
    )

    report = ScientificReportBuilder().build(source)

    assert len(report.evidence) == 2
    assert {item.method_version for item in report.evidence} == {"1", "2"}
    assert all(item.delta_to_rank1 == 0.0 for item in report.evidence)
    assert all(item.method == "custom" for item in report.evidence)
    assert all(item.score_kind == "custom_score" for item in report.evidence)
    assert any(
        "cross-version" in item
        for item in report.narrative.interpretation
    )
