from pathlib import Path

import pytest

from moldock.domain import DomainValidationError
from moldock.storage import ArtifactStore, FilesystemArtifactStore


def test_filesystem_store_implements_contract(tmp_path):
    assert isinstance(FilesystemArtifactStore(tmp_path), ArtifactStore)


def test_put_survives_store_restart(tmp_path):
    first = FilesystemArtifactStore(tmp_path)
    blob = first.put(b"pose-bytes")

    reopened = FilesystemArtifactStore(tmp_path)

    assert reopened.get(blob.blob_id) == b"pose-bytes"
    assert reopened.read(blob.uri) == b"pose-bytes"


def test_identical_content_is_deduplicated(tmp_path):
    store = FilesystemArtifactStore(tmp_path)

    first = store.put(b"same")
    second = store.put(b"same")

    assert first == second
    assert len(tuple((tmp_path / "sha256").rglob("*"))) >= 1


def test_content_is_sharded_by_sha256_prefix(tmp_path):
    store = FilesystemArtifactStore(tmp_path)

    blob = store.put(b"payload")
    digest = blob.sha256
    expected = tmp_path / "sha256" / digest[:2] / digest[2:4] / digest

    assert expected.read_bytes() == b"payload"


def test_corrupted_blob_is_rejected_on_read(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    blob = store.put(b"original")
    digest = blob.sha256
    path = tmp_path / "sha256" / digest[:2] / digest[2:4] / digest
    path.write_bytes(b"corrupted")

    with pytest.raises(DomainValidationError, match="integrity"):
        store.get(blob.blob_id)


def test_store_rejects_non_bytes_and_unknown_blob(tmp_path):
    store = FilesystemArtifactStore(tmp_path)

    with pytest.raises(DomainValidationError):
        store.put("not-bytes")

    with pytest.raises(DomainValidationError, match="unknown blob"):
        store.get("blob_" + "0" * 64)


def test_store_rejects_uri_outside_its_root(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    outside = Path(tmp_path).parent / "other" / ("a" * 64)

    with pytest.raises(DomainValidationError, match="unsupported"):
        store.read(outside.as_uri())
