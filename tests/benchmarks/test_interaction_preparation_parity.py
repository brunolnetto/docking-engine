from benchmarks import evaluate_interactions


def test_interaction_reference_uses_posebusters_receptor_policy(monkeypatch, tmp_path):
    receptor = tmp_path / "case_protein.pdb"
    ligand = tmp_path / "case_ligand.sdf"
    receptor.write_text("ATOM      1  C   GLY A   1       0.000   0.000   0.000\n", encoding="utf-8")
    ligand.write_text("dummy", encoding="utf-8")

    seen = {}

    class Receptor:
        pdbqt = b"receptor"

    class Ligand:
        pdbqt = b"ligand"

    class ReceptorPreparer:
        def __init__(self, **kwargs):
            pass
        def prepare(self, request):
            seen["receptor_parameters"] = dict(request.protocol.parameters)
            return Receptor()

    class LigandPreparer:
        def __init__(self, **kwargs):
            pass
        def prepare(self, request):
            seen["ligand_content"] = request.content
            return (Ligand(),)

    monkeypatch.setattr(evaluate_interactions, "MeekoReceptorPreparer", ReceptorPreparer)
    monkeypatch.setattr(evaluate_interactions, "MeekoLigandPreparer", LigandPreparer)
    monkeypatch.setattr(
        evaluate_interactions,
        "ligand_content_with_explicit_hydrogens",
        lambda path: b"hydrogenated-sdf",
    )

    evaluate_interactions._prepare_reference(
        {
            "case_id": "case",
            "receptor_pdb": str(receptor),
            "crystal_ligand_sdf": str(ligand),
        }
    )

    assert seen["receptor_parameters"] == {
        "delete_bad_res": True,
        "default_altloc": "A",
        "forgive_extra_bonds": True,
    }
    assert seen["ligand_content"] == b"hydrogenated-sdf"
