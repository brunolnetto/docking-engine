from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Protocol, runtime_checkable

from moldock.domain import PreparedLigand
from moldock.domain.common import (
    DomainValidationError,
    content_id,
    deep_freeze,
)


@dataclass(frozen=True, slots=True)
class LigandPreparationProtocol:
    method: str
    method_version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.method.strip():
            raise DomainValidationError("method must not be blank")
        if not self.method_version.strip():
            raise DomainValidationError(
                "method_version must not be blank"
            )
        object.__setattr__(
            self,
            "parameters",
            deep_freeze(self.parameters),
        )

    @property
    def preparation_id(self) -> str:
        return content_id(
            "lprep",
            {
                "method": self.method,
                "method_version": self.method_version,
                "parameters": self.parameters,
            },
        )


@dataclass(frozen=True, slots=True)
class LigandPreparationRequest:
    ligand_id: str
    source_format: str
    content: bytes
    protocol: LigandPreparationProtocol

    def __post_init__(self) -> None:
        if not self.ligand_id.strip():
            raise DomainValidationError("ligand_id must not be blank")
        if not self.source_format.strip():
            raise DomainValidationError(
                "source_format must not be blank"
            )
        if not isinstance(self.content, bytes):
            raise DomainValidationError(
                "ligand source content must be bytes"
            )
        if not isinstance(
            self.protocol,
            LigandPreparationProtocol,
        ):
            raise DomainValidationError(
                "protocol must be a LigandPreparationProtocol"
            )

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True, slots=True)
class LigandPreparationArtifact:
    ligand_id: str
    preparation_id: str
    microstate_id: str
    conformer_id: str
    pdbqt: bytes

    def __post_init__(self) -> None:
        for field_name in (
            "ligand_id",
            "preparation_id",
            "microstate_id",
            "conformer_id",
        ):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(
                    f"{field_name} must not be blank"
                )
        if not isinstance(self.pdbqt, bytes):
            raise DomainValidationError(
                "prepared ligand PDBQT must be bytes"
            )

    @property
    def pdbqt_sha256(self) -> str:
        return hashlib.sha256(self.pdbqt).hexdigest()

    @property
    def prepared_ligand_id(self) -> str:
        return content_id(
            "prepared_ligand",
            {
                "ligand_id": self.ligand_id,
                "preparation_id": self.preparation_id,
                "microstate_id": self.microstate_id,
                "conformer_id": self.conformer_id,
                "pdbqt_sha256": self.pdbqt_sha256,
            },
        )

    def as_prepared_ligand(self) -> PreparedLigand:
        return PreparedLigand(
            ligand_id=self.ligand_id,
            preparation_id=self.preparation_id,
            prepared_ligand_id=self.prepared_ligand_id,
        )


@runtime_checkable
class LigandPreparer(Protocol):
    def prepare(
        self,
        request: LigandPreparationRequest,
    ) -> tuple[LigandPreparationArtifact, ...]: ...
