import math

import pytest

from moldock.domain import (
    DomainValidationError,
    InteractionKind,
    PoseInteraction,
)


def make_interaction(**overrides):
    values = {
        "pose_id": "pose_1",
        "kind": InteractionKind.HYDROGEN_BOND,
        "receptor_residue": "ASN:A:10",
        "receptor_atom": "N:1:N",
        "ligand_atom": "O1:2:OA",
        "distance_angstrom": 2.8,
        "angle_degrees": 160.0,
        "protein_is_donor": True,
        "method": "autodock_atom_type_geometry",
        "method_version": "1",
    }
    values.update(overrides)
    return PoseInteraction(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"pose_id": ""}, "pose_id"),
        ({"kind": "hydrogen_bond"}, "kind"),
        ({"receptor_residue": ""}, "receptor_residue"),
        ({"receptor_atom": ""}, "receptor_atom"),
        ({"ligand_atom": ""}, "ligand_atom"),
        ({"method": ""}, "method"),
        ({"method_version": ""}, "method_version"),
        ({"distance_angstrom": -1.0}, "distance_angstrom"),
        ({"distance_angstrom": math.inf}, "distance_angstrom"),
        ({"angle_degrees": -1.0}, "angle_degrees"),
        ({"angle_degrees": 181.0}, "angle_degrees"),
    ],
)
def test_pose_interaction_validation(overrides, message):
    with pytest.raises(DomainValidationError, match=message):
        make_interaction(**overrides)


def test_interaction_identity_changes_with_geometry():
    first = make_interaction(distance_angstrom=2.8)
    second = make_interaction(distance_angstrom=2.9)

    assert first.interaction_id != second.interaction_id
