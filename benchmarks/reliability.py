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
        "evaluation_failure": [],
        "preparation_failure": [],
        "other_engine_failure": [],
    }
    preparation_reasons: Counter[str] = Counter()

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
        elif rmsds[0] is not None and float(rmsds[0]) <= 2.0:
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
            cohorts[
                "sampling_failure_top9"
                if conclusive
                else "incomplete_top9_evidence"
            ].append(case_id)

    counts = {name: len(case_ids) for name, case_ids in cohorts.items()}
    return {
        "counts": counts,
        "preparation_failure_reasons": dict(sorted(preparation_reasons.items())),\n        "ranking_diagnostics": sorted(ranking_cases, key=lambda row: str(row["case_id"])),
        "cohorts": {name: sorted(case_ids) for name, case_ids in cohorts.items()},
    }
