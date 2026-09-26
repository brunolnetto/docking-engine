from threading import RLock

import pytest

from moldock.domain import DomainValidationError
from moldock.repositories.ducklake_base import DuckLakeRepositoryBase
import moldock.repositories.ducklake_base as ducklake_base_module


class RecordingConnection:
    def __init__(self, *, rollback_error=None, close_error=None):
        self.calls = []
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.closed = False

    def execute(self, query):
        statement = query.strip().upper()
        self.calls.append(statement)
        if statement == "ROLLBACK" and self.rollback_error is not None:
            raise self.rollback_error
        return self

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def bare_base(*, retries=2, connection=None):
    repo = object.__new__(DuckLakeRepositoryBase)
    repo._write_lock = RLock()
    repo._max_transaction_retries = retries
    repo._retry_delay_seconds = 0
    repo._connection = connection or RecordingConnection()
    return repo


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("transaction conflict"),
        RuntimeError("database is locked"),
        RuntimeError("serialization conflict"),
        RuntimeError("serialization failure"),
        RuntimeError("transaction must retry"),
    ],
)
def test_ducklake_base_recognizes_retryable_conflict_messages(error):
    assert DuckLakeRepositoryBase._is_transaction_conflict(error) is True


def test_ducklake_base_does_not_retry_domain_validation_errors():
    error = DomainValidationError("transaction conflict")

    assert DuckLakeRepositoryBase._is_transaction_conflict(error) is False


def test_ducklake_base_does_not_retry_unrelated_errors():
    assert (
        DuckLakeRepositoryBase._is_transaction_conflict(
            RuntimeError("syntax error")
        )
        is False
    )


def test_run_transaction_rolls_back_and_reraises_non_conflict():
    connection = RecordingConnection()
    repo = bare_base(connection=connection)

    with pytest.raises(RuntimeError, match="boom"):
        repo._run_transaction(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            touch_coordination=False,
        )

    assert "BEGIN TRANSACTION" in connection.calls
    assert "ROLLBACK" in connection.calls


def test_run_transaction_ignores_rollback_failure_for_original_error():
    connection = RecordingConnection(
        rollback_error=RuntimeError("rollback failed")
    )
    repo = bare_base(connection=connection)

    with pytest.raises(ValueError, match="operation failed"):
        repo._run_transaction(
            lambda: (_ for _ in ()).throw(ValueError("operation failed")),
            touch_coordination=False,
        )


def test_run_transaction_reconnects_and_retries_conflict(monkeypatch):
    first = RecordingConnection()
    second = RecordingConnection()
    repo = bare_base(connection=first)
    calls = {"operation": 0, "reconnect": 0}

    def operation():
        calls["operation"] += 1
        if calls["operation"] == 1:
            raise RuntimeError("database is locked")
        return "ok"

    def reconnect():
        calls["reconnect"] += 1
        repo._connection = second

    monkeypatch.setattr(repo, "_reconnect", reconnect)

    assert repo._run_transaction(operation, touch_coordination=False) == "ok"
    assert calls == {"operation": 2, "reconnect": 1}
    assert "COMMIT" in second.calls


def test_run_transaction_exhausts_retry_budget(monkeypatch):
    repo = bare_base(retries=2)
    monkeypatch.setattr(repo, "_reconnect", lambda: None)

    with pytest.raises(
        RuntimeError,
        match="transaction retry budget exhausted",
    ):
        repo._run_transaction(
            lambda: (_ for _ in ()).throw(
                RuntimeError("serialization conflict")
            ),
            touch_coordination=False,
        )


def test_reconnect_tolerates_close_failure_and_attaches_again(monkeypatch):
    connection = RecordingConnection(
        close_error=RuntimeError("close failed")
    )
    repo = bare_base(connection=connection)
    attached = []

    monkeypatch.setattr(repo, "_attach", lambda: attached.append(True))

    repo._reconnect()

    assert connection.closed is True
    assert repo._connection is None
    assert attached == [True]


def test_close_is_idempotent_when_connection_is_absent():
    repo = bare_base()
    repo._connection = None

    repo.close()

    assert repo._connection is None


