from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.redocking import RedockingHarnessConfig, run_dataset  # noqa: E402


CONFIG = RedockingHarnessConfig(
    benchmark="Astex Diverse",
    expected_case_count=85,
    run_prefix="astex",
    worker_id="astex-benchmark",
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
