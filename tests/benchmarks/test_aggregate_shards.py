from __future__ import annotations

import json

import pytest

from benchmarks.aggregate_shards import aggregate


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cases": rows}), encoding="utf-8")
    return path


def _evaluated(case_id: str, *, success: bool = True):
    return {
        "case_id": case_id,
        "completed": True,
        "rmsd_angstrom": 1.0 if success else 3.0,
        "pb_valid": True,
        "runtime_seconds": 10.0,
        "pose_rmsd_angstroms": [1.0 if success else 3.0],
        "pose_pb_valid": [True],
        "pose_evaluation_limit": 1,
    }


def test_aggregate_shards_reconstructs_full_summary(tmp_path):
    engine_a = _write(
        tmp_path / "a" / "engine_cases.json",
        [{"case_id": "b", "completed": True}, {"case_id": "a", "completed": True}],
    )
    engine_b = _write(
        tmp_path / "b" / "engine_cases.json",
        [{"case_id": "d", "completed": False}, {"case_id": "c", "completed": True}],
    )
    eval_a = _write(
        tmp_path / "a" / "evaluated_cases.json",
        [_evaluated("b", success=False), _evaluated("a")],
    )
    eval_b = _write(
        tmp_path / "b" / "evaluated_cases.json",
        [
            {
                "case_id": "d",
                "completed": False,
                "failure_stage": "docking",
                "error": "failed",
            },
            _evaluated("c"),
        ],
    )

    engine, evaluated, summary = aggregate(
        engine_paths=(engine_a, engine_b),
        evaluated_paths=(eval_a, eval_b),
        benchmark="pb",
        expected_cases=4,
    )

    assert [row["case_id"] for row in engine] == ["a", "b", "c", "d"]
    assert [row["case_id"] for row in evaluated] == ["a", "b", "c", "d"]
    assert summary.total_cases == 4
    assert summary.engine_completed_cases == 3
    assert summary.engine_execution_success_rate == pytest.approx(0.75)
    assert summary.completed_cases == 3
    assert summary.top1_rmsd_le_2a_rate == pytest.approx(2 / 3)


def test_aggregate_shards_rejects_duplicate_cases(tmp_path):
    first = _write(
        tmp_path / "a" / "engine_cases.json",
        [{"case_id": "a", "completed": True}],
    )
    duplicate = _write(
        tmp_path / "b" / "engine_cases.json",
        [{"case_id": "a", "completed": True}],
    )
    evaluated = _write(
        tmp_path / "a" / "evaluated_cases.json",
        [_evaluated("a")],
    )

    with pytest.raises(ValueError, match="duplicate engine case_id"):
        aggregate(
            engine_paths=(first, duplicate),
            evaluated_paths=(evaluated,),
            benchmark="pb",
            expected_cases=1,
        )


def test_aggregate_shards_requires_complete_case_count(tmp_path):
    engine = _write(
        tmp_path / "engine_cases.json",
        [{"case_id": "a", "completed": True}],
    )
    evaluated = _write(
        tmp_path / "evaluated_cases.json",
        [_evaluated("a")],
    )

    with pytest.raises(ValueError, match="expected 2"):
        aggregate(
            engine_paths=(engine,),
            evaluated_paths=(evaluated,),
            benchmark="pb",
            expected_cases=2,
        )


def test_aggregate_shards_requires_identical_case_sets(tmp_path):
    engine = _write(
        tmp_path / "engine_cases.json",
        [{"case_id": "a", "completed": True}],
    )
    evaluated = _write(
        tmp_path / "evaluated_cases.json",
        [_evaluated("b")],
    )

    with pytest.raises(ValueError, match="case sets differ"):
        aggregate(
            engine_paths=(engine,),
            evaluated_paths=(evaluated,),
            benchmark="pb",
            expected_cases=1,
        )
