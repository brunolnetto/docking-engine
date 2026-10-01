import json

import pytest

from benchmarks.posebusters.run_preparation_canary import (
    evaluate_rows,
    load_treatment,
    paired_outcomes,
    serializable_config,
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


def test_treatment_loader_rejects_wrong_boolean_type(tmp_path):
    path = tmp_path / "treatment.json"
    path.write_text(
        json.dumps({"receptor_delete_bad_res": "false"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="field types are invalid"):
        load_treatment(path)


def test_serializable_config_converts_case_id_frozenset():
    config = RedockingHarnessConfig(
        benchmark="x",
        expected_case_count=2,
        run_prefix="x",
        worker_id="x",
        allowed_case_ids=frozenset({"b", "a"}),
    )
    payload = serializable_config(config)
    assert payload["allowed_case_ids"] == ["a", "b"]
    json.dumps(payload)


def test_evaluate_rows_attaches_scientific_labels_without_changing_execution_state():
    from types import SimpleNamespace

    def evaluator(row):
        result = SimpleNamespace(
            rmsd_angstrom=1.25,
            pb_valid=True,
            pose_rmsd_angstroms=(1.25, 2.5),
            pose_pb_valid=(True, False),
        )
        return result, [{"rank": 1, "reference_rmsd_angstrom": 1.25}]

    rows = evaluate_rows(
        [{"case_id": "a", "completed": True}],
        evaluator=evaluator,
    )

    assert rows[0]["completed"] is True
    assert rows[0]["scientific_evaluation_completed"] is True
    assert rows[0]["rmsd_angstrom"] == 1.25
    assert rows[0]["pb_valid"] is True
    assert rows[0]["pose_evidence"][0]["rank"] == 1


def test_evaluate_rows_fails_closed_without_relabeling_execution_failure():
    def evaluator(row):
        raise RuntimeError("PoseBusters failed")

    rows = evaluate_rows(
        [{"case_id": "a", "completed": True}],
        evaluator=evaluator,
    )

    assert rows[0]["completed"] is True
    assert rows[0]["scientific_evaluation_completed"] is False
    assert rows[0]["rmsd_angstrom"] is None
    assert rows[0]["pb_valid"] is None
    assert "PoseBusters failed" in rows[0]["scientific_evaluation_error"]


def test_evaluate_rows_does_not_attempt_failed_engine_case():
    called = False

    def evaluator(row):
        nonlocal called
        called = True
        raise AssertionError("must not evaluate failed execution")

    rows = evaluate_rows(
        [{"case_id": "a", "completed": False, "failure_stage": "preparation"}],
        evaluator=evaluator,
    )

    assert called is False
    assert rows[0]["completed"] is False
    assert rows[0]["scientific_evaluation_completed"] is False
