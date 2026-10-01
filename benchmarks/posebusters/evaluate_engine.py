from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.common import (  # noqa: E402
    CaseResult,
    summarize,
    write_summary,
)
from benchmarks.ranking_signals import vina_pose_scores  # noqa: E402


def _column_name(value: object) -> str:
    if isinstance(value, tuple):
        return " ".join(str(part) for part in value if part)
    return str(value)


def _find_rmsd_numeric(row) -> float | None:
    for key, value in row.items():
        name = _column_name(key).lower().replace("å", "a")
        if "rmsd" not in name:
            continue
        if _boolean_value(value) is not None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _boolean_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    value_type = type(value)
    if (
        value_type.__module__.startswith("numpy")
        and value_type.__name__ in {"bool", "bool_"}
    ):
        return bool(value)
    return None


def _physical_checks(binary_row) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for key, value in binary_row.items():
        name = _column_name(key)
        if "rmsd" in name.lower().replace("å", "a"):
            continue
        normalized = _boolean_value(value)
        if normalized is not None:
            checks[name] = normalized
    if not checks:
        raise RuntimeError(
            "PoseBusters returned no physical-validity boolean checks"
        )
    return checks


def _physical_validity(binary_row) -> bool:
    return all(_physical_checks(binary_row).values())


def evaluate_pose_evidence(
    row: dict[str, object],
    *,
    pose_rmsds: list[float | None],
    pose_validity: list[bool | None],
) -> list[dict[str, object]]:
    predicted_pdbqt = row.get("predicted_pdbqt")
    if predicted_pdbqt is None:
        raise RuntimeError("engine case is missing predicted_pdbqt")
    signals = vina_pose_scores(Path(str(predicted_pdbqt)).read_bytes())
    if len(signals) != len(pose_rmsds):
        raise RuntimeError(
            "Vina and PoseBusters disagree on pose count: "
            f"{len(signals)} != {len(pose_rmsds)}"
        )
    if len(pose_validity) != len(pose_rmsds):
        raise RuntimeError(
            "PoseBusters validity and RMSD disagree on pose count: "
            f"{len(pose_validity)} != {len(pose_rmsds)}"
        )

    evidence: list[dict[str, object]] = []
    for expected_rank, (signal, rmsd, valid) in enumerate(
        zip(signals, pose_rmsds, pose_validity, strict=True),
        start=1,
    ):
        if signal["rank"] != expected_rank:
            raise RuntimeError(
                "Vina signal rank is not contiguous: "
                f"expected {expected_rank}, got {signal['rank']}"
            )
        item = dict(signal)
        item["reference_rmsd_angstrom"] = rmsd
        item["reference_success_le_2a"] = (
            bool(rmsd <= 2.0) if rmsd is not None else None
        )
        item["pb_valid"] = valid
        evidence.append(item)
    return evidence


def evaluate_completed_case(
    row: dict[str, object],
    *,
    top_n: int = 9,
) -> tuple[CaseResult, list[dict[str, object]]]:
    try:
        from posebusters import PoseBusters
    except ImportError as exc:
        raise RuntimeError(
            "PoseBusters import failed after benchmark installation: "
            f"{type(exc).__name__}: {exc}. "
            "Install with python -m pip install -e '.[benchmark]'."
        ) from exc

    predicted = Path(str(row["predicted_sdf"]))
    crystal = Path(str(row["crystal_ligand_sdf"]))
    receptor = Path(str(row["receptor_pdb"]))
    buster = PoseBusters(config="redock", top_n=top_n, max_workers=0)

    full = buster.bust(
        predicted,
        crystal,
        receptor,
        full_report=True,
    )
    binary = buster.bust(
        predicted,
        crystal,
        receptor,
        full_report=False,
    )
    if full.empty or binary.empty:
        raise RuntimeError("PoseBusters returned an empty report")
    if len(full) != len(binary):
        raise RuntimeError(
            "PoseBusters full and binary reports disagree on pose count: "
            f"{len(full)} != {len(binary)}"
        )

    pose_rmsds: list[float | None] = []
    pose_validity: list[bool | None] = []
    top1_checks: dict[str, bool] = {}
    for position, ((_, full_row), (_, binary_row)) in enumerate(
        zip(full.iterrows(), binary.iterrows(), strict=True),
        start=1,
    ):
        rmsd = _find_rmsd_numeric(full_row)
        if position == 1 and rmsd is None:
            raise RuntimeError(
                "PoseBusters full report did not expose numeric RMSD "
                "for ranked pose 1"
            )
        pose_rmsds.append(rmsd)
        try:
            checks = _physical_checks(binary_row)
            pose_validity.append(all(checks.values()))
            if position == 1:
                top1_checks = checks
        except RuntimeError:
            if position == 1:
                raise
            pose_validity.append(None)

    result = CaseResult(
        case_id=str(row["case_id"]),
        completed=True,
        rmsd_angstrom=pose_rmsds[0],
        pb_valid=pose_validity[0],
        runtime_seconds=(
            float(row["runtime_seconds"])
            if row.get("runtime_seconds") is not None
            else None
        ),
        pose_rmsd_angstroms=tuple(pose_rmsds),
        pose_pb_valid=tuple(pose_validity),
        pose_evaluation_limit=top_n,
        pb_checks=top1_checks,
    )
    evidence = evaluate_pose_evidence(
        row,
        pose_rmsds=pose_rmsds,
        pose_validity=pose_validity,
    )
    return result, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=9)
    parser.add_argument("--benchmark", default="posebusters_benchmark_v1")
    args = parser.parse_args()
    if args.top_n < 1:
        parser.error("--top-n must be >= 1")

    payload = json.loads(args.engine_cases.read_text(encoding="utf-8"))
    engine_rows = payload["cases"]
    engine_total = len(engine_rows)
    engine_completed = sum(
        row.get("completed") is True for row in engine_rows
    )
    engine_rate = engine_completed / engine_total if engine_total else None
    results = []
    pose_evidence: dict[str, list[dict[str, object]]] = {}
    for row in payload["cases"]:
        if not row.get("completed"):
            results.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    completed=False,
                    runtime_seconds=row.get("runtime_seconds"),
                    failure_stage=str(
                        row.get("failure_stage") or "engine"
                    ),
                    error=(
                        str(row["error"])
                        if row.get("error") is not None
                        else None
                    ),
                )
            )
            continue
        try:
            result, evidence = evaluate_completed_case(row, top_n=args.top_n)
            results.append(result)
            pose_evidence[str(row["case_id"])] = evidence
        except Exception as exc:
            results.append(
                CaseResult(
                    case_id=str(row["case_id"]),
                    completed=False,
                    runtime_seconds=row.get("runtime_seconds"),
                    failure_stage="evaluation",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "cases": [result.__dict__ for result in results],
                "pose_evidence": pose_evidence,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = replace(
        summarize(args.benchmark, results),
        engine_completed_cases=engine_completed,
        engine_execution_success_rate=engine_rate,
    )
    write_summary(args.summary, summary)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
