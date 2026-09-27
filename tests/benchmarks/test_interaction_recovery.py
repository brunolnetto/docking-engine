from __future__ import annotations

import pytest

from benchmarks.interactions import (
    InteractionFingerprintKey,
    aggregate_metrics,
    compare_family,
    compare_fingerprints,
    extract_pdbqt_fingerprint,
    fingerprint,
)
from moldock.domain import PoseInteraction, PoseInteractionKind


def interaction(
    *,
    kind: PoseInteractionKind,
    residue: str,
    atom_serial: int,
) -> PoseInteraction:
    return PoseInteraction(
        pose_id="pose_1",
        kind=kind,
        receptor_atom_serial=atom_serial,
        receptor_atom_name="CA",
        receptor_residue_name=residue[:3],
        receptor_chain="A",
        receptor_residue_number=residue[3:],
        ligand_atom_serial=1,
        ligand_atom_name="C1",
        distance_angstrom=3.0,
        method="test",
        method_version="1",
    )


def atom(
    serial: int,
    name: str,
    residue: str,
    chain: str,
    residue_number: int,
    x: float,
    y: float,
    z: float,
    atom_type: str,
) -> bytes:
    return (
        f"ATOM  {serial:5d} {name:>4s} {residue:>3s} {chain:1s}"
        f"{residue_number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}"
        f"  1.00  0.00    +0.000 {atom_type}\n"
    ).encode()


def test_fingerprint_collapses_atom_pairs_to_residue_family():
    items = (
        interaction(
            kind=PoseInteractionKind.CONTACT,
            residue="ASP25",
            atom_serial=1,
        ),
        interaction(
            kind=PoseInteractionKind.CONTACT,
            residue="ASP25",
            atom_serial=2,
        ),
    )

    result = fingerprint(items)

    assert result == frozenset(
        {
            InteractionFingerprintKey(
                kind="contact",
                receptor_chain="A",
                receptor_residue_name="ASP",
                receptor_residue_number="25",
            )
        }
    )


def test_compare_family_reports_tp_fp_fn_and_similarity():
    reference = frozenset(
        {
            InteractionFingerprintKey("hydrogen_bond", "A", "ASP", "25"),
            InteractionFingerprintKey("hydrogen_bond", "A", "LYS", "42"),
        }
    )
    predicted = frozenset(
        {
            InteractionFingerprintKey("hydrogen_bond", "A", "ASP", "25"),
            InteractionFingerprintKey("hydrogen_bond", "A", "GLU", "50"),
        }
    )

    metric = compare_family(
        kind="hydrogen_bond",
        reference=reference,
        predicted=predicted,
    )

    assert metric.true_positive == 1
    assert metric.false_positive == 1
    assert metric.false_negative == 1
    assert metric.precision == pytest.approx(0.5)
    assert metric.recall == pytest.approx(0.5)
    assert metric.f1 == pytest.approx(0.5)
    assert metric.jaccard == pytest.approx(1 / 3)


def test_empty_family_is_unavailable_not_perfect():
    metric = compare_family(
        kind="salt_bridge",
        reference=frozenset(),
        predicted=frozenset(),
    )

    assert metric.precision is None
    assert metric.recall is None
    assert metric.f1 is None
    assert metric.jaccard is None


def test_aggregate_metrics_keeps_families_separate():
    reference = frozenset(
        {
            InteractionFingerprintKey("contact", "A", "ASP", "25"),
            InteractionFingerprintKey("hydrogen_bond", "A", "LYS", "42"),
        }
    )
    predicted = frozenset(
        {
            InteractionFingerprintKey("contact", "A", "ASP", "25"),
            InteractionFingerprintKey("hydrogen_bond", "A", "GLU", "50"),
        }
    )
    per_case = compare_fingerprints(reference, predicted)

    aggregated = {m.kind: m for m in aggregate_metrics((per_case,))}

    assert aggregated["contact"].f1 == pytest.approx(1.0)
    assert aggregated["hydrogen_bond"].f1 == pytest.approx(0.0)
    assert "overall" not in aggregated


def test_extract_pdbqt_fingerprint_uses_production_interaction_analyzer():
    receptor = atom(1, "C1", "LEU", "A", 20, 0.0, 0.0, 0.0, "C")
    ligand = atom(1, "C1", "LIG", "L", 1, 3.0, 0.0, 0.0, "C")

    result = extract_pdbqt_fingerprint(
        receptor_pdbqt=receptor,
        ligand_pdbqt=ligand,
    )

    assert InteractionFingerprintKey(
        "contact", "A", "LEU", "20"
    ) in result
    assert InteractionFingerprintKey(
        "hydrophobic_contact", "A", "LEU", "20"
    ) in result
