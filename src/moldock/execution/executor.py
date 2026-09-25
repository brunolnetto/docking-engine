from __future__ import annotations

from moldock.backends import DockingBackend
from moldock.domain import ArtifactMetadata, TaskAttempt, content_id
from moldock.repositories import ArtifactRepository, TaskRepository
from moldock.results import (
    NullScientificResultInterpreter,
    ScientificResultInterpreter,
)
from moldock.storage import ArtifactStore

from .resolver import DockingInputResolver


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
            raise RuntimeError(f"claimed task not found: {attempt.task_id}")

        request = self._resolver.resolve(task)
        result = self._backend.execute(request)

        for index, output in enumerate(result.artifacts, start=1):
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
            self._interpreter.interpret(
                task_id=task.task_id,
                artifact=artifact,
            )
