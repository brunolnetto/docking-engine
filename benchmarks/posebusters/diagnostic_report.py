from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a cases list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row["case_id"])
        if case_id in result:
            raise ValueError(f"duplicate case_id in {path}: {case_id}")
        result[case_id] = row
    return result


def stage_summary(
    engine: dict[str, dict[str, Any]],
    evaluated: dict[str, dict[str, Any]],
    interactions: dict[str, dict[str, Any]],
) -> dict[str, object]:
    ids = set(engine)
    if set(evaluated) != ids or set(interactions) != ids:
        raise ValueError("engine, evaluation and interaction case sets must match")

    total = len(ids)
    engine_ok = sum(engine[c].get("completed") is True for c in ids)
    rmsd_ok = sum(
        evaluated[c].get("completed") is True
        and evaluated[c].get("rmsd_angstrom") is not None
        for c in ids
    )
    top1_ok = sum(
        evaluated[c].get("completed") is True
        and isinstance(evaluated[c].get("rmsd_angstrom"), (int, float))
        and float(evaluated[c]["rmsd_angstrom"]) <= 2.0
        for c in ids
    )
    pb_evaluable = sum(
        evaluated[c].get("completed") is True
        and evaluated[c].get("pb_valid") is not None
        for c in ids
    )
    pb_valid = sum(evaluated[c].get("pb_valid") is True for c in ids)
    interaction_ok = sum(
        interactions[c].get("completed") is True for c in ids
    )

    def coverage_metric(count: int) -> dict[str, object]:
        return {
            "cases": count,
            "denominator": total,
            "rate": count / total if total else None,
        }

    def scientific_metric(count: int, denominator: int) -> dict[str, object]:
        return {
            "cases": count,
            "denominator": denominator,
            "rate": count / denominator if denominator else None,
        }

    return {
        "total_cases": total,
        "engine_execution": coverage_metric(engine_ok),
        "rmsd_evaluable": coverage_metric(rmsd_ok),
        "top1_rmsd_le_2a": scientific_metric(top1_ok, rmsd_ok),
        "pb_evaluable": coverage_metric(pb_evaluable),
        "pb_valid": scientific_metric(pb_valid, pb_evaluable),
        "interaction_evaluable": coverage_metric(interaction_ok),
    }


def render_markdown(summary: dict[str, object]) -> str:
    total = int(summary["total_cases"])
    labels = (
        ("engine_execution", "Engine execution"),
        ("rmsd_evaluable", "RMSD evaluable"),
        ("top1_rmsd_le_2a", "Top-1 RMSD <= 2 A"),
        ("pb_evaluable", "PB evaluable"),
        ("pb_valid", "PB valid"),
        ("interaction_evaluable", "Interaction evaluable"),
    )
    lines = [
        "# PoseBusters stage diagnostics",
        "",
        f"Cases: {total}",
        "",
        "| Question | Cases | Rate |",
        "| --- | ---: | ---: |",
    ]
    for key, label in labels:
        value = summary[key]
        count = int(value["cases"])
        denominator = int(value["denominator"])
        rate = value["rate"]
        rendered_rate = "n/a" if rate is None else f"{float(rate) * 100:.1f}%"
        lines.append(
            f"| {label} | {count}/{denominator} | {rendered_rate} |"
        )
    lines.extend(
        [
            "",
            "Each row is an independent evidence axis. A failure on one axis is not "
            "silently converted into failure on another.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-cases", type=Path, required=True)
    parser.add_argument("--evaluated-cases", type=Path, required=True)
    parser.add_argument("--interaction-cases", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    args = parser.parse_args()

    summary = stage_summary(
        _load_rows(args.engine_cases),
        _load_rows(args.evaluated_cases),
        _load_rows(args.interaction_cases),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_report.write_text(render_markdown(summary) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
