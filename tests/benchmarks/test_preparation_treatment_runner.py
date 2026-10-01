import json

import pytest

from benchmarks.posebusters.run_preparation_canary import (
    load_treatment,
    paired_outcomes,
)
from benchmarks.redocking import RedockingHarnessConfig, receptor_preparation_parameters


def test_receptor_parameters_expose_declared_meeko_treatments():
    config = RedockingHarnessConfig(
        benchmark="x",
        expected_case_count=1,
        run_prefix="x",
        worker_id="x",
        receptor_wanted_altloc="B",
        receptor_set_template="A:123=HIE",
        receptor_delete_residues="A:999",
    )
    assert receptor_preparation_parameters(config) == {
        "wanted_altloc": "B",
        "set_template": "A:123=HIE",
        "delete_residues": "A:999",
    }


def test_treatment_loader_rejects_non_preparation_knobs(tmp_path):
    path = tmp_path / "treatment.json"
    path.write_text(json.dumps({"exhaustiveness": 32}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported treatment fields"):
        load_treatment(path)


def test_paired_outcomes_requires_identical_case_sets():
    with pytest.raises(ValueError, match="case sets differ"):
        paired_outcomes(
            [{"case_id": "a", "completed": False}],
            [{"case_id": "b", "completed": True}],
            family="HEM",
        )


def test_execution_only_outcomes_cannot_be_promoted_without_scientific_labels():
    outcomes = paired_outcomes(
        [
            {"case_id": "failed", "completed": False},
            {"case_id": "control", "completed": True},
        ],
        [
            {"case_id": "failed", "completed": True},
            {"case_id": "control", "completed": True},
        ],
        family="HEM",
    )
    assert outcomes[0].baseline_rmsd is None
    assert outcomes[1].baseline_pb_valid is None
