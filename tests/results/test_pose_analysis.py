from types import SimpleNamespace

import pytest

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseMetricKind,
    PoseRanking,
    PoseScore,
    ScoreKind,
)
from moldock.results import (
    InMemoryScientificResultRepository,
    PdbqtPoseGeometryParser,
    PoseScientificAnalyzer,
    direct_rmsd,
)
from moldock.results.analysis import PoseGeometry


def atom(serial: int, x: float, y: float, z: float, atom_type: str = "C") -> bytes:
    return (
        f"ATOM  {serial:5d}  C   UNL     1    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00    +0.000 {atom_type}\n"
    ).encode()


def model(index: int, shift: float) -> bytes:
    return (
        f"MODEL {index}\n".encode()
        + f"REMARK VINA RESULT: {-10.0 + index:.3f} 0.0 0.0\n".encode()
        + atom(1, shift, 0.0, 0.0)
        + atom(2, shift + 1.0, 0.0, 0.0)
        + atom(3, shift + 2.0, 0.0, 0.0, "HD")
        + b"ENDMDL\n"
    )


def persisted_pose(index: int) -> Pose:
    return Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=index,
        geometry_sha256=(hex(index)[2:] * 64)[:64],
    )


def test_direct_rmsd_uses_heavy_atoms_in_shared_receptor_frame():
    first, second = PdbqtPoseGeometryParser().parse(
        model(1, 0.0) + model(2, 1.0)
    )

    assert first.heavy_atom_count == 2
    assert direct_rmsd(first, second) == pytest.approx(1.0)


def test_pose_analyzer_persists_rmsd_clusters_and_ligand_efficiency():
    repo = InMemoryScientificResultRepository()
    poses = [persisted_pose(index) for index in (1, 2, 3)]
    for rank, pose in enumerate(poses, start=1):
        repo.register_pose(pose)
        repo.register_score(
            PoseScore(
                pose_id=pose.pose_id,
                kind=ScoreKind.VINA_AFFINITY,
                value=(-12.0, -11.0, -9.0)[rank - 1],
                unit="kcal/mol",
                method="vina",
                method_version="1.2.7",
            )
        )
        repo.register_ranking(
            PoseRanking(
                pose_id=pose.pose_id,
                rank=rank,
                method="vina_affinity",
            )
        )

    content = model(1, 0.0) + model(2, 1.0) + model(3, 4.0)
    PoseScientificAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        content=content,
    )

    first_metrics = {
        metric.kind: metric
        for metric in repo.list_metrics_for_pose(poses[0].pose_id)
    }
    second_metrics = {
        metric.kind: metric
        for metric in repo.list_metrics_for_pose(poses[1].pose_id)
    }

    assert first_metrics[PoseMetricKind.RMSD_TO_RANK1].value == 0.0
    assert second_metrics[PoseMetricKind.RMSD_TO_RANK1].value == pytest.approx(1.0)
    assert first_metrics[PoseMetricKind.LIGAND_EFFICIENCY].value == pytest.approx(6.0)
    assert first_metrics[PoseMetricKind.LIGAND_EFFICIENCY].metadata["heavy_atom_count"] == 2

    clusters = [
        repo.list_cluster_assignments_for_pose(pose.pose_id)[0].cluster_id
        for pose in poses
    ]
    assert clusters[0] == clusters[1]
    assert clusters[2] != clusters[0]


def test_pose_analysis_is_idempotent():
    repo = InMemoryScientificResultRepository()
    pose = persisted_pose(1)
    repo.register_pose(pose)
    repo.register_score(
        PoseScore(
            pose_id=pose.pose_id,
            kind=ScoreKind.VINA_AFFINITY,
            value=-8.0,
            unit="kcal/mol",
            method="vina",
            method_version="1.2.7",
        )
    )
    repo.register_ranking(
        PoseRanking(
            pose_id=pose.pose_id,
            rank=1,
            method="vina_affinity",
        )
    )
    analyzer = PoseScientificAnalyzer(repository=repo)
    content = model(1, 0.0)

    analyzer.analyze(attempt_id="attempt_1", content=content)
    analyzer.analyze(attempt_id="attempt_1", content=content)

    assert len(repo.list_metrics_for_pose(pose.pose_id)) == 2
    assert len(repo.list_cluster_assignments_for_pose(pose.pose_id)) == 1


def test_geometry_parser_rejects_unterminated_models():
    with pytest.raises(DomainValidationError, match="unterminated MODEL"):
        PdbqtPoseGeometryParser().parse(
            b"MODEL 1\n" + atom(1, 0.0, 0.0, 0.0)
        )


def test_geometry_parser_rejects_empty_models():
    with pytest.raises(DomainValidationError, match="no heavy atoms"):
        PdbqtPoseGeometryParser().parse(
            b"MODEL 1\n"
            + atom(1, 0.0, 0.0, 0.0, "HD")
            + b"ENDMDL\n"
        )


