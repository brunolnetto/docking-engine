from __future__ import annotations

import json
from pathlib import Path

from moldock.domain import DomainValidationError
from moldock.pipeline import RunManifest
from moldock.toolchain import ExecutableInfo, ToolchainSnapshot

from .ducklake_base import DuckLakeRepositoryBase


def _tool_info_payload(info: ExecutableInfo) -> dict[str, str]:
    return {
        "name": info.name,
        "executable": info.executable,
        "resolved_path": info.resolved_path,
        "version": info.version,
    }


def _encode_toolchain(
    snapshot: ToolchainSnapshot | None,
) -> str | None:
    if snapshot is None:
        return None
    return json.dumps(
        {
            "vina": _tool_info_payload(snapshot.vina),
            "meeko_ligand": _tool_info_payload(
                snapshot.meeko_ligand
            ),
            "meeko_receptor": _tool_info_payload(
                snapshot.meeko_receptor
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_toolchain(
    payload: str | None,
) -> ToolchainSnapshot | None:
    if payload is None:
        return None
    data = json.loads(payload)
    return ToolchainSnapshot(
        vina=ExecutableInfo(**data["vina"]),
        meeko_ligand=ExecutableInfo(**data["meeko_ligand"]),
        meeko_receptor=ExecutableInfo(**data["meeko_receptor"]),
    )


class DuckLakeRunManifestRepository(DuckLakeRepositoryBase):
    def __init__(
        self,
        *,
        catalog_path: str | Path,
        data_path: str | Path,
        max_transaction_retries: int = 5,
        retry_delay_seconds: float = 0.01,
    ) -> None:
        super().__init__(
            catalog_path=catalog_path,
            data_path=data_path,
            max_transaction_retries=max_transaction_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        def operation() -> None:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.run_manifests (
                    run_id VARCHAR,
                    run_manifest_id VARCHAR,
                    experiment_id VARCHAR,
                    protocol_id VARCHAR,
                    task_manifest_id VARCHAR,
                    search_space_id VARCHAR,
                    receptor_id VARCHAR,
                    receptor_source_sha256 VARCHAR,
                    ligand_sources_json VARCHAR,
                    prepared_receptor_id VARCHAR,
                    prepared_ligand_ids_json VARCHAR,
                    task_ids_json VARCHAR,
                    toolchain_json VARCHAR
                )
                """
            )

        self._run_write(operation)

    def register(self, manifest: RunManifest) -> None:
        def operation() -> None:
            current = self._get(manifest.run_id)
            if current is not None:
                if current != manifest:
                    raise DomainValidationError(
                        "run ID already exists with conflicting manifest"
                    )
                return

            self._connection.execute(
                """
                INSERT INTO moldock.run_manifests
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    manifest.run_id,
                    manifest.run_manifest_id,
                    manifest.experiment_id,
                    manifest.protocol_id,
                    manifest.task_manifest_id,
                    manifest.search_space_id,
                    manifest.receptor_id,
                    manifest.receptor_source_sha256,
                    json.dumps(
                        list(manifest.ligand_sources),
                        separators=(",", ":"),
                    ),
                    manifest.prepared_receptor_id,
                    json.dumps(
                        list(manifest.prepared_ligand_ids),
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        list(manifest.task_ids),
                        separators=(",", ":"),
                    ),
                    _encode_toolchain(
                        manifest.toolchain_snapshot
                    ),
                ],
            )

        self._run_write(operation)

    def get(self, run_id: str) -> RunManifest | None:
        return self._get(run_id)

    def _get(self, run_id: str) -> RunManifest | None:
        rows = self._connection.execute(
            """
            SELECT
                run_id,
                run_manifest_id,
                experiment_id,
                protocol_id,
                task_manifest_id,
                search_space_id,
                receptor_id,
                receptor_source_sha256,
                ligand_sources_json,
                prepared_receptor_id,
                prepared_ligand_ids_json,
                task_ids_json,
                toolchain_json
            FROM moldock.run_manifests
            WHERE run_id = ?
            """,
            [run_id],
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("run manifest identity is duplicated")

        row = rows[0]
        manifest = RunManifest(
            run_id=row[0],
            experiment_id=row[2],
            protocol_id=row[3],
            task_manifest_id=row[4],
            search_space_id=row[5],
            receptor_id=row[6],
            receptor_source_sha256=row[7],
            ligand_sources=tuple(
                tuple(item)
                for item in json.loads(row[8])
            ),
            prepared_receptor_id=row[9],
            prepared_ligand_ids=tuple(json.loads(row[10])),
            task_ids=tuple(json.loads(row[11])),
            toolchain_snapshot=_decode_toolchain(row[12]),
        )
        if manifest.run_manifest_id != row[1]:
            raise RuntimeError(
                "persisted run manifest content does not match its identity"
            )
        return manifest
