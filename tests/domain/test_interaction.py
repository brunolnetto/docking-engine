import math

import pytest

import moldock.domain.interaction as interaction_module
from moldock.domain import (
    DomainValidationError,
    PoseInteraction,
    PoseInteractionKind,
)


def make_interaction(**overrides):
    values = {
        "pose_id": "pose_1",
        "kind": PoseInteractionKind.HYDROGEN_BOND,
        "receptor_atom_serial": 10,
        "receptor_atom_name": "NZ",
        "receptor_residue_name": "LYS",
        "receptor_chain": "A",
        "receptor_residue_number": "271",
        "ligand_atom_serial": 2,
        "ligand_atom_name": "O1",
        "distance_angstrom": 2.8,
        "method": "pdbqt_geometric_interactions",
        "method_version": "1",
        "metadata": {"angle": 165.0},
    }
    values.update(overrides)
    return PoseInteraction(**values)


def test_pose_interaction_identity_and_residue_label_are_deterministic():
    first = make_interaction()
    second = make_interaction()

    assert first.interaction_id == second.interaction_id
    assert first.interaction_id.startswith("pose_interaction_")
    assert first.residue_label == "A:LYS271"
    assert make_interaction(receptor_chain="").residue_label == "LYS271"
    assert dict(first.metadata) == {"angle": 165.0}


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("pose_id", "", "pose_id"),
        ("receptor_atom_name", "", "receptor_atom_name"),
        ("receptor_residue_name", "", "receptor_residue_name"),
        ("receptor_residue_number", "", "receptor_residue_number"),
        ("ligand_atom_name", "", "ligand_atom_name"),
        ("method", "", "method"),
        ("method_version", "", "method_version"),
    ],
)
def test_pose_interaction_rejects_blank_identifiers(field, value, match):
    with pytest.raises(DomainValidationError, match=match):
        make_interaction(**{field: value})


def test_pose_interaction_rejects_invalid_kind_and_atom_serials():
    with pytest.raises(DomainValidationError, match="PoseInteractionKind"):
        make_interaction(kind="contact")

    with pytest.raises(DomainValidationError, match="atom serials"):
        make_interaction(receptor_atom_serial=0)

    with pytest.raises(DomainValidationError, match="atom serials"):
        make_interaction(ligand_atom_serial=0)


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_pose_interaction_requires_positive_distance(value):
    with pytest.raises(DomainValidationError, match="must be > 0"):
        make_interaction(distance_angstrom=value)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_pose_interaction_requires_finite_distance(value):
    with pytest.raises(DomainValidationError, match="finite"):
        make_interaction(distance_angstrom=value)


def test_pose_interaction_collision_changes_identity_payload(monkeypatch):
    monkeypatch.setattr(
        interaction_module,
        "content_id",
        lambda prefix, value: f"{prefix}_forced",
    )

    assert make_interaction().interaction_id == "pose_interaction_forced"
