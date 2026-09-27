from __future__ import annotations

import pytest

from benchmarks.regression import build_baseline, compare


def _manifest() -> dict[str, object]:
    return {
        "benchmark": "posebusters_benchmark_v1",
        "dataset": {"paper_case_count": 4},
    }


def _summary(
    *,
    top1: float = 0.60,
    combined: float = 0.55,
    completed: int = 4,
    rmsd_evaluable: int = 4,
    pb_evaluable: int = 4,
    combined_evaluable: int = 4,
) -> dict[str, object]:
    return {
        "total_cases": 4,
        "completed_cases": completed,
        "rmsd_evaluable_cases": rmsd_evaluable,
        "pb_evaluable_cases": pb_evaluable,
        "combined_evaluable_cases": combined_evaluable,
        "top1_rmsd_le_2a_rate": top1,
        "pb_valid_rate": 0.70,
        "combined_success_rate": combined,
        "topn_rmsd_le_2a_rates": {"1": top1, "3": 0.75},
        "median_rmsd_angstrom": 1.8,
        "median_runtime_seconds": 30.0,
    }


def _engine(successes: int = 4) -> dict[str, object]:
    return {
        "cases": [
            {"case_id": str(i), "completed": i < successes}
            for i in range(4)
        ]
    }


def test_build_baseline_requires_complete_benchmark():
    with pytest.raises(ValueError, match="complete benchmark"):
        build_baseline(
            summary={**_summary(), "total_cases": 3},
            engine_cases=_engine(),
            manifest=_manifest(),
            manifest_digest="abc",
            source_commit="deadbeef",
        )


def test_build_baseline_records_measured_engine_rate():
    baseline = build_baseline(
        summary=_summary(),
        engine_cases=_engine(successes=3),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )

    assert baseline["kind"] == "repository_measured_baseline"
    assert baseline["case_count"] == 4
    assert baseline["metrics"]["engine_execution_success_rate"] == pytest.approx(0.75)
    assert baseline["metrics"]["top1_rmsd_le_2a_rate"] == pytest.approx(0.60)


def test_compare_passes_within_regression_tolerances():
    baseline = build_baseline(
        summary=_summary(),
        engine_cases=_engine(),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )
    result = compare(
        baseline=baseline,
        summary=_summary(top1=0.581, combined=0.531),
        engine_cases=_engine(),
        manifest_digest="abc",
    )

    assert result["passed"] is True
    assert all(check["passed"] for check in result["checks"])


def test_compare_fails_when_top1_drop_exceeds_tolerance():
    baseline = build_baseline(
        summary=_summary(),
        engine_cases=_engine(),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )
    result = compare(
        baseline=baseline,
        summary=_summary(top1=0.57),
        engine_cases=_engine(),
        manifest_digest="abc",
    )

    assert result["passed"] is False
    failed = [check for check in result["checks"] if not check["passed"]]
    assert [check["metric"] for check in failed] == ["top1_rmsd_le_2a_rate"]


def test_compare_rejects_protocol_drift():
    baseline = build_baseline(
        summary=_summary(),
        engine_cases=_engine(),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )

    with pytest.raises(ValueError, match="manifest differs"):
        compare(
            baseline=baseline,
            summary=_summary(),
            engine_cases=_engine(),
            manifest_digest="different",
        )


def test_compare_fails_when_evaluator_completeness_regresses():
    baseline = build_baseline(
        summary=_summary(),
        engine_cases=_engine(),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )
    result = compare(
        baseline=baseline,
        summary=_summary(
            completed=3,
            rmsd_evaluable=3,
            pb_evaluable=3,
            combined_evaluable=3,
        ),
        engine_cases=_engine(),
        manifest_digest="abc",
    )

    assert result["passed"] is False
    failed = {
        check["metric"]
        for check in result["checks"]
        if not check["passed"]
    }
    assert "end_to_end_evaluability_rate" in failed
    assert "rmsd_evaluable_rate" in failed
    assert "pb_evaluable_rate" in failed
    assert "combined_evaluable_rate" in failed


def test_compare_accepts_exact_documented_drop_boundary():
    baseline = build_baseline(
        summary=_summary(top1=0.60),
        engine_cases=_engine(),
        manifest=_manifest(),
        manifest_digest="abc",
        source_commit="deadbeef",
    )
    result = compare(
        baseline=baseline,
        summary=_summary(top1=0.58),
        engine_cases=_engine(),
        manifest_digest="abc",
    )

    top1 = next(
        check
        for check in result["checks"]
        if check["metric"] == "top1_rmsd_le_2a_rate"
    )
    assert top1["delta"] == pytest.approx(-0.02)
    assert top1["passed"] is True


def test_build_baseline_rejects_zero_engine_successes():
    with pytest.raises(ValueError, match="zero successful engine cases"):
        build_baseline(
            summary=_summary(completed=0, rmsd_evaluable=0, pb_evaluable=0, combined_evaluable=0),
            engine_cases=_engine(successes=0),
            manifest=_manifest(),
            manifest_digest="abc",
            source_commit="deadbeef",
        )


def test_build_baseline_rejects_zero_evaluable_scientific_cases():
    with pytest.raises(ValueError, match="zero end-to-end evaluable cases"):
        build_baseline(
            summary=_summary(completed=0, rmsd_evaluable=0, pb_evaluable=0, combined_evaluable=0),
            engine_cases=_engine(successes=4),
            manifest=_manifest(),
            manifest_digest="abc",
            source_commit="deadbeef",
        )


def test_build_baseline_requires_each_scientific_evaluable_denominator():
    with pytest.raises(ValueError, match="without RMSD, PB-valid and combined"):
        build_baseline(
            summary=_summary(completed=4, rmsd_evaluable=4, pb_evaluable=0, combined_evaluable=0),
            engine_cases=_engine(successes=4),
            manifest=_manifest(),
            manifest_digest="abc",
            source_commit="deadbeef",
        )
