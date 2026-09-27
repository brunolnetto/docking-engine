from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.redocking import RedockingHarnessConfig, run_dataset  # noqa: E402


CASE_IDS_PATH = HERE / "posebusters_pdb_ccd_ids.txt"


def load_case_ids(path: Path = CASE_IDS_PATH) -> frozenset[str]:
    identifiers = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    unique = frozenset(identifiers)
    if len(identifiers) != 308 or len(unique) != 308:
        raise RuntimeError(
            "PoseBusters journal subset identifier file must contain "
            "exactly 308 unique case IDs"
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
    args = parser.parse_args()

    path = run_dataset(
        dataset_root=args.dataset_root,
        output_root=args.output_root,
        config=CONFIG,
        limit=args.limit,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
