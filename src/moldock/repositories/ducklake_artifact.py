from __future__ import annotations

from pathlib import Path

from moldock.domain import ArtifactMetadata, DomainValidationError

from .ducklake_base import DuckLakeRepositoryBase


class DuckLakeArtifactRepository(DuckLakeRepositoryBase):
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
                CREATE TABLE IF NOT EXISTS moldock.artifacts (
                    artifact_id VARCHAR,
                    uri VARCHAR,
                    sha256 VARCHAR,
                    size_bytes BIGINT,
                    media_type VARCHAR,
                    kind VARCHAR,
                    producer_attempt_id VARCHAR
                )
                """
            )

        self._run_write(operation)

    def register(self, artifact: ArtifactMetadata) -> None:
        def operation() -> None:
            rows = self._rows_for_id(artifact.artifact_id)
            if rows:
                current = self._from_row(rows[0])
                if current != artifact:
                    raise DomainValidationError(
                        "artifact ID already exists with conflicting metadata"
                    )
                return
            self._connection.execute(
                """
                INSERT INTO moldock.artifacts
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    artifact.artifact_id,
                    artifact.uri,
                    artifact.sha256,
                    artifact.size_bytes,
                    artifact.media_type,
                    artifact.kind,
                    artifact.producer_attempt_id,
                ],
            )

        self._run_write(operation)

    def get(self, artifact_id: str) -> ArtifactMetadata | None:
        rows = self._rows_for_id(artifact_id)
        if not rows:
            return None
        return self._from_row(rows[0])

    def list_for_attempt(
        self,
        attempt_id: str,
    ) -> tuple[ArtifactMetadata, ...]:
        rows = self._connection.execute(
            """
            SELECT
                artifact_id,
                uri,
                sha256,
                size_bytes,
                media_type,
                kind,
                producer_attempt_id
            FROM moldock.artifacts
            WHERE producer_attempt_id = ?
            ORDER BY artifact_id
            """,
            [attempt_id],
        ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def _rows_for_id(self, artifact_id: str):
        return self._connection.execute(
            """
            SELECT
                artifact_id,
                uri,
                sha256,
                size_bytes,
                media_type,
                kind,
                producer_attempt_id
            FROM moldock.artifacts
            WHERE artifact_id = ?
            """,
            [artifact_id],
        ).fetchall()

    @staticmethod
    def _from_row(row) -> ArtifactMetadata:
        return ArtifactMetadata(
            artifact_id=row[0],
            uri=row[1],
            sha256=row[2],
            size_bytes=row[3],
            media_type=row[4],
            kind=row[5],
            producer_attempt_id=row[6],
        )
