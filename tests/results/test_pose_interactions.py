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


def ligand(
    acceptor_x: float = 2.2,
    acceptor_y: float = 0.0,
) -> bytes:
    return (
        b"MODEL 1\n"
        + atom(
            1,
            "O1",
            "LIG",
            "L",
            1,
            acceptor_x,
            acceptor_y,
            0.0,
            "OA",
        )
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
        pose_pdbqt=ligand(acceptor_x=1.0, acceptor_y=2.0),
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


def test_ligand_donor_can_hydrogen_bond_to_receptor_acceptor():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)
    receptor_acceptor = atom(
        1, "OD1", "ASP", "A", 25, 2.2, 0.0, 0.0, "OA"
    )
    ligand_donor = (
        b"MODEL 1\n"
        + atom(1, "N1", "LIG", "L", 1, 0.0, 0.0, 0.0, "N")
        + atom(2, "H1", "LIG", "L", 1, 1.0, 0.0, 0.0, "HD")
        + b"ENDMDL\n"
    )

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        receptor_pdbqt=receptor_acceptor,
        pose_pdbqt=ligand_donor,
    )

    hbonds = [
        item
        for item in repo.list_interactions_for_pose(persisted.pose_id)
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    ]
    assert len(hbonds) == 1
    assert hbonds[0].residue_label == "A:ASP25"
    assert hbonds[0].metadata["donor_side"] == "ligand"


def test_interaction_analyzer_rejects_pose_model_mismatch():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)
    wrong_model = ligand().replace(b"MODEL 1", b"MODEL 2")

    with pytest.raises(DomainValidationError, match="does not match"):
        PoseInteractionAnalyzer(repository=repo).analyze(
            attempt_id="attempt_1",
            receptor_pdbqt=receptor(),
            pose_pdbqt=wrong_model,
        )


def test_interaction_parser_rejects_empty_single_structure():
    with pytest.raises(DomainValidationError, match="no atoms"):
        PdbqtInteractionParser().parse_single(b"REMARK no coordinates\n")


def test_interaction_parser_rejects_unterminated_model():
    with pytest.raises(DomainValidationError, match="unterminated MODEL"):
        PdbqtInteractionParser().parse_models(
            b"MODEL 1\n"
            + atom(1, "C", "LIG", "L", 1, 0, 0, 0, "C")
        )


def test_interaction_parser_rejects_empty_model():
    with pytest.raises(DomainValidationError, match="has no atoms"):
        PdbqtInteractionParser().parse_models(
            b"MODEL 1\nREMARK empty\nENDMDL\n"
        )


def test_interaction_parser_rejects_invalid_atom_record():
    malformed = b"ATOM      X  BAD\n"

    with pytest.raises(DomainValidationError, match="invalid PDBQT atom"):
        PdbqtInteractionParser().parse_single(malformed)


def test_interaction_analyzer_rejects_invalid_angle_cutoff():
    with pytest.raises(DomainValidationError, match="angle cutoff"):
        PoseInteractionAnalyzer(
            repository=InMemoryScientificResultRepository(),
            hydrogen_bond_angle_degrees=181,
        )


from moldock.results.interactions import (
    PdbqtAtom,
    _angle_degrees,
)



def test_interaction_parser_rejects_nested_model_start():
    content = (
        b"MODEL 1\n"
        + atom(1, "C1", "LIG", "L", 1, 0.0, 0.0, 0.0, "C")
        + b"MODEL 2\n"
    )

    with pytest.raises(DomainValidationError, match="unterminated MODEL 1"):
        PdbqtInteractionParser().parse_models(content)


def test_interaction_parser_ignores_stray_endmdl_before_valid_model():
    content = (
        b"ENDMDL\n"
        b"MODEL 1\n"
        + atom(1, "C1", "LIG", "L", 1, 0.0, 0.0, 0.0, "C")
        + b"ENDMDL\n"
    )

    models = PdbqtInteractionParser().parse_models(content)

    assert tuple(models) == (1,)


def test_interaction_angle_rejects_coincident_atom_geometry():
    first = PdbqtAtom(
        serial=1,
        name="N",
        residue_name="LYS",
        chain="A",
        residue_number="10",
        x=0.0,
        y=0.0,
        z=0.0,
        atom_type="N",
    )
    vertex = PdbqtAtom(
        serial=2,
        name="H",
        residue_name="LYS",
        chain="A",
        residue_number="10",
        x=0.0,
        y=0.0,
        z=0.0,
        atom_type="HD",
    )
    last = PdbqtAtom(
        serial=3,
        name="O",
        residue_name="LIG",
        chain="L",
        residue_number="1",
        x=1.0,
        y=0.0,
        z=0.0,
        atom_type="OA",
    )

    with pytest.raises(DomainValidationError, match="coincident atoms"):
        _angle_degrees(first, vertex, last)


def test_hydrogen_bond_skips_polar_hydrogen_without_nearby_donor():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)
    receptor_without_donor = atom(
        1, "H", "LYS", "A", 10, 0.0, 0.0, 0.0, "HD"
    )
    acceptor = (
        b"MODEL 1\n"
        + atom(1, "O1", "LIG", "L", 1, 1.5, 0.0, 0.0, "OA")
        + b"ENDMDL\n"
    )

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        receptor_pdbqt=receptor_without_donor,
        pose_pdbqt=acceptor,
    )

    assert not [
        item
        for item in repo.list_interactions_for_pose(persisted.pose_id)
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    ]


def test_hydrogen_bond_skips_acceptor_outside_distance_cutoffs():
    repo = InMemoryScientificResultRepository()
    persisted = pose()
    repo.register_pose(persisted)
    far_acceptor = (
        b"MODEL 1\n"
        + atom(1, "O1", "LIG", "L", 1, 6.0, 0.0, 0.0, "OA")
        + b"ENDMDL\n"
    )

    PoseInteractionAnalyzer(repository=repo).analyze(
        attempt_id="attempt_1",
        receptor_pdbqt=receptor(),
        pose_pdbqt=far_acceptor,
    )

    assert not [
        item
        for item in repo.list_interactions_for_pose(persisted.pose_id)
        if item.kind is PoseInteractionKind.HYDROGEN_BOND
    ]


def test_nearest_heavy_atom_returns_none_when_no_candidate_is_close():
    analyzer = PoseInteractionAnalyzer(
        repository=InMemoryScientificResultRepository(),
    )
    hydrogen = PdbqtAtom(
        serial=1,
        name="H",
        residue_name="LIG",
        chain="L",
        residue_number="1",
        x=0.0,
        y=0.0,
        z=0.0,
        atom_type="HD",
    )
    heavy = PdbqtAtom(
        serial=2,
        name="N",
        residue_name="LIG",
        chain="L",
        residue_number="1",
        x=3.0,
        y=0.0,
        z=0.0,
        atom_type="N",
    )

    assert analyzer._nearest_heavy_atom(hydrogen, (heavy,)) is None
