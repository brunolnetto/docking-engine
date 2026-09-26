from __future__ import annotations

from moldock.backends import DockingBackend, DockingBackendTimeoutError
from moldock.domain import (
    ArtifactMetadata,
    ExecutionFailure,
    FailureKind,
    TaskAttempt,
    content_id,
)
from moldock.repositories import ArtifactRepository, TaskRepository
from moldock.results import (
    NullScientificResultInterpreter,
    ScientificResultInterpreter,
)
from moldock.storage import ArtifactStore

from .resolver import DockingInputResolver


def _wrap_failure(kind: FailureKind, exc: Exception) -> ExecutionFailure:
    if isinstance(exc, ExecutionFailure):
        return exc
    return ExecutionFailure(
        kind,
        f"{type(exc).__name__}: {exc}",
    )


class TaskExecutor:
    """Execute a previously claimed attempt without changing attempt state."""

    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        artifact_repository: ArtifactRepository,
        artifact_store: ArtifactStore,
        input_resolver: DockingInputResolver,
        backend: DockingBackend,
        result_interpreter: ScientificResultInterpreter | None = None,
    ) -> None:
        self._tasks = task_repository
        self._artifacts = artifact_repository
        self._store = artifact_store
        self._resolver = input_resolver
        self._backend = backend
        self._interpreter = (
            result_interpreter or NullScientificResultInterpreter()
        )

    def execute(self, attempt: TaskAttempt) -> None:
        task = self._tasks.get(attempt.task_id)
        if task is None:
            raise ExecutionFailure(
                FailureKind.INFRASTRUCTURE,
                f"claimed task not found: {attempt.task_id}",
            )

        try:
            request = self._resolver.resolve(task)
        except Exception as exc:
            raise _wrap_failure(FailureKind.INPUT, exc) from exc

        try:
            result = self._backend.execute(request)
        except DockingBackendTimeoutError as exc:
            raise _wrap_failure(FailureKind.TIMEOUT, exc) from exc
        except Exception as exc:
            raise _wrap_failure(FailureKind.BACKEND, exc) from exc

        for index, output in enumerate(result.artifacts, start=1):
            try:
                blob = self._store.put(output.content)
                artifact = ArtifactMetadata(
                    artifact_id=content_id(
                        "artifact",
                        {
                            "attempt_id": attempt.attempt_id,
                            "index": index,
                            "kind": output.kind,
                            "blob_id": blob.blob_id,
                        },
                    ),
                    uri=blob.uri,
                    sha256=blob.sha256,
                    size_bytes=blob.size_bytes,
                    media_type=output.media_type,
                    kind=output.kind,
                    producer_attempt_id=attempt.attempt_id,
                )
                self._artifacts.register(artifact)
            except Exception as exc:
                raise _wrap_failure(FailureKind.ARTIFACT, exc) from exc

            try:
                contextual = getattr(
                    self._interpreter,
                    "interpret_with_request",
                    None,
                )
                if callable(contextual):
                    contextual(
                        task_id=task.task_id,
                        artifact=artifact,
                        request=request,
                    )
                else:
                    self._interpreter.interpret(
                        task_id=task.task_id,
                        artifact=artifact,
                    )
            except Exception as exc:
                raise _wrap_failure(FailureKind.INTERPRETATION, exc) from exc
