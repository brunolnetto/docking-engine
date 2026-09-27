from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.redocking import RedockingHarnessConfig, run_dataset  # noqa: E402


CASE_IDS_PATH = HERE / "posebusters_pdb_ccd_ids.txt"


def load_case_ids(
    path: Path = CASE_IDS_PATH,
    *,
    expected_count: int | None = 308,
) -> frozenset[str]:
    identifiers = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    unique = frozenset(identifiers)
    if len(unique) != len(identifiers):
        raise RuntimeError("PoseBusters case identifier file contains duplicates")
    if expected_count is not None and len(unique) != expected_count:
        raise RuntimeError(
            "PoseBusters case identifier file must contain exactly "
            f"{expected_count} unique case IDs"
        )
    return unique


CONFIG = RedockingHarnessConfig(
    benchmark="PoseBusters",
    expected_case_count=308,
    run_prefix="posebusters",
    worker_id="posebusters-benchmark",
    allowed_case_ids=load_case_ids(),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case-ids-file", type=Path)
    args = parser.parse_args()

    config = CONFIG
    if args.case_ids_file is not None:
        from dataclasses import replace

        config = replace(
            CONFIG,
            allowed_case_ids=load_case_ids(
                args.case_ids_file,
                expected_count=None,
            ),
        )

    path = run_dataset(
        dataset_root=args.dataset_root,
        output_root=args.output_root,
        config=config,
        limit=args.limit,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
