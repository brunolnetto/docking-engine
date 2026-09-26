from __future__ import annotations

from collections.abc import Callable
from typing import AbstractSet
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from time import sleep
import os

try:
    import duckdb
except ImportError:  # pragma: no cover - exercised only without optional dependency
    duckdb = None

from moldock.domain import (
    DockingTask,
    DomainValidationError,
    FailureKind,
    RetryPolicy,
    TaskAttempt,
    TaskStatus,
    content_id,
)


BeforeClaimWrite = Callable[[], None]


_CATALOG_LOCKS_GUARD = Lock()
_CATALOG_WRITE_LOCKS: dict[Path, RLock] = {}


def _catalog_write_lock(catalog_path: Path) -> RLock:
    key = catalog_path.resolve()
    with _CATALOG_LOCKS_GUARD:
        lock = _CATALOG_WRITE_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _CATALOG_WRITE_LOCKS[key] = lock
        return lock


class DuckLakeTaskRepository:
    """DuckLake-backed task repository used to validate multi-client claim semantics.

    The adapter intentionally uses one coordination row to force all write
    transactions onto a shared conflict point. This serializes mutations but
    makes cross-client correctness explicit for the concurrency spike.
    """

    def __init__(
        self,
        *,
        catalog_path: str | Path,
        data_path: str | Path,
        retry_policy: RetryPolicy | None = None,
        default_lease_duration: timedelta = timedelta(minutes=5),
        max_transaction_retries: int = 5,
        retry_delay_seconds: float = 0.01,
        before_claim_write: BeforeClaimWrite | None = None,
    ) -> None:
        if duckdb is None:
            raise RuntimeError(
                'DuckLakeTaskRepository requires the "ducklake" optional dependency'
            )
        if default_lease_duration <= timedelta(0):
            raise DomainValidationError("default_lease_duration must be > 0")
        if max_transaction_retries < 1:
            raise DomainValidationError("max_transaction_retries must be >= 1")
        if retry_delay_seconds < 0:
            raise DomainValidationError("retry_delay_seconds must be >= 0")

        self._catalog_path = Path(catalog_path)
        self._data_path = Path(data_path)
        self._write_lock = _catalog_write_lock(self._catalog_path)
        self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._data_path.mkdir(parents=True, exist_ok=True)
        self._retry_policy = retry_policy or RetryPolicy()
        self._default_lease_duration = default_lease_duration
        self._max_transaction_retries = max_transaction_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._before_claim_write = before_claim_write
        self._connection = None
        self._attach()
        self._initialize_schema()

    def _attach(self) -> None:
        catalog = os.path.relpath(self._catalog_path, Path.cwd()).replace("'", "''")
        data = os.path.relpath(self._data_path, Path.cwd()).replace("'", "''")
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

    def _initialize_schema(self) -> None:
        def operation() -> None:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.tasks (
                    task_id VARCHAR,
                    experiment_id VARCHAR,
                    receptor_id VARCHAR,
                    ligand_id VARCHAR,
                    prepared_receptor_id VARCHAR,
                    prepared_ligand_id VARCHAR,
                    search_space_id VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.attempts (
                    attempt_id VARCHAR,
                    task_id VARCHAR,
                    run_id VARCHAR,
                    attempt_number INTEGER,
                    worker_id VARCHAR,
                    started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ,
                    heartbeat_at TIMESTAMPTZ,
                    lease_expires_at TIMESTAMPTZ,
                    status VARCHAR,
                    error VARCHAR,
                    failure_kind VARCHAR
                )
                """
            )
            self._connection.execute(
                """
                ALTER TABLE moldock.attempts
                ADD COLUMN IF NOT EXISTS failure_kind VARCHAR
                """
            )
            self._connection.execute(
                """
                UPDATE moldock.attempts
                SET failure_kind = CASE
                    WHEN error = 'lease expired' THEN 'LEASE'
                    ELSE 'INFRASTRUCTURE'
                END
                WHERE status = 'FAILED' AND failure_kind IS NULL
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS moldock.claim_coordination AS
                SELECT
                    CAST('task_repository' AS VARCHAR) AS coordination_key,
                    CAST(0 AS BIGINT) AS epoch
                """
            )
            rows = self._connection.execute(
                """
                SELECT coordination_key, epoch
                FROM moldock.claim_coordination
                WHERE coordination_key = 'task_repository'
                """
            ).fetchall()
            if len(rows) != 1:
                raise RuntimeError(
                    "DuckLake claim coordination row must be unique"
                )

        self._run_write(operation)

    def register(self, task: DockingTask) -> None:
        def operation() -> None:
            existing = self._task_rows(task.task_id)
            if existing:
                current = self._task_from_row(existing[0])
                if current != task:
                    raise DomainValidationError(
                        "task identity already exists with conflicting provenance"
                    )
                return
            self._touch_coordination()
            self._connection.execute(
                """
                INSERT INTO moldock.tasks VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    task.task_id,
                    task.experiment_id,
                    task.receptor_id,
                    task.ligand_id,
                    task.prepared_receptor_id,
                    task.prepared_ligand_id,
                    task.search_space_id,
                ],
            )

        self._run_write(operation)

    def get(self, task_id: str) -> DockingTask | None:
        rows = self._task_rows(task_id)
        if not rows:
            return None
        return self._task_from_row(rows[0])

    def list_for_experiment(self, experiment_id: str) -> tuple[DockingTask, ...]:
        rows = self._connection.execute(
            """
            SELECT
                task_id,
                experiment_id,
                receptor_id,
                ligand_id,
                prepared_receptor_id,
                prepared_ligand_id,
                search_space_id
            FROM moldock.tasks
            WHERE experiment_id = ?
            ORDER BY task_id
            """,
            [experiment_id],
        ).fetchall()
        return tuple(self._task_from_row(row) for row in rows)

    def claim_next(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
        at: datetime,
        *,
        lease_duration: timedelta | None = None,
        allowed_task_ids: AbstractSet[str] | None = None,
    ) -> TaskAttempt | None:
        if not run_id.strip():
            raise DomainValidationError("run_id must not be blank")
        if not worker_id.strip():
            raise DomainValidationError("worker_id must not be blank")
        self._validate_timestamp(at)
        duration = self._lease_duration(lease_duration)
        allowed = (
            None
            if allowed_task_ids is None
            else frozenset(allowed_task_ids)
        )

        def operation() -> TaskAttempt | None:
            tasks = self.list_for_experiment(experiment_id)
            for task in tasks:
                if allowed is not None and task.task_id not in allowed:
                    continue
                history = self._attempts_for_current_transaction(
                    task.task_id,
                    run_id,
                )

                if history and history[-1].status is TaskStatus.RUNNING:
                    latest = history[-1]
                    if not latest.lease_expired(at):
                        continue
                    self._replace_attempt(
                        latest.fail(at, "lease expired", FailureKind.LEASE)
                    )
                    history = self._attempts_for_current_transaction(
                        task.task_id,
                        run_id,
                    )

                if history and history[-1].status is TaskStatus.SUCCEEDED:
                    continue

                attempt_number = len(history) + 1
                previous_failure_kind = (
                    history[-1].failure_kind
                    if history and history[-1].status is TaskStatus.FAILED
                    else None
                )
                if not self._retry_policy.can_attempt(
                    attempt_number,
                    previous_failure_kind,
                ):
                    continue

                self._touch_coordination()
                attempt = TaskAttempt(
                    attempt_id=content_id(
                        "attempt",
                        {
                            "task_id": task.task_id,
                            "run_id": run_id,
                            "attempt_number": attempt_number,
                        },
                    ),
                    task_id=task.task_id,
                    run_id=run_id,
                    attempt_number=attempt_number,
                    worker_id=worker_id,
                    started_at=at,
                    heartbeat_at=at,
                    lease_expires_at=at + duration,
                    status=TaskStatus.RUNNING,
                )
                self._insert_attempt(attempt)
                return attempt
            return None

        if self._before_claim_write is not None:
            self._before_claim_write()
        return self._run_write(operation)

    def heartbeat(
        self,
        attempt_id: str,
        *,
        worker_id: str,
        at: datetime,
        lease_duration: timedelta | None = None,
    ) -> TaskAttempt:
        self._validate_timestamp(at)
        duration = self._lease_duration(lease_duration)

        def operation() -> TaskAttempt:
            self._touch_coordination()
            attempt = self._require_attempt(attempt_id)
            if attempt.worker_id != worker_id:
                raise DomainValidationError("worker does not own this attempt")
            if attempt.lease_expired(at):
                expired = attempt.fail(at, "lease expired", FailureKind.LEASE)
                self._replace_attempt(expired)
                raise _CommitThenRaise(
                    DomainValidationError("attempt lease has expired")
                )
            updated = attempt.heartbeat(
                at=at,
                lease_duration=duration,
            )
            self._replace_attempt(updated)
            return updated

        return self._run_write(operation)

    def succeed(self, attempt_id: str, at: datetime) -> TaskAttempt:
        self._validate_timestamp(at)

        def operation() -> TaskAttempt:
            self._touch_coordination()
            attempt = self._require_attempt(attempt_id)
            if attempt.lease_expired(at):
                expired = attempt.fail(at, "lease expired", FailureKind.LEASE)
                self._replace_attempt(expired)
                raise _CommitThenRaise(
                    DomainValidationError("attempt lease has expired")
                )
            updated = attempt.succeed(at)
            self._replace_attempt(updated)
            return updated

        return self._run_write(operation)

    def fail(
        self,
        attempt_id: str,
        at: datetime,
        error: str,
        failure_kind: FailureKind,
    ) -> TaskAttempt:
        self._validate_timestamp(at)

        def operation() -> TaskAttempt:
            self._touch_coordination()
            attempt = self._require_attempt(attempt_id)
            updated = attempt.fail(at, error, failure_kind)
            self._replace_attempt(updated)
            return updated

        return self._run_write(operation)

    def attempts_for(
        self,
        task_id: str,
        run_id: str,
    ) -> tuple[TaskAttempt, ...]:
        return self._attempts_for_current_transaction(task_id, run_id)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()

    def _run_write(self, operation):
        # SQLite-backed DuckLake catalogs are single-writer. Serialize writes
        # for repository instances sharing this catalog within the current
        # process, while keeping database-level retry/reconnect handling for
        # conflicts with other processes.
        with self._write_lock:
            last_error: Exception | None = None
            for attempt_number in range(self._max_transaction_retries):
                deferred_error: Exception | None = None
                transaction_started = False
                try:
                    self._connection.execute("BEGIN TRANSACTION")
                    transaction_started = True

                    try:
                        result = operation()
                    except _CommitThenRaise as deferred:
                        result = None
                        deferred_error = deferred.error

                    self._connection.execute("COMMIT")
                    transaction_started = False

                    if deferred_error is not None:
                        raise deferred_error
                    return result
                except Exception as exc:
                    if transaction_started:
                        try:
                            self._connection.execute("ROLLBACK")
                        except Exception:
                            pass

                    if deferred_error is not None and exc is deferred_error:
                        raise
                    if not self._is_transaction_conflict(exc):
                        raise

                    last_error = exc
                    if attempt_number + 1 < self._max_transaction_retries:
                        self._reconnect()
                        sleep(self._retry_delay_seconds)

            raise RuntimeError(
                "DuckLake transaction retry budget exhausted"
            ) from last_error

    def _reconnect(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        self._attach()

    def _touch_coordination(self) -> None:
        self._connection.execute(
            """
            UPDATE moldock.claim_coordination
            SET epoch = epoch + 1
            WHERE coordination_key = 'task_repository'
            """
        )

    def _task_rows(self, task_id: str):
        return self._connection.execute(
            """
            SELECT
                task_id,
                experiment_id,
                receptor_id,
                ligand_id,
                prepared_receptor_id,
                prepared_ligand_id,
                search_space_id
            FROM moldock.tasks
            WHERE task_id = ?
            """,
            [task_id],
        ).fetchall()

    @staticmethod
    def _task_from_row(row) -> DockingTask:
        (
            _task_id,
            experiment_id,
            receptor_id,
            ligand_id,
            prepared_receptor_id,
            prepared_ligand_id,
            search_space_id,
        ) = row
        return DockingTask(
            experiment_id=experiment_id,
            receptor_id=receptor_id,
            ligand_id=ligand_id,
            prepared_receptor_id=prepared_receptor_id,
            prepared_ligand_id=prepared_ligand_id,
            search_space_id=search_space_id,
        )

    def _attempts_for_current_transaction(
        self,
        task_id: str,
        run_id: str,
    ) -> tuple[TaskAttempt, ...]:
        rows = self._connection.execute(
            """
            SELECT
                attempt_id,
                task_id,
                run_id,
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                heartbeat_at,
                lease_expires_at,
                status,
                error,
                failure_kind
            FROM moldock.attempts
            WHERE task_id = ? AND run_id = ?
            ORDER BY attempt_number
            """,
            [task_id, run_id],
        ).fetchall()
        return tuple(self._attempt_from_row(row) for row in rows)

    def _require_attempt(self, attempt_id: str) -> TaskAttempt:
        rows = self._connection.execute(
            """
            SELECT
                attempt_id,
                task_id,
                run_id,
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                heartbeat_at,
                lease_expires_at,
                status,
                error,
                failure_kind
            FROM moldock.attempts
            WHERE attempt_id = ?
            """,
            [attempt_id],
        ).fetchall()
        if not rows:
            raise DomainValidationError(f"unknown attempt: {attempt_id}")
        return self._attempt_from_row(rows[0])

    def _insert_attempt(self, attempt: TaskAttempt) -> None:
        self._connection.execute(
            """
            INSERT INTO moldock.attempts
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._attempt_values(attempt),
        )

    def _replace_attempt(self, attempt: TaskAttempt) -> None:
        self._connection.execute(
            "DELETE FROM moldock.attempts WHERE attempt_id = ?",
            [attempt.attempt_id],
        )
        self._insert_attempt(attempt)

    @staticmethod
    def _attempt_values(attempt: TaskAttempt) -> list[object]:
        return [
            attempt.attempt_id,
            attempt.task_id,
            attempt.run_id,
            attempt.attempt_number,
            attempt.worker_id,
            attempt.started_at,
            attempt.finished_at,
            attempt.heartbeat_at,
            attempt.lease_expires_at,
            attempt.status.value,
            attempt.error,
            (
                attempt.failure_kind.value
                if attempt.failure_kind is not None
                else None
            ),
        ]

    @staticmethod
    def _attempt_from_row(row) -> TaskAttempt:
        return TaskAttempt(
            attempt_id=row[0],
            task_id=row[1],
            run_id=row[2],
            attempt_number=row[3],
            worker_id=row[4],
            started_at=row[5],
            finished_at=row[6],
            heartbeat_at=row[7],
            lease_expires_at=row[8],
            status=TaskStatus(row[9]),
            error=row[10],
            failure_kind=(
                FailureKind(row[11])
                if row[11] is not None
                else None
            ),
        )

    @staticmethod
    def _validate_timestamp(value: datetime) -> None:
        if not isinstance(value, datetime):
            raise DomainValidationError("timestamp must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise DomainValidationError(
                "timestamps must be timezone-aware"
            )

    def _lease_duration(
        self,
        lease_duration: timedelta | None,
    ) -> timedelta:
        duration = (
            self._default_lease_duration
            if lease_duration is None
            else lease_duration
        )
        if duration <= timedelta(0):
            raise DomainValidationError("lease_duration must be > 0")
        return duration

    @staticmethod
    def _is_transaction_conflict(error: Exception) -> bool:
        transaction_error = getattr(duckdb, "TransactionException", None)
        if transaction_error is not None and isinstance(error, transaction_error):
            return True
        message = str(error).lower()
        return (
            "conflict" in message
            or "database is locked" in message
            or "serialization" in message
            or ("transaction" in message and "retry" in message)
        )


class _CommitThenRaise(Exception):
    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error
