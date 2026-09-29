from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    pose_rmsd_angstroms: tuple[float | None, ...] = ()
    pose_pb_valid: tuple[bool | None, ...] = ()
    pose_evaluation_limit: int = 1
    pb_checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ranked_rmsds(self) -> tuple[float | None, ...]:
        if self.pose_rmsd_angstroms:
            return tuple(self.pose_rmsd_angstroms)
        if self.rmsd_angstrom is not None:
            return (self.rmsd_angstrom,)
        return ()

    def top_n_rmsd_success(self, n: int) -> bool | None:
        if n < 1:
            raise ValueError("top-N must be >= 1")
        evidence = self.ranked_rmsds[:n]
        if any(rmsd is not None and rmsd <= 2.0 for rmsd in evidence):
            return True
        if self.pose_evaluation_limit < n:
            return None
        if any(rmsd is None for rmsd in evidence):
            return None
        return False

    @property
    def rmsd_success(self) -> bool:
        return self.top_n_rmsd_success(1) is True

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
    topn_rmsd_le_2a_rates: dict[str, float] = field(default_factory=dict)
    topn_evaluable_cases: dict[str, int] = field(default_factory=dict)
    pb_failures_by_check: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize(
    benchmark: str,
    results: Iterable[CaseResult],
    *,
    top_n_values: tuple[int, ...] = (1, 3, 5, 9),
) -> BenchmarkSummary:
    rows = tuple(results)
    completed = tuple(row for row in rows if row.completed)
    rmsd_rows = tuple(
        row for row in completed
        if row.top_n_rmsd_success(1) is not None
    )
    pb_rows = tuple(row for row in completed if row.pb_valid is not None)
    combined_rows = tuple(
        row
        for row in completed
        if row.top_n_rmsd_success(1) is not None
        and row.pb_valid is not None
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
    rmsds = [
        row.ranked_rmsds[0]
        for row in rmsd_rows
        if row.ranked_rmsds and row.ranked_rmsds[0] is not None
    ]

    topn_evidence = {
        n: tuple(
            result
            for row in completed
            if (result := row.top_n_rmsd_success(n)) is not None
        )
        for n in top_n_values
    }
    topn_rates = {
        str(n): (
            sum(results) / len(results)
            if results
            else 0.0
        )
        for n, results in topn_evidence.items()
    }
    topn_counts = {
        str(n): len(results)
        for n, results in topn_evidence.items()
    }
    pb_failures: dict[str, int] = {}
    for row in pb_rows:
        for check, passed in row.pb_checks.items():
            if passed is False:
                pb_failures[check] = pb_failures.get(check, 0) + 1

    return BenchmarkSummary(
        benchmark=benchmark,
        total_cases=len(rows),
        completed_cases=len(completed),
        execution_success_rate=(len(completed) / len(rows) if rows else 0.0),
        top1_rmsd_le_2a_rate=topn_rates.get("1", 0.0),
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
        topn_rmsd_le_2a_rates=topn_rates,
        topn_evaluable_cases=topn_counts,
        pb_failures_by_check=dict(sorted(pb_failures.items())),
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
