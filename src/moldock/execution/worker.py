from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from moldock.backends import DockingBackend
from moldock.domain import ArtifactMetadata, TaskAttempt, content_id
from moldock.repositories import ArtifactRepository, TaskRepository
from moldock.storage import ArtifactStore

from .resolver import DockingInputResolver


class Worker:
    def __init__(
        self,
        *,
        task_repository: TaskRepository,
        artifact_repository: ArtifactRepository,
        artifact_store: ArtifactStore,
        input_resolver: DockingInputResolver,
        backend: DockingBackend,
        clock: Callable[[], datetime],
    ) -> None:
        self._tasks = task_repository
        self._artifacts = artifact_repository
        self._store = artifact_store
        self._resolver = input_resolver
        self._backend = backend
        self._clock = clock

    def run_once(
        self,
        experiment_id: str,
        run_id: str,
        worker_id: str,
    ) -> TaskAttempt | None:
        started_at = self._clock()
        attempt = self._tasks.claim_next(
            experiment_id=experiment_id,
            run_id=run_id,
            worker_id=worker_id,
            at=started_at,
        )
        if attempt is None:
            return None

        task = self._tasks.get(attempt.task_id)
        if task is None:
            return self._tasks.fail(
                attempt.attempt_id,
                self._clock(),
                f"RuntimeError: claimed task not found: {attempt.task_id}",
            )

        try:
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
        except Exception as exc:
            return self._tasks.fail(
                attempt.attempt_id,
                self._clock(),
                f"{type(exc).__name__}: {exc}",
            )

        return self._tasks.succeed(attempt.attempt_id, self._clock())
