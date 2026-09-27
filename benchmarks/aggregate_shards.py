from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Iterable

from benchmarks.common import CaseResult, summarize, write_summary
from benchmarks.interaction_summary import aggregate_family_rows, render_interaction_report


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a cases list")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} contains a non-object case row")
    return rows


def _merge_rows(
    paths: Iterable[Path],
    *,
    label: str,
) -> list[dict[str, Any]]:
    by_case: dict[str, dict[str, Any]] = {}
    for path in sorted(paths):
        for row in _load_cases(path):
            case_id = row.get("case_id")
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{path} contains a case without case_id")
            if case_id in by_case:
                raise ValueError(f"duplicate {label} case_id: {case_id}")
            by_case[case_id] = row
    return [by_case[key] for key in sorted(by_case)]


def aggregate(
    *,
    engine_paths: Iterable[Path],
    evaluated_paths: Iterable[Path],
    benchmark: str,
    expected_cases: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], object]:
    engine_rows = _merge_rows(engine_paths, label="engine")
    evaluated_rows = _merge_rows(evaluated_paths, label="evaluated")

    if len(engine_rows) != expected_cases:
        raise ValueError(
            "full benchmark engine case count mismatch: "
            f"expected {expected_cases}, got {len(engine_rows)}"
        )
    if len(evaluated_rows) != expected_cases:
        raise ValueError(
            "full benchmark evaluated case count mismatch: "
            f"expected {expected_cases}, got {len(evaluated_rows)}"
        )

    engine_ids = {str(row["case_id"]) for row in engine_rows}
    evaluated_ids = {str(row["case_id"]) for row in evaluated_rows}
    if engine_ids != evaluated_ids:
        missing_evaluated = sorted(engine_ids - evaluated_ids)
        missing_engine = sorted(evaluated_ids - engine_ids)
        raise ValueError(
            "engine/evaluated case sets differ: "
            f"missing_evaluated={missing_evaluated}, "
            f"missing_engine={missing_engine}"
        )

    results = tuple(CaseResult(**row) for row in evaluated_rows)
    engine_completed = sum(row.get("completed") is True for row in engine_rows)
    engine_rate = engine_completed / expected_cases
    summary = replace(
        summarize(benchmark, results),
        engine_completed_cases=engine_completed,
        engine_execution_success_rate=engine_rate,
    )
    return engine_rows, evaluated_rows, summary



def aggregate_interactions(
    *,
    interaction_paths: Iterable[Path],
    expected_case_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    rows = _merge_rows(interaction_paths, label="interaction")
    interaction_ids = {str(row["case_id"]) for row in rows}
    if interaction_ids != expected_case_ids:
        missing_interaction = sorted(expected_case_ids - interaction_ids)
        unexpected_interaction = sorted(interaction_ids - expected_case_ids)
        raise ValueError(
            "engine/interaction case sets differ: "
            f"missing_interaction={missing_interaction}, "
            f"unexpected_interaction={unexpected_interaction}"
        )

    successful_families: list[list[dict[str, object]]] = []
    for row in rows:
        if row.get("completed") is not True:
            continue
        families = row.get("families")
        if not isinstance(families, list) or not all(
            isinstance(family, dict) for family in families
        ):
            raise ValueError(
                f"interaction case {row['case_id']} must contain a families list"
            )
        successful_families.append(families)

    total = len(rows)
    evaluable = len(successful_families)
    summary = {
        "total_cases": total,
        "interaction_evaluable_cases": evaluable,
        "interaction_evaluability_rate": (
            evaluable / total if total else None
        ),
        "families": aggregate_family_rows(successful_families),
    }
    return rows, summary


def _write_cases(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cases": rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    benchmark = manifest.get("benchmark")
    expected_cases = manifest.get("dataset", {}).get("paper_case_count")
    if not isinstance(benchmark, str) or not benchmark:
        raise ValueError("manifest benchmark is missing")
    if not isinstance(expected_cases, int) or isinstance(expected_cases, bool):
        raise ValueError("manifest dataset.paper_case_count must be an integer")

    engine_paths = tuple(args.input_root.rglob("engine_cases.json"))
    evaluated_paths = tuple(args.input_root.rglob("evaluated_cases.json"))
    interaction_paths = tuple(args.input_root.rglob("interaction_cases.json"))
    if not engine_paths or not evaluated_paths:
        raise ValueError("no shard benchmark artifacts discovered")
    if not interaction_paths:
        raise ValueError("no shard interaction artifacts discovered")

    engine_rows, evaluated_rows, summary = aggregate(
        engine_paths=engine_paths,
        evaluated_paths=evaluated_paths,
        benchmark=benchmark,
        expected_cases=expected_cases,
    )

    interaction_rows, interaction_summary = aggregate_interactions(
        interaction_paths=interaction_paths,
        expected_case_ids={str(row["case_id"]) for row in engine_rows},
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    _write_cases(args.output_root / "engine_cases.json", engine_rows)
    _write_cases(args.output_root / "evaluated_cases.json", evaluated_rows)
    _write_cases(args.output_root / "interaction_cases.json", interaction_rows)
    write_summary(args.output_root / "summary.json", summary)
    (args.output_root / "interaction_summary.json").write_text(
        json.dumps(interaction_summary, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    (args.output_root / "interaction_report.md").write_text(
        render_interaction_report(interaction_summary) + "\\n",
        encoding="utf-8",
    )
    print(args.output_root / "summary.json")
    print(args.output_root / "interaction_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
