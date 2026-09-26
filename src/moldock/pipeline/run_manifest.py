from __future__ import annotations

from dataclasses import dataclass

from moldock.domain import DomainValidationError
from moldock.domain.common import content_id
from moldock.toolchain import ToolchainSnapshot


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    experiment_id: str
    protocol_id: str
    task_manifest_id: str
    search_space_id: str
    receptor_id: str
    receptor_source_sha256: str
    ligand_sources: tuple[tuple[str, str], ...]
    prepared_receptor_id: str
    prepared_ligand_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    toolchain_snapshot: ToolchainSnapshot | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "experiment_id",
            "protocol_id",
            "task_manifest_id",
            "search_space_id",
            "receptor_id",
            "receptor_source_sha256",
            "prepared_receptor_id",
        ):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(
                    f"{field_name} must not be blank"
                )

        for ligand_id, source_sha256 in self.ligand_sources:
            if not ligand_id.strip() or not source_sha256.strip():
                raise DomainValidationError(
                    "ligand_sources must contain non-blank identities"
                )
        if any(not value.strip() for value in self.prepared_ligand_ids):
            raise DomainValidationError(
                "prepared_ligand_ids must not contain blanks"
            )
        if any(not value.strip() for value in self.task_ids):
            raise DomainValidationError(
                "task_ids must not contain blanks"
            )

    @property
    def run_manifest_id(self) -> str:
        return content_id(
            "run_manifest",
            {
                "run_id": self.run_id,
                "experiment_id": self.experiment_id,
                "protocol_id": self.protocol_id,
                "task_manifest_id": self.task_manifest_id,
                "search_space_id": self.search_space_id,
                "receptor_id": self.receptor_id,
                "receptor_source_sha256": self.receptor_source_sha256,
                "ligand_sources": self.ligand_sources,
                "prepared_receptor_id": self.prepared_receptor_id,
                "prepared_ligand_ids": self.prepared_ligand_ids,
                "task_ids": self.task_ids,
                "toolchain_snapshot": self.toolchain_snapshot,
            },
        )

    def to_pipeline_result(self):
        from .offline import PipelineRunResult

        return PipelineRunResult(
            run_id=self.run_id,
            experiment_id=self.experiment_id,
            protocol_id=self.protocol_id,
            manifest_id=self.task_manifest_id,
            prepared_receptor_id=self.prepared_receptor_id,
            prepared_ligand_ids=self.prepared_ligand_ids,
            task_ids=self.task_ids,
            toolchain_snapshot=self.toolchain_snapshot,
        )
