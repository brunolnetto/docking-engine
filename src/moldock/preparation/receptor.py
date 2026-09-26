from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Protocol, runtime_checkable

from moldock.domain import PreparedReceptor
from moldock.domain.common import (
    DomainValidationError,
    content_id,
    deep_freeze,
)


@dataclass(frozen=True, slots=True)
class ReceptorPreparationProtocol:
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
            "rprep",
            {
                "method": self.method,
                "method_version": self.method_version,
                "parameters": self.parameters,
            },
        )


@dataclass(frozen=True, slots=True)
class ReceptorPreparationRequest:
    receptor_id: str
    source_format: str
    content: bytes
    protocol: ReceptorPreparationProtocol

    def __post_init__(self) -> None:
        if not self.receptor_id.strip():
            raise DomainValidationError(
                "receptor_id must not be blank"
            )
        if not self.source_format.strip():
            raise DomainValidationError(
                "source_format must not be blank"
            )
        if not isinstance(self.content, bytes):
            raise DomainValidationError(
                "receptor source content must be bytes"
            )
        if not isinstance(
            self.protocol,
            ReceptorPreparationProtocol,
        ):
            raise DomainValidationError(
                "protocol must be a ReceptorPreparationProtocol"
            )

    @property
    def source_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True, slots=True)
class ReceptorPreparationArtifact:
    receptor_id: str
    preparation_id: str
    model_id: str
    chain_ids: tuple[str, ...]
    pdbqt: bytes

    def __post_init__(self) -> None:
        for field_name in (
            "receptor_id",
            "preparation_id",
            "model_id",
        ):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(
                    f"{field_name} must not be blank"
                )

        normalized_chains = tuple(
            sorted(set(self.chain_ids))
        )
        if not normalized_chains:
            raise DomainValidationError(
                "chain_ids must not be empty"
            )
        if any(not chain.strip() for chain in normalized_chains):
            raise DomainValidationError(
                "chain_ids must not contain blanks"
            )
        object.__setattr__(self, "chain_ids", normalized_chains)

        if not isinstance(self.pdbqt, bytes):
            raise DomainValidationError(
                "prepared receptor PDBQT must be bytes"
            )

    @property
    def pdbqt_sha256(self) -> str:
        return hashlib.sha256(self.pdbqt).hexdigest()

    @property
    def prepared_receptor_id(self) -> str:
        return content_id(
            "prepared_receptor",
            {
                "receptor_id": self.receptor_id,
                "preparation_id": self.preparation_id,
                "model_id": self.model_id,
                "chain_ids": self.chain_ids,
                "pdbqt_sha256": self.pdbqt_sha256,
            },
        )

    def as_prepared_receptor(self) -> PreparedReceptor:
        return PreparedReceptor(
            receptor_id=self.receptor_id,
            preparation_id=self.preparation_id,
            prepared_receptor_id=self.prepared_receptor_id,
        )


@runtime_checkable
class ReceptorPreparer(Protocol):
    def prepare(
        self,
        request: ReceptorPreparationRequest,
    ) -> ReceptorPreparationArtifact: ...
