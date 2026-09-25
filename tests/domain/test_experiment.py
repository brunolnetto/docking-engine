from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from moldock.domain import DockingExperiment, DomainValidationError


def make_experiment(**overrides):
    values = dict(
        receptor_id="rec_1",
        ligand_set_id="lib_1",
        search_space_id="space_1",
        backend="vina",
        backend_version="1.2.7",
        receptor_preparation_id="rprep_1",
        ligand_preparation_id="lprep_1",
        parameters={"exhaustiveness": 8, "seed": 42},
    )
    values.update(overrides)
    return DockingExperiment(**values)


def test_equivalent_experiments_have_same_identity():
    a = make_experiment(parameters={"seed": 42, "exhaustiveness": 8})
    b = make_experiment(parameters={"exhaustiveness": 8, "seed": 42})

    assert a.experiment_id == b.experiment_id


def test_parameter_change_creates_new_experiment_identity():
    a = make_experiment(parameters={"exhaustiveness": 8})
    b = make_experiment(parameters={"exhaustiveness": 16})

    assert a.experiment_id != b.experiment_id


def test_backend_version_is_part_of_experiment_identity():
    a = make_experiment(backend_version="1.2.7")
    b = make_experiment(backend_version="1.2.8")

    assert a.experiment_id != b.experiment_id


def test_experiment_is_immutable():
    experiment = make_experiment()

    with pytest.raises(FrozenInstanceError):
        experiment.backend = "gnina"


def test_parameters_are_not_mutable_after_construction():
    source = {"exhaustiveness": 8}
    experiment = make_experiment(parameters=source)

    source["exhaustiveness"] = 99

    assert experiment.parameters["exhaustiveness"] == 8
    with pytest.raises(TypeError):
        experiment.parameters["exhaustiveness"] = 16


def test_nested_parameters_are_deeply_immutable_and_identity_stays_stable():
    source = {
        "search": {
            "weights": [1.0, 2.0],
            "options": {"local_only": False},
        }
    }
    experiment = make_experiment(parameters=source)
    original_id = experiment.experiment_id

    source["search"]["weights"].append(3.0)
    source["search"]["options"]["local_only"] = True

    assert experiment.experiment_id == original_id
    assert experiment.parameters["search"]["weights"] == (1.0, 2.0)
    assert experiment.parameters["search"]["options"]["local_only"] is False

    with pytest.raises(TypeError):
        experiment.parameters["search"]["options"]["local_only"] = True

    with pytest.raises(TypeError):
        experiment.parameters["search"]["weights"][0] = 99.0


def test_tuple_and_set_parameters_are_deeply_frozen():
    experiment = make_experiment(
        parameters={
            "tuple_value": ({"x": 1}, 2),
            "set_value": {"b", "a"},
        }
    )

    assert isinstance(experiment.parameters["tuple_value"], tuple)
    assert isinstance(experiment.parameters["tuple_value"][0], MappingProxyType)
    assert experiment.parameters["set_value"] == frozenset({"a", "b"})


def test_required_field_cannot_be_blank():
    with pytest.raises(DomainValidationError):
        make_experiment(backend=" ")