def test_geometry_parser_rejects_inconsistent_atom_order():
    content = (
        b"MODEL 1\n"
        + atom(1, 0.0, 0.0, 0.0, "C")
        + b"ENDMDL\n"
        + b"MODEL 2\n"
        + atom(1, 0.0, 0.0, 0.0, "N")
        + b"ENDMDL\n"
    )

    with pytest.raises(DomainValidationError, match="atom order differs"):
        PdbqtPoseGeometryParser().parse(content)


def test_direct_rmsd_rejects_different_atom_orders():
    first = PdbqtPoseGeometryParser().parse(model(1, 0.0))[0]
    second = type(first)(
        model_index=2,
        atom_labels=("N:N", "C:C"),
        coordinates=first.coordinates,
    )

    with pytest.raises(DomainValidationError, match="different atom order"):
        direct_rmsd(first, second)


def test_pose_analyzer_rejects_invalid_threshold():
    with pytest.raises(DomainValidationError, match="threshold"):
        PoseScientificAnalyzer(
            repository=InMemoryScientificResultRepository(),
            cluster_threshold_angstrom=0,
        )


def test_pose_analyzer_is_noop_without_persisted_poses():
    repo = InMemoryScientificResultRepository()

    PoseScientificAnalyzer(repository=repo).analyze(
        attempt_id="missing",
        content=model(1, 0.0),
    )


def test_pose_analyzer_rejects_geometry_model_mismatch():
    repo = InMemoryScientificResultRepository()
    pose = persisted_pose(1)
    repo.register_pose(pose)
    repo.register_ranking(
        PoseRanking(
            pose_id=pose.pose_id,
            rank=1,
            method="vina_affinity",
        )
    )

    with pytest.raises(DomainValidationError, match="does not match"):
        PoseScientificAnalyzer(repository=repo).analyze(
            attempt_id="attempt_1",
            content=model(2, 0.0),
        )


def test_pose_analyzer_skips_attempt_without_vina_ranking():
    repo = InMemoryScientificResultRepository()
    pose = persisted_pose(1)
    repo.register_pose(pose)

    PoseScientificAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        content=model(1, 0.0),
    )

    assert repo.list_metrics_for_pose(pose.pose_id) == ()
    assert repo.list_cluster_assignments_for_pose(pose.pose_id) == ()



def test_geometry_parser_rejects_missing_model_blocks():
    with pytest.raises(DomainValidationError, match="no MODEL"):
        PdbqtPoseGeometryParser().parse(
            atom(1, 0.0, 0.0, 0.0)
        )


def test_geometry_parser_rejects_invalid_coordinates():
    malformed = (
        b"MODEL 1\n"
        b"ATOM      1  C   UNL     1         bad     0.0     0.0"
        b"  1.00  0.00    +0.000 C\n"
        b"ENDMDL\n"
    )

    with pytest.raises(DomainValidationError, match="invalid PDBQT coordinates"):
        PdbqtPoseGeometryParser().parse(malformed)


def test_geometry_parser_rejects_nested_model_start():
    content = (
        b"MODEL 1\n"
        + atom(1, 0.0, 0.0, 0.0)
        + b"MODEL 2\n"
    )

    with pytest.raises(DomainValidationError, match="unterminated MODEL 1"):
        PdbqtPoseGeometryParser().parse(content)


def test_geometry_parser_ignores_stray_endmdl_and_outside_lines():
    content = (
        b"REMARK outside\n"
        b"ENDMDL\n"
        b"MODEL 1\n"
        + atom(1, 0.0, 0.0, 0.0)
        + b"ENDMDL\n"
    )

    parsed = PdbqtPoseGeometryParser().parse(content)

    assert len(parsed) == 1
    assert parsed[0].model_index == 1


def test_direct_rmsd_rejects_different_coordinate_counts():
    left = PoseGeometry(
        model_index=1,
        atom_labels=("C:C",),
        coordinates=((0.0, 0.0, 0.0),),
    )
    right = PoseGeometry(
        model_index=2,
        atom_labels=("C:C",),
        coordinates=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    )

    with pytest.raises(DomainValidationError, match="different atom counts"):
        direct_rmsd(left, right)


def test_pose_analyzer_ignores_non_vina_score_kind_from_repository():
    class Repository(InMemoryScientificResultRepository):
        def list_scores_for_pose(self, pose_id):
            return (SimpleNamespace(kind="other"),)

    repo = Repository()
    persisted = persisted_pose(1)
    repo.register_pose(persisted)
    repo.register_ranking(
        PoseRanking(
            pose_id=persisted.pose_id,
            rank=1,
            method="vina_affinity",
        )
    )

    PoseScientificAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        content=model(1, 0.0),
    )

    metrics = repo.list_metrics_for_pose(persisted.pose_id)
    assert [metric.kind for metric in metrics] == [
        PoseMetricKind.RMSD_TO_RANK1
    ]