def test_attach_retries_conflict_then_succeeds(monkeypatch, tmp_path):
    class AttachConnection(RecordingConnection):
        def __init__(self, *, fail=False):
            super().__init__()
            self.fail = fail

        def execute(self, query):
            statement = query.strip().upper()
            self.calls.append(statement)
            if self.fail and statement == "INSTALL SQLITE":
                raise RuntimeError("database is locked")
            return self

    first = AttachConnection(fail=True)
    second = AttachConnection()
    connections = iter([first, second])

    monkeypatch.setattr(
        ducklake_base_module.duckdb,
        "connect",
        lambda: next(connections),
    )

    repo = object.__new__(DuckLakeRepositoryBase)
    repo._catalog_path = tmp_path / "catalog.sqlite"
    repo._data_path = tmp_path / "data"
    repo._max_transaction_retries = 2
    repo._retry_delay_seconds = 0
    repo._connection = None

    repo._attach()

    assert first.closed is True
    assert repo._connection is second
    assert any(call.startswith("ATTACH") for call in second.calls)


def test_attach_exhausts_conflict_retry_budget(monkeypatch, tmp_path):
    class AlwaysFailConnection(RecordingConnection):
        def execute(self, query):
            self.calls.append(query.strip().upper())
            raise RuntimeError("database is locked")

    created = []

    def connect():
        connection = AlwaysFailConnection()
        created.append(connection)
        return connection

    monkeypatch.setattr(
        ducklake_base_module.duckdb,
        "connect",
        connect,
    )

    repo = object.__new__(DuckLakeRepositoryBase)
    repo._catalog_path = tmp_path / "catalog.sqlite"
    repo._data_path = tmp_path / "data"
    repo._max_transaction_retries = 2
    repo._retry_delay_seconds = 0
    repo._connection = None

    with pytest.raises(RuntimeError, match="attach retry budget exhausted"):
        repo._attach()

    assert len(created) == 2
    assert all(connection.closed for connection in created)



def test_ducklake_base_constructor_rejects_missing_optional_dependency(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(ducklake_base_module, "duckdb", None)

    with pytest.raises(RuntimeError, match="optional dependency"):
        DuckLakeRepositoryBase(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"max_transaction_retries": 0}, "max_transaction_retries"),
        ({"retry_delay_seconds": -1}, "retry_delay_seconds"),
    ],
)
def test_ducklake_base_constructor_validates_retry_configuration(
    tmp_path,
    kwargs,
    match,
):
    with pytest.raises(DomainValidationError, match=match):
        DuckLakeRepositoryBase(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
            **kwargs,
        )


def test_attach_closes_connection_and_propagates_non_conflict(
    monkeypatch,
    tmp_path,
):
    class FailingConnection(RecordingConnection):
        def execute(self, query):
            self.calls.append(query.strip().upper())
            raise RuntimeError("syntax error")

    connection = FailingConnection()
    monkeypatch.setattr(
        ducklake_base_module.duckdb,
        "connect",
        lambda: connection,
    )
    repo = object.__new__(DuckLakeRepositoryBase)
    repo._catalog_path = tmp_path / "catalog.sqlite"
    repo._data_path = tmp_path / "data"
    repo._max_transaction_retries = 2
    repo._retry_delay_seconds = 0
    repo._connection = None

    with pytest.raises(RuntimeError, match="syntax error"):
        repo._attach()

    assert connection.closed is True


def test_bootstrap_coordination_rejects_duplicate_shared_rows():
    class Result:
        def __init__(self, rows=()):
            self._rows = rows

        def fetchall(self):
            return list(self._rows)

    class CoordinationConnection(RecordingConnection):
        def execute(self, query):
            statement = query.strip().upper()
            self.calls.append(statement)
            if statement.startswith("SELECT COORDINATION_KEY"):
                return Result(
                    [
                        ("shared_adapters", 0),
                        ("shared_adapters", 1),
                    ]
                )
            return Result()

    repo = bare_base(connection=CoordinationConnection())

    with pytest.raises(RuntimeError, match="must be unique"):
        repo._bootstrap_coordination()


def test_run_transaction_retries_conflict_before_transaction_starts(
    monkeypatch,
):
    first = RecordingConnection()
    second = RecordingConnection()
    original_first_execute = first.execute
    state = {"failed": False}

    def first_execute(query):
        statement = query.strip().upper()
        if statement == "BEGIN TRANSACTION" and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("database is locked")
        return original_first_execute(query)

    first.execute = first_execute
    repo = bare_base(connection=first)
    reconnects = []

    def reconnect():
        reconnects.append(True)
        repo._connection = second

    monkeypatch.setattr(repo, "_reconnect", reconnect)

    assert repo._run_transaction(
        lambda: "ok",
        touch_coordination=False,
    ) == "ok"
    assert reconnects == [True]
    assert "ROLLBACK" not in first.calls


def test_reconnect_attaches_when_connection_is_already_absent(monkeypatch):
    repo = bare_base()
    repo._connection = None
    attached = []
    monkeypatch.setattr(repo, "_attach", lambda: attached.append(True))

    repo._reconnect()

    assert attached == [True]
