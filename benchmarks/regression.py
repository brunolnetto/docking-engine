from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_THRESHOLDS = {
    "engine_execution_success_rate": 0.01,
    "top1_rmsd_le_2a_rate": 0.02,
    "combined_success_rate": 0.02,
}


@dataclass(frozen=True)
class RegressionCheck:
    metric: str
    baseline: float
    current: float
    delta: float
    allowed_drop: float
    passed: bool


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_success(engine_cases: dict[str, Any]) -> tuple[int, int, float | None]:
    rows = engine_cases.get("cases")
    if not isinstance(rows, list):
        raise ValueError("engine cases payload must contain a cases list")
    total = len(rows)
    completed = sum(
        1
        for row in rows
        if isinstance(row, dict) and row.get("completed") is True
    )
    return completed, total, (completed / total if total else None)


def build_baseline(
    *,
    summary: dict[str, Any],
    engine_cases: dict[str, Any],
    manifest: dict[str, Any],
    manifest_digest: str,
    source_commit: str,
) -> dict[str, Any]:
    benchmark = manifest.get("benchmark")
    expected_cases = manifest.get("dataset", {}).get("paper_case_count")
    total_cases = summary.get("total_cases")
    if not isinstance(expected_cases, int) or expected_cases < 1:
        raise ValueError("manifest must declare a positive dataset.paper_case_count")
    if total_cases != expected_cases:
        raise ValueError(
            "authoritative baseline requires the complete benchmark: "
            f"expected {expected_cases} cases, got {total_cases}"
        )

    completed, engine_total, engine_rate = engine_success(engine_cases)
    if engine_total != expected_cases:
        raise ValueError(
            "engine case count does not match complete benchmark: "
            f"expected {expected_cases}, got {engine_total}"
        )
    if engine_rate is None:
        raise ValueError("cannot baseline an empty engine run")

    required_rates = (
        "top1_rmsd_le_2a_rate",
        "combined_success_rate",
        "pb_valid_rate",
    )
    for name in required_rates:
        value = summary.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"summary missing numeric metric: {name}")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "repository_measured_baseline",
        "benchmark": benchmark,
        "case_count": expected_cases,
        "manifest_sha256": manifest_digest,
        "source_commit": source_commit,
        "metrics": {
            "engine_execution_success_rate": engine_rate,
            "engine_completed_cases": completed,
            "top1_rmsd_le_2a_rate": float(summary["top1_rmsd_le_2a_rate"]),
            "pb_valid_rate": float(summary["pb_valid_rate"]),
            "combined_success_rate": float(summary["combined_success_rate"]),
            "topn_rmsd_le_2a_rates": dict(
                summary.get("topn_rmsd_le_2a_rates") or {}
            ),
            "median_rmsd_angstrom": summary.get("median_rmsd_angstrom"),
            "median_runtime_seconds": summary.get("median_runtime_seconds"),
        },
    }


def compare(
    *,
    baseline: dict[str, Any],
    summary: dict[str, Any],
    engine_cases: dict[str, Any],
    manifest_digest: str,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    if baseline.get("kind") != "repository_measured_baseline":
        raise ValueError("regression baseline must be repository-measured")
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported baseline schema version")
    if baseline.get("manifest_sha256") != manifest_digest:
        raise ValueError(
            "benchmark manifest differs from baseline; establish a new baseline "
            "instead of comparing non-equivalent protocols"
        )

    _, total, engine_rate = engine_success(engine_cases)
    if total != baseline.get("case_count"):
        raise ValueError("current engine run case count differs from baseline")
    if summary.get("total_cases") != baseline.get("case_count"):
        raise ValueError("current evaluated case count differs from baseline")
    if engine_rate is None:
        raise ValueError("current engine run has no cases")

    baseline_metrics = baseline.get("metrics")
    if not isinstance(baseline_metrics, dict):
        raise ValueError("baseline metrics are missing")

    current_metrics = {
        "engine_execution_success_rate": engine_rate,
        "top1_rmsd_le_2a_rate": summary.get("top1_rmsd_le_2a_rate"),
        "combined_success_rate": summary.get("combined_success_rate"),
    }
    limits = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        limits.update(thresholds)

    checks = []
    for metric, allowed_drop in limits.items():
        base = baseline_metrics.get(metric)
        current = current_metrics.get(metric)
        if not isinstance(base, (int, float)) or isinstance(base, bool):
            raise ValueError(f"baseline metric unavailable: {metric}")
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise ValueError(f"current metric unavailable: {metric}")
        delta = float(current) - float(base)
        checks.append(
            RegressionCheck(
                metric=metric,
                baseline=float(base),
                current=float(current),
                delta=delta,
                allowed_drop=allowed_drop,
                passed=delta >= -allowed_drop,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_source_commit": baseline.get("source_commit"),
        "manifest_sha256": manifest_digest,
        "passed": all(check.passed for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--summary", type=Path, required=True)
    record.add_argument("--engine-cases", type=Path, required=True)
    record.add_argument("--manifest", type=Path, required=True)
    record.add_argument("--source-commit", required=True)
    record.add_argument("--output", type=Path, required=True)

    check = subparsers.add_parser("compare")
    check.add_argument("--baseline", type=Path, required=True)
    check.add_argument("--summary", type=Path, required=True)
    check.add_argument("--engine-cases", type=Path, required=True)
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    manifest = _load_object(args.manifest)
    digest = manifest_sha256(args.manifest)

    if args.command == "record":
        payload = build_baseline(
            summary=_load_object(args.summary),
            engine_cases=_load_object(args.engine_cases),
            manifest=manifest,
            manifest_digest=digest,
            source_commit=args.source_commit,
        )
        _write(args.output, payload)
        print(args.output)
        return 0

    result = compare(
        baseline=_load_object(args.baseline),
        summary=_load_object(args.summary),
        engine_cases=_load_object(args.engine_cases),
        manifest_digest=digest,
    )
    _write(args.output, result)
    print(args.output)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
