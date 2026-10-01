from benchmarks.posebusters.preparation_policy import (
    preparation_decisions,
)


def _hetatm(name: str, chain: str, number: int) -> str:
    return (
        f"HETATM    1  X   {name:>3} {chain}{number:4d}    "
        "   0.000   0.000   0.000  1.00 20.00           C\n"
    )


def test_policy_preserves_functional_cofactors_and_metals():
    decisions = preparation_decisions(
        (_hetatm("HEM", "A", 401) + _hetatm("CO", "A", 402)).encode()
    )
    assert [item.decision for item in decisions] == ["preserve", "preserve"]
    assert all("delete" in item.reason or "retain" in item.reason for item in decisions)


def test_policy_marks_only_known_solvent_additives_as_removal_candidates():
    decisions = preparation_decisions(
        (_hetatm("HOH", "A", 501) + _hetatm("GOL", "A", 502)).encode()
    )
    assert [item.decision for item in decisions] == [
        "safe_remove_candidate",
        "safe_remove_candidate",
    ]
    assert all("explicit policy" in item.reason for item in decisions)


def test_policy_requires_manual_disposition_for_unknown_hetero_residue():
    [decision] = preparation_decisions(_hetatm("XYZ", "B", 9).encode())
    assert decision.decision == "manual_template_required"
    assert "explicit template" in decision.reason
