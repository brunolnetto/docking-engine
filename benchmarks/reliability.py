from __future__ import annotations

from collections import Counter
import re
from typing import Any


def preparation_failure_reason(error: str | None) -> str | None:
    if not error:
        return None
    patterns = (
        (r"Failed building template from CCD for resname='HEM'", "ccd_template:HEM"),
        (r"Failed building template from CCD for resname='K'", "ccd_template:K"),
        (r"Failed building template from CCD for resname='CO'", "ccd_template:CO"),
        (r"Failed building template from CCD for resname='([^']+)'", "ccd_template:other"),
        (r"No template matched", "residue_template_mismatch"),
        (r"tied for fewest missing and excess H", "protonation_ambiguity"),
        (r"Explicit valence", "chemical_valence"),
        (r"unable to build rdkit mol", "rdkit_residue_build"),
    )
    for pattern, label in patterns:
        if re.search(pattern, error, flags=re.IGNORECASE):
            return label
    return "other_preparation"


def ranking_diagnostics(row: dict[str, Any]) -> dict[str, object] | None:
    rmsds = row.get("pose_rmsd_angstroms")
    if not isinstance(rmsds, list) or not rmsds:
        return None
    ranked = [
        (rank, float(value))
        for rank, value in enumerate(rmsds, start=1)
        if value is not None
    ]
    if not ranked:
        return None
    best_rank, best_rmsd = min(ranked, key=lambda item: item[1])
    top1 = float(rmsds[0]) if rmsds[0] is not None else None
    return {
        "case_id": str(row["case_id"]),
        "top1_rmsd_angstrom": top1,
        "best_rmsd_angstrom": best_rmsd,
        "best_pose_rank": best_rank,
        "top1_regret_angstrom": None if top1 is None else top1 - best_rmsd,
    }


def reliability_cohorts(
    engine_rows: list[dict[str, Any]],
    evaluated_rows: list[dict[str, Any]],
) -> dict[str, object]:
    engine_by_id = {str(row["case_id"]): row for row in engine_rows}
    cohorts: dict[str, list[str]] = {
        "top1_hit": [],
        "ranking_recoverable_top3": [],
        "ranking_recoverable_top9": [],
        "sampling_failure_top9": [],
        "incomplete_top9_evidence": [],
        "evaluation_failure": [],
        "preparation_failure": [],
        "other_engine_failure": [],
    }
    preparation_reasons: Counter[str] = Counter()
    ranking_cases: list[dict[str, object]] = []

    for case_id, engine in engine_by_id.items():
        if engine.get("completed") is True:
            continue
        stage = engine.get("failure_stage")
        if stage == "preparation":
            cohorts["preparation_failure"].append(case_id)
            reason = preparation_failure_reason(str(engine.get("error") or ""))
            if reason:
                preparation_reasons[reason] += 1
        else:
            cohorts["other_engine_failure"].append(case_id)

    for row in evaluated_rows:
        case_id = str(row["case_id"])
        if row.get("completed") is not True:
            if engine_by_id.get(case_id, {}).get("completed") is True:
                cohorts["evaluation_failure"].append(case_id)
            continue
        rmsds = row.get("pose_rmsd_angstroms")
        if not isinstance(rmsds, list) or not rmsds:
            cohorts["evaluation_failure"].append(case_id)
            continue
        valid = [float(value) for value in rmsds if value is not None]
        if not valid:
            cohorts["evaluation_failure"].append(case_id)
            continue

        diagnostic = ranking_diagnostics(row)
        if diagnostic is not None and diagnostic["best_pose_rank"] != 1:
            ranking_cases.append(diagnostic)

        if rmsds[0] is not None and float(rmsds[0]) <= 2.0:
            cohorts["top1_hit"].append(case_id)
        elif any(value is not None and float(value) <= 2.0 for value in rmsds[1:3]):
            cohorts["ranking_recoverable_top3"].append(case_id)
        elif any(value is not None and float(value) <= 2.0 for value in rmsds[3:9]):
            cohorts["ranking_recoverable_top9"].append(case_id)
        else:
            limit = row.get("pose_evaluation_limit")
            conclusive = (
                isinstance(limit, int)
                and not isinstance(limit, bool)
                and limit >= 9
                and len(rmsds) >= 9
                and all(value is not None for value in rmsds[:9])
            )
            cohort = (
                "sampling_failure_top9"
                if conclusive
                else "incomplete_top9_evidence"
            )
            cohorts[cohort].append(case_id)

    counts = {name: len(case_ids) for name, case_ids in cohorts.items()}
    return {
        "counts": counts,
        "preparation_failure_reasons": dict(sorted(preparation_reasons.items())),
        "ranking_diagnostics": sorted(
            ranking_cases,
            key=lambda row: str(row["case_id"]),
        ),
        "cohorts": {name: sorted(case_ids) for name, case_ids in cohorts.items()},
    }
