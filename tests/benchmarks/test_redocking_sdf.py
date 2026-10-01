from benchmarks import redocking


def test_explicit_hydrogen_ligand_is_complete_sdf_record(monkeypatch, tmp_path):
    ligand = tmp_path / "ligand.sdf"
    ligand.write_text("dummy", encoding="utf-8")

    class Conformer:
        pass

    class Molecule:
        pass

    class Supplier:
        def __init__(self, *args, **kwargs):
            pass
        def __iter__(self):
            return iter([Molecule()])

    class ChemStub:
        SDMolSupplier = Supplier

        @staticmethod
        def AddHs(molecule, addCoords):
            assert addCoords is True
            return molecule

        @staticmethod
        def MolToMolBlock(molecule):
            return "molblock"

    monkeypatch.setattr(redocking, "_rdkit_chem", lambda: ChemStub)

    content = redocking.ligand_content_with_explicit_hydrogens(ligand)

    assert content.endswith(b"\n$$$$\n")
