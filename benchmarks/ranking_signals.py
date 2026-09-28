from __future__ import annotations

import re
from typing import Any


_MODEL = re.compile(rb"^MODEL\s+(\d+)\s*$")
_RESULT = re.compile(
    rb"^REMARK VINA RESULT:\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)\s*$"
)


def vina_pose_scores(content: bytes) -> list[dict[str, Any]]:
    """Extract production-available Vina ranking signals without reference truth."""
    rows: list[dict[str, Any]] = []
    model_index: int | None = None
    for raw in content.splitlines():
        model = _MODEL.match(raw)
        if model:
            model_index = int(model.group(1))
            continue
        result = _RESULT.match(raw)
        if result and model_index is not None:
            affinity, rmsd_lb, rmsd_ub = (
                float(result.group(index)) for index in (1, 2, 3)
            )
            rows.append(
                {
                    "rank": len(rows) + 1,
                    "model_index": model_index,
                    "vina_affinity_kcal_mol": affinity,
                    "vina_internal_rmsd_lb": rmsd_lb,
                    "vina_internal_rmsd_ub": rmsd_ub,
                }
            )
    return rows


def attach_reference_labels(
    signals: list[dict[str, Any]],
    reference_rmsds: list[float | None],
) -> list[dict[str, Any]]:
    """Attach benchmark-only labels after feature extraction.

    Reference RMSD is deliberately isolated from the production signal extractor
    so an offline reranker cannot accidentally use oracle information.
    """
    labeled: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        row = dict(signal)
        rmsd = reference_rmsds[index] if index < len(reference_rmsds) else None
        row["reference_rmsd_angstrom"] = rmsd
        row["reference_success_le_2a"] = (
            bool(float(rmsd) <= 2.0) if rmsd is not None else None
        )
        labeled.append(row)
    return labeled
