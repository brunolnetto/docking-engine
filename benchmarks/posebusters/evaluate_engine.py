from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.common import (  # noqa: E402
    CaseResult,
    summarize,
    write_summary,
)


def _column_name(value: object) -> str:
    if isinstance(value, tuple):
        return " ".join(str(part) for part in value if part)
    return str(value)


def _find_rmsd_numeric(row) -> float | None:
    for key, value in row.items():
        name = _column_name(key).lower().replace("å", "a")
        if "rmsd" not in name:
            continue
        if _boolean_value(value) is not None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _boolean_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    value_type = type(value)
    if (
        value_type.__module__.startswith("numpy")
        and value_type.__name__ in {"bool", "bool_"}
    ):
        return bool(value)
    return None


def _physical_validity(binary_row) -> bool:
    checks = []
    for key, value in binary_row.items():
        name = _column_name(key).lower().replace("å", "a")
        if "rmsd" in name:
            continue
        normalized = _boolean_value(value)
        if normalized is not None:
            checks.append(normalized)
    if not checks:
        raise RuntimeError(
            "PoseBusters returned no physical-validity boolean checks"
        )
    return all(checks)


def evaluate_completed_case(row: dict[str, object]) -> CaseResult:
    try:
        from posebusters import PoseBusters
    except ImportError as exc:
        raise RuntimeError(
            "PoseBusters import failed after benchmark installation: "
            f"{type(exc).__name__}: {exc}. "
            "Install with python -m pip install -e '.[benchmark]'."
        ) from exc

    predicted = Path(str(row["predicted_sdf"]))
    crystal = Path(str(row["crystal_ligand_sdf"]))
    receptor = Path(str(row["receptor_pdb"]))
    buster = PoseBusters(config="redock", top_n=1, max_workers=0)

    full = buster.bust(
        predicted,
        crystal,
        receptor,
        full_report=True,
    )
    if full.empty:
        raise RuntimeError("PoseBusters returned an empty report")

    full_row = full.iloc[0]
    rmsd = _find_rmsd_numeric(full_row)
    if rmsd is None:
        raise RuntimeError(
            "PoseBusters full report did not expose numeric RMSD"
        )

    return CaseResult(
        case_id=str(row["case_id"]),
        completed=True,
        rmsd_angstrom=rmsd,
        pb_valid=_physical_validity(full_row),
        runtime_seconds=(
            float(row["runtime_seconds"])
            if row.get("runtime_seconds") is not None
            else None
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.engine_cases.read_text(encoding="utf-8"))
    results = []
    for row in payload["cases"]:
        if not row.get("completed"):
            results.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    completed=False,
                    runtime_seconds=row.get("runtime_seconds"),
                    failure_stage=str(
                        row.get("failure_stage") or "engine"
                    ),
                    error=(
                        str(row["error"])
                        if row.get("error") is not None
                        else None
                    ),
                )
            )
            continue
        try:
            results.append(evaluate_completed_case(row))
        except Exception as exc:
            results.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    completed=False,
                    runtime_seconds=row.get("runtime_seconds"),
                    failure_stage="evaluation",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"cases": [result.__dict__ for result in results]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = summarize("posebusters_benchmark_v1", results)
    write_summary(args.summary, summary)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
