from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.interactions import (  # noqa: E402
    InteractionRecoveryMetrics,
    aggregate_metrics,
    compare_fingerprints,
    extract_pdbqt_fingerprint,
)
from moldock.preparation import (  # noqa: E402
    LigandPreparationProtocol,
    LigandPreparationRequest,
    MeekoLigandPreparer,
    MeekoReceptorPreparer,
    ReceptorPreparationProtocol,
    ReceptorPreparationRequest,
)


MEEKO_VERSION = "0.8.0"


def _prepare_reference(
    row: dict[str, object],
) -> tuple[bytes, bytes]:
    receptor_protocol = ReceptorPreparationProtocol(
        method="meeko",
        method_version=MEEKO_VERSION,
        parameters={},
    )
    ligand_protocol = LigandPreparationProtocol(
        method="meeko",
        method_version=MEEKO_VERSION,
        parameters={},
    )
    receptor_path = Path(str(row["receptor_pdb"]))
    ligand_path = Path(str(row["crystal_ligand_sdf"]))

    receptor = MeekoReceptorPreparer(
        method_version=MEEKO_VERSION
    ).prepare(
        ReceptorPreparationRequest(
            receptor_id=str(row["case_id"]),
            source_format="pdb",
            content=receptor_path.read_bytes(),
            protocol=receptor_protocol,
        )
    )
    ligands = MeekoLigandPreparer(
        method_version=MEEKO_VERSION
    ).prepare(
        LigandPreparationRequest(
            ligand_id=str(row["case_id"]),
            source_format="sdf",
            content=ligand_path.read_bytes(),
            protocol=ligand_protocol,
        )
    )
    if len(ligands) != 1:
        raise RuntimeError(
            "crystal reference preparation did not produce exactly one ligand"
        )
    return receptor.pdbqt, ligands[0].pdbqt


def evaluate_case(row: dict[str, object]) -> dict[str, object]:
    receptor_pdbqt, crystal_ligand_pdbqt = _prepare_reference(row)
    predicted_pdbqt = Path(str(row["predicted_pdbqt"])).read_bytes()

    reference = extract_pdbqt_fingerprint(
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=crystal_ligand_pdbqt,
    )
    predicted = extract_pdbqt_fingerprint(
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=predicted_pdbqt,
    )
    metrics = compare_fingerprints(reference, predicted)
    return {
        "case_id": str(row["case_id"]),
        "completed": True,
        "reference_fingerprint_size": len(reference),
        "predicted_fingerprint_size": len(predicted),
        "families": [metric.to_dict() for metric in metrics],
    }


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_report(summary: dict[str, object]) -> str:
    families = summary.get("families")
    if not isinstance(families, list):
        raise ValueError("interaction summary families must be a list")
    lines = [
        "# Interaction Recovery Benchmark",
        "",
        (
            "This benchmark compares residue-level interaction fingerprints "
            "between the prepared crystallographic ligand and the engine's "
            "Top-1 predicted pose."
        ),
        "",
        f"**Cases:** {summary.get('total_cases', 0)}",
        (
            "**Interaction-evaluable cases:** "
            f"{summary.get('interaction_evaluable_cases', 0)}"
        ),
        "",
        "| Family | Reference | Predicted | TP | FP | FN | Precision | Recall | F1 | Jaccard |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for family in families:
        if not isinstance(family, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(family.get("kind", "unknown")),
                    str(family.get("reference_count", 0)),
                    str(family.get("predicted_count", 0)),
                    str(family.get("true_positive", 0)),
                    str(family.get("false_positive", 0)),
                    str(family.get("false_negative", 0)),
                    _format_metric(family.get("precision")),
                    _format_metric(family.get("recall")),
                    _format_metric(family.get("f1")),
                    _format_metric(family.get("jaccard")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Semantics",
            "",
            "- Fingerprints are compared independently by interaction family.",
            "- The fingerprint unit is interaction family + receptor residue, not atom-pair count.",
            "- Empty reference/prediction families are reported as n/a rather than perfect recovery.",
            "- Salt bridges retain the engine's current putative-charge semantics.",
            "- These recurrence/recovery statistics are not molecular-dynamics occupancy.",
            "- No combined interaction confidence score is calculated.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.engine_cases.read_text(encoding="utf-8"))
    rows = payload.get("cases")
    if not isinstance(rows, list):
        raise ValueError("engine cases payload must contain a cases list")

    evaluated = []
    successful_metrics = []
    for row in rows:
        case_id = str(row.get("case_id", "unknown"))
        if row.get("completed") is not True:
            evaluated.append(
                {
                    "case_id": case_id,
                    "completed": False,
                    "failure_stage": "engine",
                    "error": row.get("error"),
                }
            )
            continue
        try:
            result = evaluate_case(row)
        except Exception as exc:
            evaluated.append(
                {
                    "case_id": case_id,
                    "completed": False,
                    "failure_stage": "interaction_evaluation",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        evaluated.append(result)
        successful_metrics.append(
            tuple(
                InteractionRecoveryMetrics(**metric)
                for metric in result["families"]
            )
        )

    aggregate = aggregate_metrics(successful_metrics)
    summary = {
        "total_cases": len(rows),
        "interaction_evaluable_cases": len(successful_metrics),
        "interaction_evaluability_rate": (
            len(successful_metrics) / len(rows) if rows else None
        ),
        "families": [metric.to_dict() for metric in aggregate],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"cases": evaluated}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            render_report(summary) + "\n",
            encoding="utf-8",
        )
    print(args.output)
    print(args.summary)
    if args.report is not None:
        print(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
