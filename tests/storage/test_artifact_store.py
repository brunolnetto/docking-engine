import pytest

from moldock.domain import DomainValidationError
from moldock.storage import ArtifactStore, MemoryArtifactStore


def test_memory_store_implements_artifact_store_contract():
    assert isinstance(MemoryArtifactStore(), ArtifactStore)


def test_put_and_get_round_trip():
    store = MemoryArtifactStore()

    blob = store.put(b"pose-bytes")

    assert blob.size_bytes == len(b"pose-bytes")
    assert len(blob.sha256) == 64
    assert blob.uri.startswith("memory://blobs/")
    assert store.get(blob.blob_id) == b"pose-bytes"
    assert store.read(blob.uri) == b"pose-bytes"


def test_identical_content_is_deduplicated():
    store = MemoryArtifactStore()

    first = store.put(b"same")
    second = store.put(b"same")

    assert first == second
    assert store.blob_count == 1


def test_different_content_has_different_identity():
    store = MemoryArtifactStore()

    assert store.put(b"a").blob_id != store.put(b"b").blob_id


def test_put_rejects_non_bytes():
    store = MemoryArtifactStore()

    with pytest.raises(DomainValidationError):
        store.put("not-bytes")


def test_get_rejects_unknown_blob():
    store = MemoryArtifactStore()

    with pytest.raises(DomainValidationError, match="unknown blob"):
        store.get("blob_missing")


def test_read_rejects_unsupported_uri():
    store = MemoryArtifactStore()

    with pytest.raises(DomainValidationError, match="unsupported"):
        store.read("s3://bucket/blob")
