from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from benchmarks.failure_taxonomy import classify_preparation_error


@dataclass(frozen=True, slots=True)
class CanaryOutcome:
    case_id: str
    family: str
    baseline_completed: bool
    treatment_completed: bool
    baseline_rmsd: float | None = None
    treatment_rmsd: float | None = None
    baseline_pb_valid: bool | None = None
    treatment_pb_valid: bool | None = None


def promotion_summary(rows: Iterable[CanaryOutcome]) -> dict[str, object]:
    outcomes = tuple(rows)
    if not outcomes:
        raise ValueError("at least one canary outcome is required")

    recovered = tuple(
        row for row in outcomes
        if not row.baseline_completed and row.treatment_completed
    )
    regressions = tuple(
        row for row in outcomes
        if row.baseline_completed and not row.treatment_completed
    )
    comparable = tuple(
        row for row in outcomes
        if row.baseline_completed and row.treatment_completed
    )
    rmsd_regressions = tuple(
        row for row in comparable
        if row.baseline_rmsd is not None
        and row.treatment_rmsd is not None
        and row.treatment_rmsd > row.baseline_rmsd + 0.5
    )
    pb_regressions = tuple(
        row for row in comparable
        if row.baseline_pb_valid is True and row.treatment_pb_valid is False
    )

    return {
        "cases": len(outcomes),
        "preparation_recoveries": len(recovered),
        "execution_regressions": len(regressions),
        "rmsd_regressions_gt_0_5a": len(rmsd_regressions),
        "pb_valid_regressions": len(pb_regressions),
        "promotion_eligible": (
            bool(recovered)
            and not regressions
            and not rmsd_regressions
            and not pb_regressions
        ),
        "recovered_case_ids": [row.case_id for row in recovered],
        "regressed_case_ids": sorted({
            row.case_id
            for row in (*regressions, *rmsd_regressions, *pb_regressions)
        }),
    }


def cohort_case_ids(
    engine_rows: Iterable[dict[str, object]],
    *,
    residue_names: frozenset[str] = frozenset(),
    failure_classes: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    selected: set[str] = set()
    for row in engine_rows:
        if row.get("completed") is True:
            continue
        evidence = row.get("preparation_evidence")
        decisions = (
            evidence.get("decisions", [])
            if isinstance(evidence, dict)
            else []
        )
        observed = {
            str(item.get("residue", {}).get("residue_name", "")).upper()
            for item in decisions
            if isinstance(item, dict) and isinstance(item.get("residue"), dict)
        }
        explicit_failure_class = row.get("preparation_failure_class")
        failure_class = (
            str(explicit_failure_class)
            if explicit_failure_class
            else classify_preparation_error(
                str(row["error"]) if row.get("error") is not None else None
            )
        )
        if observed.intersection(residue_names) or failure_class in failure_classes:
            selected.add(str(row["case_id"]))
    return tuple(sorted(selected))
