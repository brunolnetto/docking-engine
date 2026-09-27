from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
POSEBUSTERS = HERE.parent / "posebusters"


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
    interaction_cases = args.output_root / "interaction_cases.json"
    interaction_summary = args.output_root / "interaction_summary.json"

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
            str(POSEBUSTERS / "evaluate_engine.py"),
            "--engine-cases",
            str(engine_cases),
            "--output",
            str(evaluated_cases),
            "--summary",
            str(summary),
            "--benchmark",
            "astex_diverse_v1",
            "--top-n",
            "9",
        ]
    )
    run(
        [
            sys.executable,
            str(POSEBUSTERS / "report.py"),
            "--engine-cases",
            str(engine_cases),
            "--evaluated-cases",
            str(evaluated_cases),
            "--manifest",
            str(HERE / "manifest.json"),
            "--output",
            str(report),
        ]
    )
    run(
        [
            sys.executable,
            str(HERE.parent / "evaluate_interactions.py"),
            "--engine-cases",
            str(engine_cases),
            "--output",
            str(interaction_cases),
            "--summary",
            str(interaction_summary),
        ]
    )
    print(summary)
    print(report)
    print(interaction_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
