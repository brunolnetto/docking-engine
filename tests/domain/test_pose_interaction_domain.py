import pytest

from moldock.domain import (
    DomainValidationError,
    PoseInteraction,
    PoseInteractionKind,
)


def make_interaction(**overrides):
    values = {
        "pose_id": "pose_1",
        "kind": PoseInteractionKind.CONTACT,
        "receptor_chain_id": "A",
        "receptor_residue_name": "THR",
        "receptor_residue_number": "315",
        "receptor_atom_name": "OG1",
        "ligand_atom_name": "N1",
        "distance_angstrom": 3.1,
        "method": "pdbqt_geometric_interactions",
        "method_version": "1",
        "metadata": {"rule": "distance"},
    }
    values.update(overrides)
    return PoseInteraction(**values)


def test_pose_interaction_has_deterministic_identity_and_residue_label():
    first = make_interaction()
    second = make_interaction()

    assert first == second
    assert first.interaction_id == second.interaction_id
    assert first.receptor_residue_id == "A:THR315"
    assert first.metadata["rule"] == "distance"


@pytest.mark.parametrize(
    "field",
    [
        "pose_id",
        "receptor_chain_id",
        "receptor_residue_name",
        "receptor_residue_number",
        "receptor_atom_name",
        "ligand_atom_name",
        "method",
        "method_version",
    ],
)
def test_pose_interaction_rejects_blank_identifiers(field):
    with pytest.raises(DomainValidationError, match=field):
        make_interaction(**{field: " "})


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_pose_interaction_rejects_invalid_distance(value):
    with pytest.raises(DomainValidationError, match="distance_angstrom"):
        make_interaction(distance_angstrom=value)


def test_pose_interaction_rejects_non_enum_kind():
    with pytest.raises(DomainValidationError, match="PoseInteractionKind"):
        make_interaction(kind="contact")
