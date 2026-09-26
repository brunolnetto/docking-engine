from __future__ import annotations

from pathlib import Path

from moldock.domain import (
    DomainValidationError,
    PreparedLigand,
    PreparedReceptor,
    StoredBlob,
)

from .ducklake_base import DuckLakeRepositoryBase
from .prepared_inputs import (
    PreparedLigandBinding,
    PreparedReceptorBinding,
)


class DuckLakePreparedInputRepository(DuckLakeRepositoryBase):
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
                CREATE TABLE IF NOT EXISTS moldock.prepared_ligands (
                    prepared_ligand_id VARCHAR,
                    ligand_id VARCHAR,
                    preparation_id VARCHAR,
                    blob_id VARCHAR,
                    uri VARCHAR,
                    sha256 VARCHAR,
                    size_bytes BIGINT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.prepared_receptors (
                    prepared_receptor_id VARCHAR,
                    receptor_id VARCHAR,
                    preparation_id VARCHAR,
                    blob_id VARCHAR,
                    uri VARCHAR,
                    sha256 VARCHAR,
                    size_bytes BIGINT
                )
                """
            )

        self._run_write(operation)

    def register_ligand(
        self,
        prepared: PreparedLigand,
        blob: StoredBlob,
    ) -> None:
        binding = PreparedLigandBinding(prepared, blob)

        def operation() -> None:
            current = self._get_ligand(
                prepared.prepared_ligand_id
            )
            if current is not None:
                if current != binding:
                    raise DomainValidationError(
                        "prepared ligand ID already exists with conflicting binding"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.prepared_ligands
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    prepared.prepared_ligand_id,
                    prepared.ligand_id,
                    prepared.preparation_id,
                    blob.blob_id,
                    blob.uri,
                    blob.sha256,
                    blob.size_bytes,
                ],
            )

        self._run_write(operation)

    def register_receptor(
        self,
        prepared: PreparedReceptor,
        blob: StoredBlob,
    ) -> None:
        binding = PreparedReceptorBinding(prepared, blob)

        def operation() -> None:
            current = self._get_receptor(
                prepared.prepared_receptor_id
            )
            if current is not None:
                if current != binding:
                    raise DomainValidationError(
                        "prepared receptor ID already exists with conflicting binding"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.prepared_receptors
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    prepared.prepared_receptor_id,
                    prepared.receptor_id,
                    prepared.preparation_id,
                    blob.blob_id,
                    blob.uri,
                    blob.sha256,
                    blob.size_bytes,
                ],
            )

        self._run_write(operation)

    def get_ligand(
        self,
        prepared_ligand_id: str,
    ) -> PreparedLigandBinding | None:
        return self._get_ligand(prepared_ligand_id)

    def get_receptor(
        self,
        prepared_receptor_id: str,
    ) -> PreparedReceptorBinding | None:
        return self._get_receptor(prepared_receptor_id)

    def _get_ligand(
        self,
        prepared_ligand_id: str,
    ) -> PreparedLigandBinding | None:
        rows = self._connection.execute(
            """
            SELECT
                prepared_ligand_id,
                ligand_id,
                preparation_id,
                blob_id,
                uri,
                sha256,
                size_bytes
            FROM moldock.prepared_ligands
            WHERE prepared_ligand_id = ?
            """,
            [prepared_ligand_id],
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError(
                "prepared ligand identity is duplicated"
            )
        row = rows[0]
        return PreparedLigandBinding(
            prepared=PreparedLigand(
                ligand_id=row[1],
                preparation_id=row[2],
                prepared_ligand_id=row[0],
            ),
            blob=StoredBlob(
                blob_id=row[3],
                uri=row[4],
                sha256=row[5],
                size_bytes=row[6],
            ),
        )

    def _get_receptor(
        self,
        prepared_receptor_id: str,
    ) -> PreparedReceptorBinding | None:
        rows = self._connection.execute(
            """
            SELECT
                prepared_receptor_id,
                receptor_id,
                preparation_id,
                blob_id,
                uri,
                sha256,
                size_bytes
            FROM moldock.prepared_receptors
            WHERE prepared_receptor_id = ?
            """,
            [prepared_receptor_id],
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError(
                "prepared receptor identity is duplicated"
            )
        row = rows[0]
        return PreparedReceptorBinding(
            prepared=PreparedReceptor(
                receptor_id=row[1],
                preparation_id=row[2],
                prepared_receptor_id=row[0],
            ),
            blob=StoredBlob(
                blob_id=row[3],
                uri=row[4],
                sha256=row[5],
                size_bytes=row[6],
            ),
        )
