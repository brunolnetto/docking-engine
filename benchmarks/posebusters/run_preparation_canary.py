from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any

from benchmarks.posebusters.evaluate_engine import evaluate_completed_case
from benchmarks.posebusters.preparation_canary import CanaryOutcome, promotion_summary
from benchmarks.redocking import RedockingHarnessConfig, run_dataset


ALLOWED_TREATMENT_FIELDS = frozenset({
    "receptor_delete_bad_res",
    "receptor_default_altloc",
    "receptor_forgive_extra_bonds",
    "receptor_wanted_altloc",
    "receptor_set_template",
    "receptor_delete_residues",
})


def load_treatment(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("treatment must be a JSON object")
    unknown = set(payload) - ALLOWED_TREATMENT_FIELDS
    if unknown:
        raise ValueError(f"unsupported treatment fields: {sorted(unknown)}")
    boolean_fields = {
        "receptor_delete_bad_res",
        "receptor_forgive_extra_bonds",
    }
    string_fields = ALLOWED_TREATMENT_FIELDS - boolean_fields
    invalid = {
        key: value
        for key, value in payload.items()
        if (
            key in boolean_fields
            and not isinstance(value, bool)
        )
        or (
            key in string_fields
            and value is not None
            and not isinstance(value, str)
        )
    }
    if invalid:
        raise ValueError(
            "treatment field types are invalid: "
            + ", ".join(f"{key}={value!r}" for key, value in sorted(invalid.items()))
        )
    return payload


def evaluate_rows(
    rows: list[dict[str, object]],
    *,
    evaluator=evaluate_completed_case,
) -> list[dict[str, object]]:
    evaluated: list[dict[str, object]] = []
    for row in rows:
        merged = dict(row)
        if row.get("completed") is not True:
            merged["scientific_evaluation_completed"] = False
            merged["scientific_evaluation_error"] = None
            merged["rmsd_angstrom"] = None
            merged["pb_valid"] = None
            evaluated.append(merged)
            continue
        try:
            result, pose_evidence = evaluator(row)
        except Exception as exc:
            merged["scientific_evaluation_completed"] = False
            merged["scientific_evaluation_error"] = f"{type(exc).__name__}: {exc}"
            merged["rmsd_angstrom"] = None
            merged["pb_valid"] = None
            evaluated.append(merged)
            continue
        merged["scientific_evaluation_completed"] = True
        merged["scientific_evaluation_error"] = None
        merged["rmsd_angstrom"] = result.rmsd_angstrom
        merged["pb_valid"] = result.pb_valid
        merged["pose_rmsd_angstroms"] = list(result.pose_rmsd_angstroms or ())
        merged["pose_pb_valid"] = list(result.pose_pb_valid or ())
        merged["pose_evidence"] = pose_evidence
        evaluated.append(merged)
    return evaluated


def write_evaluated_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cases": rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def paired_outcomes(
    baseline_rows: list[dict[str, object]],
    treatment_rows: list[dict[str, object]],
    *,
    family: str,
) -> list[CanaryOutcome]:
    baseline = {str(row["case_id"]): row for row in baseline_rows}
    treatment = {str(row["case_id"]): row for row in treatment_rows}
    if set(baseline) != set(treatment):
        raise ValueError("baseline/treatment case sets differ")
    rows = []
    for case_id in sorted(baseline):
        before, after = baseline[case_id], treatment[case_id]
        rows.append(CanaryOutcome(
            case_id=case_id,
            family=family,
            baseline_completed=before.get("completed") is True,
            treatment_completed=after.get("completed") is True,
            baseline_rmsd=_optional_float(before.get("rmsd_angstrom")),
            treatment_rmsd=_optional_float(after.get("rmsd_angstrom")),
            baseline_pb_valid=_optional_bool(before.get("pb_valid")),
            treatment_pb_valid=_optional_bool(after.get("pb_valid")),
        ))
    return rows


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _cases(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} must contain a cases list")
    return rows


def serializable_config(config: RedockingHarnessConfig) -> dict[str, object]:
    payload = asdict(config)
    case_ids = payload.get("allowed_case_ids")
    if isinstance(case_ids, (set, frozenset)):
        payload["allowed_case_ids"] = sorted(case_ids)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--case-id", action="append", required=True)
    args = parser.parse_args()

    treatment = load_treatment(args.treatment)
    case_ids = frozenset(args.case_id)
    common = RedockingHarnessConfig(
        benchmark="posebusters-canary",
        expected_case_count=len(case_ids),
        run_prefix="canary-baseline",
        worker_id="preparation-canary",
        allowed_case_ids=case_ids,
        add_ligand_hydrogens=True,
        receptor_delete_bad_res=True,
        receptor_default_altloc="A",
        receptor_forgive_extra_bonds=True,
    )
    baseline_root = args.output_root / "baseline"
    treatment_root = args.output_root / "treatment"
    baseline_path = run_dataset(
        dataset_root=args.dataset_root,
        output_root=baseline_root,
        config=common,
    )
    treated = replace(
        common,
        run_prefix="canary-treatment",
        **treatment,
    )
    treatment_path = run_dataset(
        dataset_root=args.dataset_root,
        output_root=treatment_root,
        config=treated,
    )

    baseline_rows = evaluate_rows(_cases(baseline_path))
    treatment_rows = evaluate_rows(_cases(treatment_path))
    write_evaluated_rows(baseline_root / "evaluated_cases.json", baseline_rows)
    write_evaluated_rows(treatment_root / "evaluated_cases.json", treatment_rows)

    outcomes = paired_outcomes(
        baseline_rows,
        treatment_rows,
        family=args.family,
    )
    summary = promotion_summary(outcomes)
    payload = {
        "family": args.family,
        "case_ids": sorted(case_ids),
        "baseline_config": serializable_config(common),
        "treatment": treatment,
        "treatment_config": serializable_config(treated),
        "outcomes": [asdict(row) for row in outcomes],
        "summary": summary,
        "scientific_evaluation_required": False,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "canary_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
