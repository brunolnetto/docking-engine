from __future__ import annotations

import os
from pathlib import Path
from time import sleep

try:
    import duckdb
except ImportError:  # pragma: no cover - optional dependency guard
    duckdb = None

from moldock.domain import DomainValidationError

from .ducklake import _catalog_write_lock


class DuckLakeRepositoryBase:
    """Shared connection/retry mechanics for append-oriented DuckLake adapters."""

    def __init__(
        self,
        *,
        catalog_path: str | Path,
        data_path: str | Path,
        max_transaction_retries: int = 5,
        retry_delay_seconds: float = 0.01,
    ) -> None:
        if duckdb is None:
            raise RuntimeError(
                'DuckLake repositories require the "ducklake" optional dependency'
            )
        if max_transaction_retries < 1:
            raise DomainValidationError(
                "max_transaction_retries must be >= 1"
            )
        if retry_delay_seconds < 0:
            raise DomainValidationError(
                "retry_delay_seconds must be >= 0"
            )

        self._catalog_path = Path(catalog_path)
        self._data_path = Path(data_path)
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._data_path.mkdir(parents=True, exist_ok=True)
        self._max_transaction_retries = max_transaction_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._write_lock = _catalog_write_lock(self._catalog_path)
        self._connection = None
        self._attach()
        self._bootstrap_coordination()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _attach(self) -> None:
        catalog = os.path.relpath(
            self._catalog_path,
            Path.cwd(),
        ).replace("'", "''")
        data = os.path.relpath(
            self._data_path,
            Path.cwd(),
        ).replace("'", "''")
        last_error: Exception | None = None

        for attempt_number in range(self._max_transaction_retries):
            connection = duckdb.connect()
            try:
                connection.execute("INSTALL sqlite")
                connection.execute("INSTALL ducklake")
                connection.execute("LOAD sqlite")
                connection.execute("LOAD ducklake")
                connection.execute(
                    f"""
                    ATTACH 'ducklake:sqlite:{catalog}' AS moldock
                    (
                        DATA_PATH '{data}',
                        DATA_INLINING_ROW_LIMIT 1000
                    )
                    """
                )
                self._connection = connection
                return
            except Exception as exc:
                try:
                    connection.close()
                except Exception:
                    pass
                if not self._is_transaction_conflict(exc):
                    raise
                last_error = exc
                if attempt_number + 1 < self._max_transaction_retries:
                    sleep(self._retry_delay_seconds)

        raise RuntimeError(
            "DuckLake attach retry budget exhausted"
        ) from last_error

    def _bootstrap_coordination(self) -> None:
        def operation() -> None:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.repository_coordination AS
                SELECT
                    CAST('shared_adapters' AS VARCHAR) AS coordination_key,
                    CAST(0 AS BIGINT) AS epoch
                """
            )
            rows = self._connection.execute(
                """
                SELECT coordination_key, epoch
                FROM moldock.repository_coordination
                WHERE coordination_key = 'shared_adapters'
                """
            ).fetchall()
            if len(rows) != 1:
                raise RuntimeError(
                    "DuckLake shared coordination row must be unique"
                )

        self._run_transaction(operation, touch_coordination=False)

    def _run_write(self, operation):
        return self._run_transaction(operation, touch_coordination=True)

    def _run_transaction(self, operation, *, touch_coordination: bool):
        with self._write_lock:
            last_error: Exception | None = None
            for attempt_number in range(self._max_transaction_retries):
                transaction_started = False
                try:
                    self._connection.execute("BEGIN TRANSACTION")
                    transaction_started = True
                    if touch_coordination:
                        self._touch_coordination()
                    result = operation()
                    self._connection.execute("COMMIT")
                    transaction_started = False
                    return result
                except Exception as exc:
                    if transaction_started:
                        try:
                            self._connection.execute("ROLLBACK")
                        except Exception:
                            pass
                    if not self._is_transaction_conflict(exc):
                        raise
                    last_error = exc
                    if attempt_number + 1 < self._max_transaction_retries:
                        self._reconnect()
                        sleep(self._retry_delay_seconds)

            raise RuntimeError(
                "DuckLake transaction retry budget exhausted"
            ) from last_error

    def _touch_coordination(self) -> None:
        self._connection.execute(
            """
            UPDATE moldock.repository_coordination
            SET epoch = epoch + 1
            WHERE coordination_key = 'shared_adapters'
            """
        )

    def _reconnect(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        self._attach()

    @staticmethod
    def _is_transaction_conflict(error: Exception) -> bool:
        transaction_error = getattr(
            duckdb,
            "TransactionException",
            None,
        )
        if (
            transaction_error is not None
            and isinstance(error, transaction_error)
        ):
            return True
        message = str(error).lower()
        return (
            "conflict" in message
            or "database is locked" in message
            or "serialization" in message
            or (
                "transaction" in message
                and "retry" in message
            )
        )
