import pytest

from moldock.domain import (
    InteractionKind,
    Pose,
)
from moldock.results import (
    InMemoryScientificResultRepository,
    PdbqtInteractionParser,
    PoseInteractionAnalyzer,
)


def atom(
    serial,
    name,
    residue,
    chain,
    residue_number,
    x,
    y,
    z,
    atom_type,
):
    return (
        f"ATOM  {serial:5d} {name:>4s} {residue:>3s} "
        f"{chain:1s}{residue_number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}"
        f"  1.00  0.00     0.000 {atom_type}\n"
    ).encode()


def receptor():
    return (
        atom(1, "N", "ASN", "A", 10, 0, 0, 0, "N")
        + atom(2, "H", "ASN", "A", 10, 1, 0, 0, "HD")
        + atom(3, "C1", "LEU", "A", 20, 0, 3, 0, "C")
        + atom(4, "O", "ASP", "A", 30, 5, 0, 0, "OA")
    )


def ligand_model(index=1):
    return (
        f"MODEL {index}\n".encode()
        + atom(1, "O1", "UNL", "L", 1, 2.6, 0, 0, "OA")
        + atom(2, "C1", "UNL", "L", 1, 2.0, 3, 0, "C")
        + atom(3, "N1", "UNL", "L", 1, 6.8, 0, 0, "N")
        + atom(4, "H1", "UNL", "L", 1, 5.8, 0, 0, "HD")
        + b"ENDMDL\n"
    )


class Resolver:
    def resolve(self, task_id):
        assert task_id == "task_1"
        return receptor()


def register_pose(repo):
    pose = Pose(
        task_id="task_1",
        attempt_id="attempt_1",
        source_artifact_id="artifact_1",
        model_index=1,
        geometry_sha256="a" * 64,
    )
    repo.register_pose(pose)
    return pose


def test_interaction_parser_preserves_residue_and_atom_identity():
    atoms = PdbqtInteractionParser().receptor_atoms(receptor())

    assert atoms[0].residue_id == "ASN:A:10"
    assert atoms[0].atom_type == "N"
    assert atoms[1].is_hydrogen is True


def test_interaction_analyzer_finds_contacts_hydrophobic_and_hbonds():
    repo = InMemoryScientificResultRepository()
    pose = register_pose(repo)
    analyzer = PoseInteractionAnalyzer(
        repository=repo,
        receptor_resolver=Resolver(),
    )

    analyzer.analyze(
        task_id="task_1",
        attempt_id="attempt_1",
        pose_content=ligand_model(),
    )

    interactions = repo.list_interactions_for_pose(pose.pose_id)
    kinds = {item.kind for item in interactions}

    assert InteractionKind.RESIDUE_CONTACT in kinds
    assert InteractionKind.HYDROPHOBIC_CONTACT in kinds
    assert InteractionKind.HYDROGEN_BOND in kinds

    hbonds = [
        item
        for item in interactions
        if item.kind is InteractionKind.HYDROGEN_BOND
    ]
    assert {item.protein_is_donor for item in hbonds} == {True, False}
    assert all(item.angle_degrees >= 100 for item in hbonds)
    assert all(item.distance_angstrom <= 4.1 for item in hbonds)

    contacts = {
        item.receptor_residue
        for item in interactions
        if item.kind is InteractionKind.RESIDUE_CONTACT
    }
    assert {"ASN:A:10", "LEU:A:20", "ASP:A:30"} <= contacts


def test_interaction_analysis_is_idempotent():
    repo = InMemoryScientificResultRepository()
    pose = register_pose(repo)
    analyzer = PoseInteractionAnalyzer(
        repository=repo,
        receptor_resolver=Resolver(),
    )

    for _ in range(2):
        analyzer.analyze(
            task_id="task_1",
            attempt_id="attempt_1",
            pose_content=ligand_model(),
        )

    interactions = repo.list_interactions_for_pose(pose.pose_id)
    assert len(interactions) == len(
        {item.interaction_id for item in interactions}
    )


def test_interaction_analysis_is_noop_without_poses():
    repo = InMemoryScientificResultRepository()
    PoseInteractionAnalyzer(
        repository=repo,
        receptor_resolver=Resolver(),
    ).analyze(
        task_id="task_1",
        attempt_id="missing",
        pose_content=ligand_model(),
    )


def test_interaction_analysis_rejects_model_mismatch():
    repo = InMemoryScientificResultRepository()
    register_pose(repo)

    with pytest.raises(Exception, match="does not match"):
        PoseInteractionAnalyzer(
            repository=repo,
            receptor_resolver=Resolver(),
        ).analyze(
            task_id="task_1",
            attempt_id="attempt_1",
            pose_content=ligand_model(index=2),
        )
