from dataclasses import FrozenInstanceError, dataclass

import pytest

from moldock.domain import DockingProtocol, DomainValidationError


def make_protocol(**overrides):
    values = dict(
        backend="vina",
        backend_version="1.2.7",
        receptor_preparation_id="rprep_1",
        ligand_preparation_id="lprep_1",
        parameters={
            "seed": 42,
            "exhaustiveness": 8,
            "num_modes": 9,
        },
    )
    values.update(overrides)
    return DockingProtocol(**values)


def test_equivalent_protocols_have_same_identity():
    a = make_protocol(parameters={"seed": 42, "exhaustiveness": 8})
    b = make_protocol(parameters={"exhaustiveness": 8, "seed": 42})

    assert a.protocol_id == b.protocol_id


def test_scientific_parameter_change_changes_protocol_identity():
    assert (
        make_protocol(parameters={"seed": 1}).protocol_id
        != make_protocol(parameters={"seed": 2}).protocol_id
    )


def test_backend_and_preparation_versions_are_identity():
    base = make_protocol()

    assert make_protocol(backend_version="1.2.8").protocol_id != base.protocol_id
    assert make_protocol(ligand_preparation_id="lprep_2").protocol_id != base.protocol_id
    assert make_protocol(receptor_preparation_id="rprep_2").protocol_id != base.protocol_id


def test_parameters_are_deeply_immutable():
    source = {"search": {"weights": [1, 2]}}
    protocol = make_protocol(parameters=source)
    original_id = protocol.protocol_id

    source["search"]["weights"].append(3)

    assert protocol.parameters["search"]["weights"] == (1, 2)
    assert protocol.protocol_id == original_id
    with pytest.raises(TypeError):
        protocol.parameters["search"]["weights"][0] = 9


def test_protocol_is_frozen():
    protocol = make_protocol()

    with pytest.raises(FrozenInstanceError):
        protocol.backend = "gnina"


@pytest.mark.parametrize(
    "field",
    [
        "backend",
        "backend_version",
        "receptor_preparation_id",
        "ligand_preparation_id",
    ],
)
def test_required_protocol_fields_reject_blank(field):
    with pytest.raises(DomainValidationError):
        make_protocol(**{field: " "})


@dataclass
class MutableSearchParameters:
    weights: list[int]
    enabled: bool = True


def test_mutable_dataclass_parameter_is_snapshotted():
    source = MutableSearchParameters(weights=[1, 2])
    protocol = make_protocol(parameters={"search": source})
    original_id = protocol.protocol_id

    source.weights.append(3)
    source.enabled = False

    assert protocol.protocol_id == original_id
    assert protocol.parameters["search"]["weights"] == (1, 2)
    assert protocol.parameters["search"]["enabled"] is True

    with pytest.raises(TypeError):
        protocol.parameters["search"]["enabled"] = False
