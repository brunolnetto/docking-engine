from rdkit import Chem
from rdkit.Chem import AllChem

from benchmarks.redocking import ligand_content_with_explicit_hydrogens


def test_ligand_content_with_explicit_hydrogens_is_valid_sdf(tmp_path):
    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(molecule, randomSeed=42)
    source = tmp_path / "ligand.sdf"
    writer = Chem.SDWriter(str(source))
    writer.write(molecule)
    writer.close()

    content = ligand_content_with_explicit_hydrogens(source)

    assert content.endswith(b"$$$$\n")
    output = tmp_path / "roundtrip.sdf"
    output.write_bytes(content)
    parsed = [
        mol
        for mol in Chem.SDMolSupplier(str(output), removeHs=False)
        if mol is not None
    ]
    assert len(parsed) == 1
