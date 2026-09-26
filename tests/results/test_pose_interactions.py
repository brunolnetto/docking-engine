import pytest

from moldock.domain import (
    DomainValidationError,
    Pose,
    PoseInteractionKind,
)
from moldock.results import (
    InMemoryScientificResultRepository,
    PdbqtInteractionParser,
    PoseInteractionAnalyzer,
)


def atom(
    serial: int,
    name: str,
    residue: str,
    chain: str,
    residue_number: int,
    x: float,
    y: float,
    z: float,
    atom_type: str,
) -> bytes:
    return (
        f"ATOM  {serial:5d} {name:>4s} {residue:>3s} {chain:1s}"
        f"{residue_number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}"
        f"  1.00  0.00    +0.000 {atom_type}\n"
    ).encode()


def pose() -> Pose:
    return Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )


def receptor() -> bytes:
    return (
        atom(1, "N", "LYS", "A", 10, 0.0, 0.0, 0.0, "N")
        + atom(2, "H", "LYS", "A", 10, 1.0, 0.0, 0.0, "HD")
        + atom(3, "C1", "LEU", "A", 20, 0.0, 3.0, 0.0, "C")
    )


def ligand(acceptor_y: float = 0.0) -> bytes:
    return (
        b"MODEL 1\n"
        + atom(1, "O1", "LIG", "L", 1, 2.2, acceptor_y, 0.0, "OA")
        + atom(2, "C1", "LIG", "L", 1, 3.0, 3.0, 0.0, "C")
        + b"ENDMDL\n"
    )


def test_interaction_analyzer_persists_contacts_hydrophobics_and_hbond():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        receptor_pdbqt=receptor(),
        pose_pdbqt=ligand(),
    )

    interactions = repo.list_interactions_for_pose(persisted.pose_id)
    kinds = [item.kind for item in interactions]

    assert PoseInteractionKind.CONTACT in kinds
    assert PoseInteractionKind.HYDROPHOBIC_CONTACT in kinds
    hbonds = [
        item
        for item in interactions
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    ]
    assert len(hbonds) == 1
    assert hbonds[0].residue_label == "A:LYS10"
    assert hbonds[0].distance_angstrom == pytest.approx(2.2)
    assert hbonds[0].metadata[
        "donor_hydrogen_acceptor_angle_degrees"
    ] == pytest.approx(180.0)


def test_hydrogen_bond_requires_directional_geometry():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        receptor_pdbqt=receptor(),
        pose_pdbqt=ligand(acceptor_y=2.0),
    )

    hbonds = [
        item
        for item in repo.list_interactions_for_pose(persisted.pose_id)
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    ]
    assert hbonds == []


def test_interaction_analysis_is_idempotent():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)
    analyzer = PoseInteractionAnalyzer(repository=repo)

    for _ in range(2):
        analyzer.analyze(
            attempt_id="attempt_1",
            receptor_pdbqt=receptor(),
            pose_pdbqt=ligand(),
        )

    ids = [
        item.interaction_id
        for item in repo.list_interactions_for_pose(persisted.pose_id)
    ]
    assert len(ids) == len(set(ids))


def test_interaction_analyzer_is_noop_without_poses():
    repo = InMemoryScientificResultRepository()

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="missing",
        receptor_pdbqt=receptor(),
        pose_pdbqt=ligand(),
    )


def test_interaction_analyzer_rejects_invalid_cutoff():
    with pytest.raises(DomainValidationError, match="cutoffs"):
        PoseInteractionAnalyzer(
            repository=InMemoryScientificResultRepository(),
            contact_cutoff_angstrom=0,
        )


def test_interaction_parser_rejects_missing_models():
    with pytest.raises(DomainValidationError, match="MODEL"):
        PdbqtInteractionParser().parse_models(
            atom(1, "C", "LIG", "L", 1, 0, 0, 0, "C")
        )
