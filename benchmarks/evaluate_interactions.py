from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parent.parent
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
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
    print(args.output)
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
