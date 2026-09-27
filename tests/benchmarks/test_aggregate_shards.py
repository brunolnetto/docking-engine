from __future__ import annotations

import json

import pytest

from benchmarks.aggregate_shards import aggregate, aggregate_interactions


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


def _interaction(case_id: str, *, completed: bool = True, tp: int = 1, fp: int = 0, fn: int = 0):
    if not completed:
        return {
            "case_id": case_id,
            "completed": False,
            "failure_stage": "interaction_evaluation",
            "error": "failed",
        }
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        None
        if precision is None or recall is None
        else (0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    )
    union = tp + fp + fn
    return {
        "case_id": case_id,
        "completed": True,
        "reference_fingerprint_size": tp + fn,
        "predicted_fingerprint_size": tp + fp,
        "families": [
            {
                "kind": "hydrogen_bond",
                "reference_count": tp + fn,
                "predicted_count": tp + fp,
                "true_positive": tp,
                "false_positive": fp,
                "false_negative": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "jaccard": tp / union if union else None,
            }
        ],
    }


def test_aggregate_interactions_recomputes_metrics_from_case_evidence(tmp_path):
    first = _write(
        tmp_path / "a" / "interaction_cases.json",
        [_interaction("a", tp=1, fp=1, fn=0)],
    )
    second = _write(
        tmp_path / "b" / "interaction_cases.json",
        [
            _interaction("b", tp=1, fp=0, fn=1),
            _interaction("c", completed=False),
        ],
    )

    rows, summary = aggregate_interactions(
        interaction_paths=(first, second),
        expected_case_ids={"a", "b", "c"},
    )

    assert [row["case_id"] for row in rows] == ["a", "b", "c"]
    assert summary["total_cases"] == 3
    assert summary["interaction_evaluable_cases"] == 2
    assert summary["interaction_evaluability_rate"] == pytest.approx(2 / 3)
    family = summary["families"][0]
    assert family["kind"] == "hydrogen_bond"
    assert family["true_positive"] == 2
    assert family["false_positive"] == 1
    assert family["false_negative"] == 1
    assert family["precision"] == pytest.approx(2 / 3)
    assert family["recall"] == pytest.approx(2 / 3)
    assert family["f1"] == pytest.approx(2 / 3)


def test_aggregate_interactions_requires_identical_case_set(tmp_path):
    interactions = _write(
        tmp_path / "interaction_cases.json",
        [_interaction("a")],
    )

    with pytest.raises(ValueError, match="engine/interaction case sets differ"):
        aggregate_interactions(
            interaction_paths=(interactions,),
            expected_case_ids={"a", "b"},
        )
