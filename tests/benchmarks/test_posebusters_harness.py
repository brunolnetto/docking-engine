from __future__ import annotations

import math

import pytest

from benchmarks.common import CaseResult, summarize
from benchmarks.posebusters.cases import load_case_ids
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
            pose_rmsd_angstroms=(1.5, 1.2, 0.9),
            pose_evaluation_limit=9,
        ),
        CaseResult(
            case_id="b",
            completed=True,
            rmsd_angstrom=3.0,
            pb_valid=True,
            runtime_seconds=20.0,
            pose_rmsd_angstroms=(3.0, 2.5, 1.8),
            pose_evaluation_limit=9,
        ),
        CaseResult(
            case_id="c",
            completed=True,
            rmsd_angstrom=1.0,
            pb_valid=False,
            runtime_seconds=30.0,
            pose_rmsd_angstroms=(1.0, 0.8, 0.7),
            pose_evaluation_limit=9,
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
    assert summary.topn_rmsd_le_2a_rates["3"] == pytest.approx(1.0)
    assert summary.topn_rmsd_le_2a_rates["5"] == pytest.approx(1.0)
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



def test_find_rmsd_numeric_skips_numpy_boolean_check():
    BoolLike = type(
        "bool",
        (),
        {
            "__module__": "numpy",
            "__bool__": lambda self: True,
            "__float__": lambda self: 1.0,
        },
    )
    row = {
        ("rmsd", "rmsd_<=_2A"): BoolLike(),
        ("rmsd", "rmsd"): 2.345,
    }

    assert _find_rmsd_numeric(row) == pytest.approx(2.345)


def test_case_result_top_n_preserves_engine_rank_order():
    row = CaseResult(
        case_id="ranked",
        completed=True,
        rmsd_angstrom=4.0,
        pose_rmsd_angstroms=(4.0, 3.0, 1.5, 0.8),
        pose_evaluation_limit=9,
    )

    assert row.top_n_rmsd_success(1) is False
    assert row.top_n_rmsd_success(2) is False
    assert row.top_n_rmsd_success(3) is True
    with pytest.raises(ValueError, match=">= 1"):
        row.top_n_rmsd_success(0)


def test_top_n_is_unavailable_when_evaluation_depth_is_too_shallow():
    row = CaseResult(
        case_id="shallow",
        completed=True,
        rmsd_angstrom=3.0,
        pose_rmsd_angstroms=(3.0,),
        pose_evaluation_limit=1,
    )

    assert row.top_n_rmsd_success(1) is False
    assert row.top_n_rmsd_success(3) is None


def test_top_n_preserves_known_success_before_missing_rank():
    row = CaseResult(
        case_id="partial",
        completed=True,
        rmsd_angstrom=3.0,
        pose_rmsd_angstroms=(3.0, None, 1.5),
        pose_evaluation_limit=3,
    )

    assert row.top_n_rmsd_success(2) is None
    assert row.top_n_rmsd_success(3) is True


def test_combined_metric_excludes_missing_top1_rmsd():
    summary = summarize(
        "pb",
        (
            CaseResult(
                case_id="missing-top1",
                completed=True,
                pb_valid=True,
                pose_rmsd_angstroms=(None, 1.5),
                pose_evaluation_limit=2,
            ),
        ),
    )

    assert summary.rmsd_evaluable_cases == 0
    assert summary.combined_evaluable_cases == 0
    assert summary.combined_success_rate == 0.0


def test_pinned_posebusters_subset_contains_308_unique_identifiers():
    identifiers = load_case_ids()

    assert len(identifiers) == 308
    assert "5SAK_ZRY" in identifiers
    assert "5S8I_2LY" not in identifiers



def test_load_case_ids_rejects_duplicates(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("A\nA\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="contains duplicates"):
        load_case_ids(path)


def test_load_case_ids_supports_explicit_smoke_subset(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("1iep_STI\n", encoding="utf-8")

    assert load_case_ids(path, expected_count=None) == frozenset({"1iep_STI"})


def test_load_case_ids_rejects_wrong_journal_subset_size(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("A\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="exactly 308 unique"):
        load_case_ids(path)
