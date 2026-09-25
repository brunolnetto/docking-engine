import pytest

from moldock.domain import (
    DomainValidationError,
    PreparedLigand,
    PreparedReceptor,
)


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (PreparedReceptor, "receptor_id"),
        (PreparedReceptor, "preparation_id"),
        (PreparedReceptor, "prepared_receptor_id"),
        (PreparedLigand, "ligand_id"),
        (PreparedLigand, "preparation_id"),
        (PreparedLigand, "prepared_ligand_id"),
    ],
)
def test_prepared_inputs_reject_blank_identifiers(factory, field):
    if factory is PreparedReceptor:
        values = {
            "receptor_id": "rec_1",
            "preparation_id": "rprep_1",
            "prepared_receptor_id": "prepared_rec_1",
        }
    else:
        values = {
            "ligand_id": "lig_1",
            "preparation_id": "lprep_1",
            "prepared_ligand_id": "prepared_lig_1",
        }

    values[field] = " "

    with pytest.raises(DomainValidationError):
        factory(**values)
