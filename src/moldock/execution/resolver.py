from __future__ import annotations

import hashlib
from typing import Any, Mapping, Protocol, runtime_checkable

from moldock.domain import (
    DockingBox,
    DockingExecutionRequest,
    DockingTask,
    DomainValidationError,
)


@runtime_checkable
class DockingInputResolver(Protocol):
    def resolve(self, task: DockingTask) -> DockingExecutionRequest: ...


class MemoryDockingInputResolver:
    def __init__(self) -> None:
        self._receptors: dict[str, bytes] = {}
        self._ligands: dict[str, bytes] = {}
        self._search_spaces: dict[str, DockingBox] = {}
        self._parameters: dict[str, Mapping[str, Any]] = {}

    def register_receptor(self, prepared_receptor_id: str, content: bytes) -> None:
        existing = self._receptors.get(prepared_receptor_id)
        if existing is not None and existing != content:
            raise DomainValidationError(
                "prepared receptor ID already exists with conflicting content"
            )
        self._receptors[prepared_receptor_id] = content

    def register_ligand(self, prepared_ligand_id: str, content: bytes) -> None:
        existing = self._ligands.get(prepared_ligand_id)
        if existing is not None and existing != content:
            raise DomainValidationError(
                "prepared ligand ID already exists with conflicting content"
            )
        self._ligands[prepared_ligand_id] = content

    def register_search_space(self, search_space: DockingBox) -> None:
        self._search_spaces[search_space.search_space_id] = search_space

    def register_parameters(
        self,
        experiment_id: str,
        parameters: Mapping[str, Any],
    ) -> None:
        self._parameters[experiment_id] = dict(parameters)

    def resolve(self, task: DockingTask) -> DockingExecutionRequest:
        receptor = self._receptors.get(task.prepared_receptor_id)
        if receptor is None:
            raise DomainValidationError(
                f"prepared receptor not found: {task.prepared_receptor_id}"
            )

        ligand = self._ligands.get(task.prepared_ligand_id)
        if ligand is None:
            raise DomainValidationError(
                f"prepared ligand not found: {task.prepared_ligand_id}"
            )

        search_space = self._search_spaces.get(task.search_space_id)
        if search_space is None:
            raise DomainValidationError(
                f"search space not found: {task.search_space_id}"
            )

        return DockingExecutionRequest(
            task=task,
            receptor_pdbqt=receptor,
            ligand_pdbqt=ligand,
            search_space=search_space,
            parameters=self._parameters.get(task.experiment_id, {}),
        )



class PersistentDockingInputResolver:
    """Resolve durable prepared molecular inputs into execution requests."""

    def __init__(
        self,
        *,
        prepared_inputs,
        artifact_store,
    ) -> None:
        self._prepared_inputs = prepared_inputs
        self._artifact_store = artifact_store
        self._search_spaces: dict[str, DockingBox] = {}
        self._parameters: dict[str, Mapping[str, Any]] = {}

    def register_search_space(self, search_space: DockingBox) -> None:
        self._search_spaces[search_space.search_space_id] = search_space

    def register_parameters(
        self,
        experiment_id: str,
        parameters: Mapping[str, Any],
    ) -> None:
        self._parameters[experiment_id] = dict(parameters)

    def resolve(self, task: DockingTask) -> DockingExecutionRequest:
        receptor_binding = self._prepared_inputs.get_receptor(
            task.prepared_receptor_id
        )
        if receptor_binding is None:
            raise DomainValidationError(
                f"prepared receptor not found: {task.prepared_receptor_id}"
            )

        ligand_binding = self._prepared_inputs.get_ligand(
            task.prepared_ligand_id
        )
        if ligand_binding is None:
            raise DomainValidationError(
                f"prepared ligand not found: {task.prepared_ligand_id}"
            )

        search_space = self._search_spaces.get(task.search_space_id)
        if search_space is None:
            raise DomainValidationError(
                f"search space not found: {task.search_space_id}"
            )

        receptor = self._read_verified(
            receptor_binding.blob,
            "prepared receptor",
        )
        ligand = self._read_verified(
            ligand_binding.blob,
            "prepared ligand",
        )

        return DockingExecutionRequest(
            task=task,
            receptor_pdbqt=receptor,
            ligand_pdbqt=ligand,
            search_space=search_space,
            parameters=self._parameters.get(task.experiment_id, {}),
        )

    def _read_verified(self, blob, label: str) -> bytes:
        content = self._artifact_store.read(blob.uri)
        digest = hashlib.sha256(content).hexdigest()
        if digest != blob.sha256 or len(content) != blob.size_bytes:
            raise DomainValidationError(
                f"{label} artifact integrity check failed: {blob.blob_id}"
            )
        return content
