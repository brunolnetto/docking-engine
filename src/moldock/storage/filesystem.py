from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlparse

from moldock.domain import DomainValidationError, StoredBlob


def _fsync_directory(path: Path) -> None:
    """Persist directory-entry updates when the platform supports it."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        if os.name == "nt":
            return
        raise

    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    """Create a directory hierarchy and fsync every new parent entry."""

    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent

    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        _fsync_directory(directory.parent)


class FilesystemArtifactStore:
    """Content-addressed artifact storage rooted in a local directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._blob_root = self._root / "sha256"
        _mkdir_durable(self._blob_root)

    def put(self, content: bytes) -> StoredBlob:
        if not isinstance(content, bytes):
            raise DomainValidationError("artifact content must be bytes")

        sha256 = hashlib.sha256(content).hexdigest()
        blob_id = f"blob_{sha256}"
        path = self._path_for_digest(sha256)
        _mkdir_durable(path.parent)

        if path.exists():
            self._verify(path, sha256)
        else:
            fd, temporary_name = tempfile.mkstemp(
                prefix=".moldock-",
                dir=path.parent,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                _fsync_directory(path.parent)
            finally:
                if temporary.exists():
                    temporary.unlink()
            self._verify(path, sha256)

        return StoredBlob(
            blob_id=blob_id,
            uri=path.as_uri(),
            sha256=sha256,
            size_bytes=len(content),
        )

    def get(self, blob_id: str) -> bytes:
        prefix = "blob_"
        if not blob_id.startswith(prefix):
            raise DomainValidationError(f"unknown blob: {blob_id}")
        digest = blob_id[len(prefix):]
        if len(digest) != 64 or any(
            char not in "0123456789abcdef"
            for char in digest.lower()
        ):
            raise DomainValidationError(f"unknown blob: {blob_id}")

        path = self._path_for_digest(digest.lower())
        if not path.is_file():
            raise DomainValidationError(f"unknown blob: {blob_id}")

        return self._verify(path, digest.lower())

    def read(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise DomainValidationError(
                f"unsupported filesystem artifact URI: {uri}"
            )

        path = Path(unquote(parsed.path)).resolve()
        try:
            path.relative_to(self._blob_root)
        except ValueError as exc:
            raise DomainValidationError(
                f"unsupported filesystem artifact URI: {uri}"
            ) from exc

        digest = path.name.lower()
        if (
            len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or path != self._path_for_digest(digest)
        ):
            raise DomainValidationError(
                f"unsupported filesystem artifact URI: {uri}"
            )

        return self.get(f"blob_{digest}")

    def _path_for_digest(self, digest: str) -> Path:
        return (
            self._blob_root
            / digest[:2]
            / digest[2:4]
            / digest
        )

    @staticmethod
    def _verify(path: Path, expected_sha256: str) -> bytes:
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected_sha256:
            raise DomainValidationError(
                f"artifact integrity check failed: {path}"
            )
        return content
