from __future__ import annotations

from typing import Protocol, runtime_checkable

from moldock.run_manifest import RunManifest


@runtime_checkable
class RunManifestRepository(Protocol):
    def register(self, manifest: RunManifest) -> None: ...

    def get(self, run_id: str) -> RunManifest | None: ...
