from moldock.repositories import (
    ArtifactRepository,
    InMemoryArtifactRepository,
    InMemoryTaskRepository,
    TaskRepository,
)


def test_in_memory_task_repository_implements_contract():
    assert isinstance(InMemoryTaskRepository(), TaskRepository)


def test_in_memory_artifact_repository_implements_contract():
    assert isinstance(InMemoryArtifactRepository(), ArtifactRepository)
