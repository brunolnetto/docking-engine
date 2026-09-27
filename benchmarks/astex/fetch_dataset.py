from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.posebusters.fetch_dataset import main as fetch_posebusters_archive  # noqa: E402


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

    original_argv = sys.argv
    try:
        sys.argv = [
            str(HERE / "fetch_dataset.py"),
            "--destination",
            str(args.destination),
        ]
        if args.keep_archive:
            sys.argv.append("--keep-archive")
        fetch_posebusters_archive()
    finally:
        sys.argv = original_argv

    root = find_astex_root(args.destination.resolve())
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
