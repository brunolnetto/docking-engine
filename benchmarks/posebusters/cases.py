from __future__ import annotations

from pathlib import Path


HERE = Path(__file__).resolve().parent
CASE_IDS_PATH = HERE / "posebusters_pdb_ccd_ids.txt"


def load_case_ids(
    path: Path = CASE_IDS_PATH,
    *,
    expected_count: int | None = 308,
) -> frozenset[str]:
    identifiers = tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    unique = frozenset(identifiers)
    if len(unique) != len(identifiers):
        raise RuntimeError("PoseBusters case identifier file contains duplicates")
    if expected_count is not None and len(unique) != expected_count:
        raise RuntimeError(
            "PoseBusters case identifier file must contain exactly "
            f"{expected_count} unique case IDs"
        )
    return unique
