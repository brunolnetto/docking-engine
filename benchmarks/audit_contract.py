from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any


SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a cases list")
    return rows


def coverage_contract(
    *,
    engine_cases: Path,
    evaluated_cases: Path,
    interaction_cases: Path,
    expected_cases: int,
) -> dict[str, object]:
    engine = _cases(engine_cases)
    evaluated = _cases(evaluated_cases)
    interactions = _cases(interaction_cases)
    for name, rows in (
        ("engine", engine),
        ("evaluation", evaluated),
        ("interaction", interactions),
    ):
        if len(rows) != expected_cases:
            raise ValueError(
                f"{name} case count mismatch: expected {expected_cases}, got {len(rows)}"
            )

    engine_completed = sum(row.get("completed") is True for row in engine)
    rmsd_evaluable = sum(
        row.get("completed") is True and row.get("rmsd_angstrom") is not None
        for row in evaluated
    )
    pb_evaluable = sum(
        row.get("completed") is True and row.get("pb_valid") is not None
        for row in evaluated
    )
    interaction_evaluable = sum(
        row.get("completed") is True for row in interactions
    )
    axes = {
        "dataset_accounted": expected_cases,
        "engine_completed": engine_completed,
        "rmsd_evaluable": rmsd_evaluable,
        "pb_evaluable": pb_evaluable,
        "interaction_evaluable": interaction_evaluable,
    }
    return {
        "expected_cases": expected_cases,
        "axes": {
            key: {
                "cases": value,
                "denominator": expected_cases,
                "rate": value / expected_cases if expected_cases else None,
                "complete": value == expected_cases,
            }
            for key, value in axes.items()
        },
        "fully_evaluable": all(
            value == expected_cases
            for key, value in axes.items()
            if key != "dataset_accounted"
        ),
    }


def provenance(
    *,
    source_commit: str,
    workflow_run_id: str | None,
    manifest: Path,
    artifacts: list[Path],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "manifest_sha256": sha256_file(manifest),
        "artifacts": {
            path.name: sha256_file(path)
            for path in sorted(artifacts, key=lambda item: item.name)
        },
    }
