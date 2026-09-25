from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from moldock.domain import DomainValidationError, StoredBlob


_BLOB_ID_RE = re.compile(r"^blob_([0-9a-f]{64})$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
_ALREADY_EXISTS_CODES = {
    "412",
    "PreconditionFailed",
    "ConditionalRequestConflict",
}


class RustFSArtifactStore:
    """Content-addressed artifact storage backed by RustFS's S3-compatible API."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "artifacts",
        client=None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        if not bucket.strip():
            raise DomainValidationError("bucket must not be blank")

        normalized_prefix = prefix.strip("/")
        if (
            not normalized_prefix
            or normalized_prefix in {".", ".."}
            or any(part in {".", ".."} for part in normalized_prefix.split("/"))
        ):
            raise DomainValidationError("prefix must be a safe non-blank object prefix")

        if client is None:
            if endpoint_url is None or not endpoint_url.strip():
                raise DomainValidationError(
                    "endpoint_url is required when no RustFS client is supplied"
                )
            client = self._create_client(
                endpoint_url=endpoint_url,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region_name=region_name,
            )

        self._bucket = bucket.strip()
        self._prefix = normalized_prefix
        self._client = client

    @staticmethod
    def _create_client(
        *,
        endpoint_url: str,
        access_key_id: str | None,
        secret_access_key: str | None,
        region_name: str,
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise RuntimeError(
                'RustFSArtifactStore requires the "rustfs" optional dependency'
            ) from exc

        kwargs = {
            "service_name": "s3",
            "endpoint_url": endpoint_url,
            "region_name": region_name,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        }
        if access_key_id is not None:
            kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key is not None:
            kwargs["aws_secret_access_key"] = secret_access_key
        return boto3.client(**kwargs)

    def put(self, content: bytes) -> StoredBlob:
        if not isinstance(content, bytes):
            raise DomainValidationError("artifact content must be bytes")

        digest = hashlib.sha256(content).hexdigest()
        blob_id = f"blob_{digest}"
        key = self._key_for_digest(digest)
        metadata = {
            "sha256": digest,
            "size_bytes": str(len(content)),
        }

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                Metadata=metadata,
                IfNoneMatch="*",
            )
        except Exception as exc:
            if not self._is_error_code(exc, _ALREADY_EXISTS_CODES):
                raise
            self._read_verified(
                key=key,
                expected_digest=digest,
                expected_size=len(content),
                unknown_message=f"unknown blob: {blob_id}",
            )

        return StoredBlob(
            blob_id=blob_id,
            uri=self._uri_for_key(key),
            sha256=digest,
            size_bytes=len(content),
        )

    def get(self, blob_id: str) -> bytes:
        match = _BLOB_ID_RE.fullmatch(blob_id)
        if match is None:
            raise DomainValidationError(f"invalid blob id: {blob_id}")

        digest = match.group(1)
        key = self._key_for_digest(digest)
        return self._read_verified(
            key=key,
            expected_digest=digest,
            expected_size=None,
            unknown_message=f"unknown blob: {blob_id}",
        )

    def read(self, uri: str) -> bytes:
        key, digest = self._parse_uri(uri)
        return self._read_verified(
            key=key,
            expected_digest=digest,
            expected_size=None,
            unknown_message=f"unknown RustFS artifact URI: {uri}",
        )

    def _read_verified(
        self,
        *,
        key: str,
        expected_digest: str,
        expected_size: int | None,
        unknown_message: str,
    ) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=key,
            )
        except Exception as exc:
            if self._is_error_code(exc, _NOT_FOUND_CODES):
                raise DomainValidationError(unknown_message) from exc
            raise

        body = response["Body"].read()
        if not isinstance(body, bytes):
            body = bytes(body)

        actual_digest = hashlib.sha256(body).hexdigest()
        metadata = {
            str(key).lower(): str(value)
            for key, value in (response.get("Metadata") or {}).items()
        }
        content_length = response.get("ContentLength", len(body))
        metadata_digest = metadata.get("sha256")
        metadata_size = metadata.get("size_bytes")

        invalid = (
            actual_digest != expected_digest
            or content_length != len(body)
            or metadata_digest != expected_digest
            or metadata_size != str(len(body))
            or (expected_size is not None and len(body) != expected_size)
        )
        if invalid:
            raise DomainValidationError(
                f"RustFS artifact integrity check failed for s3://{self._bucket}/{key}"
            )
        return body

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self._bucket:
            raise DomainValidationError(f"unsupported RustFS artifact URI: {uri}")

        key = parsed.path.lstrip("/")
        prefix = f"{self._prefix}/sha256/"
        if not key.startswith(prefix):
            raise DomainValidationError(f"unsupported RustFS artifact URI: {uri}")

        remainder = key[len(prefix):]
        parts = remainder.split("/")
        if len(parts) != 2:
            raise DomainValidationError(f"unsupported RustFS artifact URI: {uri}")
        shard, digest = parts
        if (
            _SHA256_RE.fullmatch(digest) is None
            or shard != digest[:2]
        ):
            raise DomainValidationError(f"unsupported RustFS artifact URI: {uri}")
        return key, digest

    def _key_for_digest(self, digest: str) -> str:
        return f"{self._prefix}/sha256/{digest[:2]}/{digest}"

    def _uri_for_key(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    @staticmethod
    def _is_error_code(error: Exception, accepted: set[str]) -> bool:
        response = getattr(error, "response", None)
        if not isinstance(response, dict):
            return False
        error_payload = response.get("Error")
        if not isinstance(error_payload, dict):
            return False
        code = str(error_payload.get("Code", ""))
        return code in accepted
