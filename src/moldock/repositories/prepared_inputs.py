from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from moldock.domain import (
    PreparedLigand,
    PreparedReceptor,
    StoredBlob,
)


@dataclass(frozen=True, slots=True)
class PreparedLigandBinding:
    prepared: PreparedLigand
    blob: StoredBlob


@dataclass(frozen=True, slots=True)
class PreparedReceptorBinding:
    prepared: PreparedReceptor
    blob: StoredBlob


@runtime_checkable
class PreparedInputRepository(Protocol):
    def register_ligand(
        self,
        prepared: PreparedLigand,
        blob: StoredBlob,
    ) -> None: ...

    def register_receptor(
        self,
        prepared: PreparedReceptor,
        blob: StoredBlob,
    ) -> None: ...

    def get_ligand(
        self,
        prepared_ligand_id: str,
    ) -> PreparedLigandBinding | None: ...

    def get_receptor(
        self,
        prepared_receptor_id: str,
    ) -> PreparedReceptorBinding | None: ...
