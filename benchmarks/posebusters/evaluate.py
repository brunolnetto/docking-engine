from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BENCHMARKS = HERE.parent
sys.path.insert(0, str(BENCHMARKS))

from common import CaseResult, summarize, write_summary  # noqa: E402


def _pick(column_names: list[str], *needles: str) -> str | None:
    lowered = {
        name: name.lower().replace("å", "a").replace("≤", "<=")
        for name in column_names
    }
    for name, normalized in lowered.items():
        if all(needle in normalized for needle in needles):
            return name
    return None


def load_posebusters_csv(path: Path) -> tuple[CaseResult, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return ()

    fields = list(rows[0])
    rmsd_field = _pick(fields, "rmsd")
    if rmsd_field is None:
        raise RuntimeError("PoseBusters CSV does not expose an RMSD column")

    validity_fields = [
        name
        for name in fields
        if name not in {
            "file",
            "molecule",
            "position",
            rmsd_field,
        }
        and rows[0].get(name, "").strip().lower()
        in {"true", "false", "0", "1"}
    ]

    results = []
    for row in rows:
        case_id = Path(row.get("file") or "unknown").stem
        raw_rmsd = row.get(rmsd_field, "")
        try:
            rmsd = float(raw_rmsd)
        except (TypeError, ValueError):
            rmsd = None
        pb_valid = (
            all(
                row.get(field, "").strip().lower()
                in {"true", "1"}
                for field in validity_fields
            )
            if validity_fields
            else None
        )
        results.append(
            CaseResult(
                case_id=case_id,
                completed=rmsd is not None,
                rmsd_angstrom=rmsd,
                pb_valid=pb_valid,
                failure_stage=None if rmsd is not None else "evaluation",
            )
        )
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posebusters-csv", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    results = load_posebusters_csv(args.posebusters_csv)
    summary = summarize("posebusters_benchmark_v1", results)
    write_summary(args.summary, summary)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
