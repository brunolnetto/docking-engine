from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    completed: bool
    rmsd_angstrom: float | None = None
    pb_valid: bool | None = None
    runtime_seconds: float | None = None
    failure_stage: str | None = None
    error: str | None = None

    @property
    def rmsd_success(self) -> bool:
        return self.rmsd_angstrom is not None and self.rmsd_angstrom <= 2.0

    @property
    def combined_success(self) -> bool:
        return self.rmsd_success and self.pb_valid is True


@dataclass(frozen=True)
class BenchmarkSummary:
    benchmark: str
    total_cases: int
    completed_cases: int
    execution_success_rate: float
    top1_rmsd_le_2a_rate: float
    pb_valid_rate: float
    combined_success_rate: float
    median_rmsd_angstrom: float | None
    median_runtime_seconds: float | None
    failures_by_stage: dict[str, int]
    rmsd_evaluable_cases: int = 0
    pb_evaluable_cases: int = 0
    combined_evaluable_cases: int = 0
    engine_completed_cases: int | None = None
    engine_execution_success_rate: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize(
    benchmark: str,
    results: Iterable[CaseResult],
) -> BenchmarkSummary:
    rows = tuple(results)
    completed = tuple(row for row in rows if row.completed)
    rmsd_rows = tuple(
        row for row in completed if row.rmsd_angstrom is not None
    )
    pb_rows = tuple(row for row in completed if row.pb_valid is not None)
    combined_rows = tuple(
        row for row in completed
        if row.rmsd_angstrom is not None and row.pb_valid is not None
    )

    failures: dict[str, int] = {}
    for row in rows:
        if row.completed:
            continue
        stage = row.failure_stage or "unknown"
        failures[stage] = failures.get(stage, 0) + 1

    runtimes = [
        row.runtime_seconds
        for row in completed
        if row.runtime_seconds is not None
    ]
    rmsds = [row.rmsd_angstrom for row in rmsd_rows]

    return BenchmarkSummary(
        benchmark=benchmark,
        total_cases=len(rows),
        completed_cases=len(completed),
        execution_success_rate=(
            len(completed) / len(rows) if rows else 0.0
        ),
        top1_rmsd_le_2a_rate=(
            sum(row.rmsd_success for row in rmsd_rows) / len(rmsd_rows)
            if rmsd_rows
            else 0.0
        ),
        pb_valid_rate=(
            sum(row.pb_valid is True for row in pb_rows) / len(pb_rows)
            if pb_rows
            else 0.0
        ),
        combined_success_rate=(
            sum(row.combined_success for row in combined_rows) / len(combined_rows)
            if combined_rows
            else 0.0
        ),
        median_rmsd_angstrom=median(rmsds) if rmsds else None,
        median_runtime_seconds=median(runtimes) if runtimes else None,
        failures_by_stage=dict(sorted(failures.items())),
        rmsd_evaluable_cases=len(rmsd_rows),
        pb_evaluable_cases=len(pb_rows),
        combined_evaluable_cases=len(combined_rows),
    )


def load_case_results(path: Path) -> tuple[CaseResult, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["cases"] if isinstance(payload, dict) else payload
    return tuple(CaseResult(**row) for row in rows)


def write_summary(path: Path, summary: BenchmarkSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
