from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.posebusters.fetch_dataset import fetch_and_extract  # noqa: E402


def find_astex_root(destination: Path) -> Path:
    matches = sorted(
        path
        for path in destination.rglob("astex_diverse_set")
        if path.is_dir()
    )
    if len(matches) != 1:
        raise RuntimeError(
            "expected exactly one astex_diverse_set directory after extraction; "
            f"found {len(matches)}"
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args()

    destination = fetch_and_extract(
        args.destination,
        keep_archive=args.keep_archive,
    )
    root = find_astex_root(destination)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
