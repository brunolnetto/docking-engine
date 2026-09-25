from __future__ import annotations

from dataclasses import dataclass

from .common import DomainValidationError


def _require_identifiers(instance: object, fields: tuple[str, ...]) -> None:
    for field in fields:
        value = getattr(instance, field)
        if not value.strip():
            raise DomainValidationError(f"{field} must not be blank")


@dataclass(frozen=True, slots=True)
class PreparedReceptor:
    receptor_id: str
    preparation_id: str
    prepared_receptor_id: str

    def __post_init__(self) -> None:
        _require_identifiers(
            self,
            ("receptor_id", "preparation_id", "prepared_receptor_id"),
        )


@dataclass(frozen=True, slots=True)
class PreparedLigand:
    ligand_id: str
    preparation_id: str
    prepared_ligand_id: str

    def __post_init__(self) -> None:
        _require_identifiers(
            self,
            ("ligand_id", "preparation_id", "prepared_ligand_id"),
        )
