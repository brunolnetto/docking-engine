from __future__ import annotations

from collections import Counter
from typing import Iterable


def classify_preparation_error(error: str | None) -> str:
    text = error or ""
    if "Can't write PDBQT because atom_type is None" in text:
        return "missing_atom_type"
    if "Failed building template from CCD" in text:
        return "ccd_template_failure"
    if "tied for fewest missing and excess H" in text:
        return "ambiguous_residue_template"
    if "not in residue_templates" in text:
        return "unresolved_nonstandard_residue"
    if "MeekoReceptorPreparation" in text:
        return "other_receptor_preparation"
    if "MeekoLigandPreparation" in text:
        return "other_ligand_preparation"
    return "other_preparation"


def preparation_failure_taxonomy(
    rows: Iterable[dict[str, object]],
) -> dict[str, int]:
    counts = Counter(
        classify_preparation_error(
            str(row["error"]) if row.get("error") is not None else None
        )
        for row in rows
        if row.get("completed") is not True
        and row.get("failure_stage") == "preparation"
    )
    return dict(sorted(counts.items()))
