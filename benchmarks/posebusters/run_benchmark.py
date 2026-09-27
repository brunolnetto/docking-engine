from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    engine_cases = args.output_root / "engine_cases.json"
    evaluated_cases = args.output_root / "evaluated_cases.json"
    summary = args.output_root / "summary.json"
    report = args.output_root / "report.md"

    runner = [
        sys.executable,
        str(HERE / "runner.py"),
        "--dataset-root",
        str(args.dataset_root),
        "--output-root",
        str(args.output_root),
    ]
    if args.limit is not None:
        runner.extend(["--limit", str(args.limit)])
    run(runner)

    run(
        [
            sys.executable,
            str(HERE / "evaluate_engine.py"),
            "--engine-cases",
            str(engine_cases),
            "--output",
            str(evaluated_cases),
            "--summary",
            str(summary),
        ]
    )
    run(
        [
            sys.executable,
            str(HERE / "report.py"),
            "--evaluated-cases",
            str(evaluated_cases),
            "--manifest",
            str(HERE / "manifest.json"),
            "--baseline",
            str(HERE / "baselines" / "vina-paper.json"),
            "--output",
            str(report),
        ]
    )
    print(summary)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
