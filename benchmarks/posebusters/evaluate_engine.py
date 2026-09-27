from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BENCHMARKS = HERE.parent
sys.path.insert(0, str(BENCHMARKS))

from common import CaseResult, summarize, write_summary  # noqa: E402


def _column_name(value: object) -> str:
    if isinstance(value, tuple):
        return " ".join(str(part) for part in value if part)
    return str(value)


def _find_rmsd_numeric(row) -> float | None:
    for key, value in row.items():
        name = _column_name(key).lower().replace("å", "a")
        if "rmsd" not in name:
            continue
        if isinstance(value, bool):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _physical_validity(binary_row) -> bool:
    checks = []
    for key, value in binary_row.items():
        name = _column_name(key).lower().replace("å", "a")
        if "rmsd" in name:
            continue
        if isinstance(value, bool):
            checks.append(value)
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
            "PoseBusters evaluation requires the benchmark extra: "
            "python -m pip install -e '.[benchmark]'"
        ) from exc

    predicted = Path(str(row["predicted_sdf"]))
    crystal = Path(str(row["crystal_ligand_sdf"]))
    receptor = Path(str(row["receptor_pdb"]))
    buster = PoseBusters(config="redock", top_n=1, max_workers=0)

    binary = buster.bust(
        predicted,
        crystal,
        receptor,
        full_report=False,
    )
    full = buster.bust(
        predicted,
        crystal,
        receptor,
        full_report=True,
    )
    if binary.empty or full.empty:
        raise RuntimeError("PoseBusters returned an empty report")

    binary_row = binary.iloc[0]
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
        pb_valid=_physical_validity(binary_row),
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
