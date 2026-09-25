from __future__ import annotations

import hashlib
from io import BytesIO

import pytest

from moldock.domain import DomainValidationError
from moldock.storage import ArtifactStore, RustFSArtifactStore


class ClientError(Exception):
    def __init__(self, code: str):
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeRustFSClient:
    def __init__(self):
        self.objects = {}
        self.put_calls = []

    def put_object(self, *, Bucket, Key, Body, Metadata):
        self.put_calls.append((Bucket, Key))
        identity = (Bucket, Key)
        body = bytes(Body)
        self.objects[identity] = {
            "Body": body,
            "Metadata": dict(Metadata),
            "ContentLength": len(body),
        }
        return {"ETag": "fake"}

    def head_object(self, *, Bucket, Key):
        try:
            obj = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError("NoSuchKey") from exc
        return {
            "Metadata": dict(obj["Metadata"]),
            "ContentLength": obj["ContentLength"],
        }

    def get_object(self, *, Bucket, Key):
        try:
            obj = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError("NoSuchKey") from exc
        return {
            "Body": BytesIO(obj["Body"]),
            "Metadata": dict(obj["Metadata"]),
            "ContentLength": obj["ContentLength"],
        }


def make_store(client=None):
    return RustFSArtifactStore(
        bucket="moldock",
        prefix="artifacts",
        client=client or FakeRustFSClient(),
    )


def expected_key(content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"artifacts/sha256/{digest[:2]}/{digest}"


def test_rustfs_store_implements_artifact_store_contract():
    assert isinstance(make_store(), ArtifactStore)


def test_put_writes_content_addressed_object_and_returns_restart_safe_uri():
    client = FakeRustFSClient()
    store = make_store(client)

    blob = store.put(b"pose-bytes")

    digest = hashlib.sha256(b"pose-bytes").hexdigest()
    key = expected_key(b"pose-bytes")
    assert blob.blob_id == f"blob_{digest}"
    assert blob.sha256 == digest
    assert blob.size_bytes == len(b"pose-bytes")
    assert blob.uri == f"s3://moldock/{key}"
    assert client.objects[("moldock", key)]["Body"] == b"pose-bytes"
    assert client.objects[("moldock", key)]["Metadata"] == {
        "sha256": digest,
        "size_bytes": str(len(b"pose-bytes")),
    }


def test_identical_content_reuses_verified_object_without_second_write():
    client = FakeRustFSClient()
    store = make_store(client)

    first = store.put(b"same")
    second = store.put(b"same")

    assert first == second
    assert len(client.objects) == 1
    assert len(client.put_calls) == 1


def test_existing_object_is_verified_before_reuse():
    client = FakeRustFSClient()
    store = make_store(client)
    blob = store.put(b"same")
    key = blob.uri.removeprefix("s3://moldock/")

    client.objects[("moldock", key)]["Metadata"]["sha256"] = "0" * 64

    with pytest.raises(DomainValidationError, match="integrity"):
        store.put(b"same")


def test_get_and_read_verify_object_integrity():
    client = FakeRustFSClient()
    store = make_store(client)
    blob = store.put(b"pose-bytes")

    assert store.get(blob.blob_id) == b"pose-bytes"
    assert store.read(blob.uri) == b"pose-bytes"

    key = blob.uri.removeprefix("s3://moldock/")
    client.objects[("moldock", key)]["Body"] = b"corrupted"
    client.objects[("moldock", key)]["ContentLength"] = len(b"corrupted")

    with pytest.raises(DomainValidationError, match="integrity"):
        store.get(blob.blob_id)


def test_new_store_instance_can_read_existing_uri():
    client = FakeRustFSClient()
    first = make_store(client)
    blob = first.put(b"persistent")

    restarted = make_store(client)

    assert restarted.read(blob.uri) == b"persistent"
    assert restarted.get(blob.blob_id) == b"persistent"


def test_get_rejects_unknown_blob():
    store = make_store()

    with pytest.raises(DomainValidationError, match="unknown blob"):
        store.get("blob_" + "0" * 64)


@pytest.mark.parametrize(
    "uri",
    [
        "memory://blobs/blob_abc",
        "s3://other-bucket/artifacts/sha256/aa/" + "a" * 64,
        "s3://moldock/other-prefix/" + "a" * 64,
    ],
)
def test_read_rejects_foreign_or_unsupported_uri(uri):
    store = make_store()

    with pytest.raises(DomainValidationError, match="unsupported RustFS artifact URI"):
        store.read(uri)


def test_put_rejects_non_bytes():
    store = make_store()

    with pytest.raises(DomainValidationError, match="bytes"):
        store.put("not-bytes")


def test_constructor_rejects_blank_bucket_and_unsafe_prefix():
    with pytest.raises(DomainValidationError):
        RustFSArtifactStore(bucket="", client=FakeRustFSClient())

    with pytest.raises(DomainValidationError):
        RustFSArtifactStore(
            bucket="moldock",
            prefix="../escape",
            client=FakeRustFSClient(),
        )


def test_constructor_builds_path_style_sigv4_rustfs_client():
    store = RustFSArtifactStore(
        bucket=" moldock ",
        endpoint_url="http://127.0.0.1:9000",
        access_key_id="access",
        secret_access_key="secret",
        region_name="us-east-1",
    )

    assert store._bucket == "moldock"
    assert store._client.meta.endpoint_url == "http://127.0.0.1:9000"
    assert store._client.meta.config.signature_version == "s3v4"
    assert store._client.meta.config.s3["addressing_style"] == "path"
