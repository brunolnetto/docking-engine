from __future__ import annotations

import math

import pytest

from benchmarks.common import CaseResult, summarize
from benchmarks.posebusters.evaluate_engine import (
    _boolean_value,
    _find_rmsd_numeric,
    _physical_validity,
)


def test_benchmark_summary_separates_science_and_engine_failures():
    rows = (
        CaseResult(
            case_id="a",
            completed=True,
            rmsd_angstrom=1.5,
            pb_valid=True,
            runtime_seconds=10.0,
        ),
        CaseResult(
            case_id="b",
            completed=True,
            rmsd_angstrom=3.0,
            pb_valid=True,
            runtime_seconds=20.0,
        ),
        CaseResult(
            case_id="c",
            completed=True,
            rmsd_angstrom=1.0,
            pb_valid=False,
            runtime_seconds=30.0,
        ),
        CaseResult(
            case_id="d",
            completed=False,
            failure_stage="preparation",
        ),
    )

    summary = summarize("pb", rows)

    assert summary.total_cases == 4
    assert summary.completed_cases == 3
    assert summary.execution_success_rate == pytest.approx(0.75)
    assert summary.top1_rmsd_le_2a_rate == pytest.approx(2 / 3)
    assert summary.pb_valid_rate == pytest.approx(2 / 3)
    assert summary.combined_success_rate == pytest.approx(1 / 3)
    assert summary.median_rmsd_angstrom == pytest.approx(1.5)
    assert summary.median_runtime_seconds == pytest.approx(20.0)
    assert summary.failures_by_stage == {"preparation": 1}


def test_benchmark_summary_handles_no_evaluable_cases():
    summary = summarize(
        "empty",
        (
            CaseResult(
                case_id="failed",
                completed=False,
                failure_stage=None,
            ),
        ),
    )

    assert summary.execution_success_rate == 0.0
    assert summary.top1_rmsd_le_2a_rate == 0.0
    assert summary.pb_valid_rate == 0.0
    assert summary.combined_success_rate == 0.0
    assert summary.median_rmsd_angstrom is None
    assert summary.median_runtime_seconds is None
    assert summary.failures_by_stage == {"unknown": 1}


def test_find_rmsd_numeric_ignores_boolean_rmsd_check():
    row = {
        ("rmsd", "rmsd_<=_2A"): True,
        ("rmsd", "rmsd"): 1.234,
    }

    assert _find_rmsd_numeric(row) == pytest.approx(1.234)


def test_physical_validity_excludes_rmsd_boolean():
    row = {
        "sanitization": True,
        "bond_lengths": True,
        "rmsd_<=_2A": False,
    }

    assert _physical_validity(row) is True


def test_physical_validity_requires_checks():
    with pytest.raises(RuntimeError, match="no physical-validity"):
        _physical_validity({"rmsd_<=_2A": True})



@pytest.mark.parametrize("type_name", ["bool", "bool_"])
def test_boolean_value_accepts_numpy_style_bool(type_name):
    BoolLike = type(
        type_name,
        (),
        {
            "__module__": "numpy",
            "__bool__": lambda self: True,
        },
    )

    assert _boolean_value(BoolLike()) is True
