from pathlib import Path

import pytest

from moldock.domain import DomainValidationError
from moldock.storage import ArtifactStore, FilesystemArtifactStore
import moldock.storage.filesystem as filesystem_module


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


def test_get_returns_the_same_bytes_that_passed_integrity_check(
    tmp_path,
    monkeypatch,
):
    store = FilesystemArtifactStore(tmp_path)
    blob = store.put(b"original")
    digest = blob.sha256
    path = (
        tmp_path
        / "sha256"
        / digest[:2]
        / digest[2:4]
        / digest
    ).resolve()
    original_read_bytes = Path.read_bytes
    reads = 0

    def changing_read_bytes(self):
        nonlocal reads
        if self.resolve() == path:
            reads += 1
            if reads == 1:
                return b"original"
            return b"changed-after-verification"
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", changing_read_bytes)

    assert store.get(blob.blob_id) == b"original"
    assert reads == 1


def test_put_fsyncs_directory_entries_before_returning(
    tmp_path,
    monkeypatch,
):
    synced = []

    monkeypatch.setattr(
        filesystem_module,
        "_fsync_directory",
        lambda path: synced.append(Path(path).resolve()),
        raising=False,
    )

    store = FilesystemArtifactStore(tmp_path)
    blob = store.put(b"durable")
    digest = blob.sha256

    root = tmp_path.resolve()
    sha_root = root / "sha256"
    first_shard = sha_root / digest[:2]
    second_shard = first_shard / digest[2:4]

    assert root in synced
    assert sha_root in synced
    assert first_shard in synced
    assert second_shard in synced



@pytest.mark.parametrize(
    "blob_id",
    [
        "not-a-blob",
        "blob_short",
        "blob_" + "g" * 64,
    ],
)
def test_filesystem_get_rejects_malformed_blob_ids(tmp_path, blob_id):
    store = FilesystemArtifactStore(tmp_path)

    with pytest.raises(DomainValidationError, match="unknown blob"):
        store.get(blob_id)


def test_filesystem_read_rejects_non_file_scheme(tmp_path):
    store = FilesystemArtifactStore(tmp_path)

    with pytest.raises(DomainValidationError, match="unsupported"):
        store.read("s3://bucket/key")


def test_filesystem_read_rejects_noncanonical_path_inside_root(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    malformed = (tmp_path / "sha256" / ("a" * 64)).resolve()

    with pytest.raises(DomainValidationError, match="unsupported"):
        store.read(malformed.as_uri())


def test_filesystem_read_rejects_invalid_digest_filename(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    malformed = (tmp_path / "sha256" / "aa" / "bb" / ("g" * 64)).resolve()

    with pytest.raises(DomainValidationError, match="unsupported"):
        store.read(malformed.as_uri())


def test_put_cleans_temporary_file_when_replace_fails(tmp_path, monkeypatch):
    store = FilesystemArtifactStore(tmp_path)

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(filesystem_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.put(b"payload")

    assert not list((tmp_path / "sha256").rglob(".moldock-*"))


def test_fsync_directory_windows_ignores_open_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(filesystem_module.os, "name", "nt")
    monkeypatch.setattr(
        filesystem_module.os,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unsupported")),
    )

    filesystem_module._fsync_directory(tmp_path)


def test_fsync_directory_non_windows_propagates_open_failure(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(filesystem_module.os, "name", "posix")
    monkeypatch.setattr(
        filesystem_module.os,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")),
    )

    with pytest.raises(OSError, match="boom"):
        filesystem_module._fsync_directory(tmp_path)
