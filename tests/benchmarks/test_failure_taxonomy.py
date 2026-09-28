from benchmarks.failure_taxonomy import (
    classify_preparation_error,
    preparation_failure_taxonomy,
)


def test_classifies_known_meeko_preparation_failures():
    assert classify_preparation_error(
        "MeekoReceptorPreparationError: Failed building template from CCD for resname='CO'"
    ) == "ccd_template_failure"
    assert classify_preparation_error(
        "ValueError: Can't write PDBQT because atom_type is None."
    ) == "missing_atom_type"
    assert classify_preparation_error(
        "RuntimeError: tied for fewest missing and excess H"
    ) == "ambiguous_residue_template"
    assert classify_preparation_error(
        "RuntimeWarning: Input residues {'A:1': 'HEM'} not in residue_templates"
    ) == "unresolved_nonstandard_residue"


def test_taxonomy_counts_only_preparation_failures():
    rows = [
        {"completed": False, "failure_stage": "preparation", "error": "Failed building template from CCD"},
        {"completed": False, "failure_stage": "preparation", "error": "Can't write PDBQT because atom_type is None"},
        {"completed": False, "failure_stage": "evaluation", "error": "Failed building template from CCD"},
        {"completed": True},
    ]
    assert preparation_failure_taxonomy(rows) == {
        "ccd_template_failure": 1,
        "missing_atom_type": 1,
    }
