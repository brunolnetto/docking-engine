# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

## Current architecture

```text
Experiment
   ↓
TaskPlanner
   ↓
TaskManifest
   ↓
TaskRepository
   ↓ claim
Worker
   ↓
DockingBackend
   ↓
DockingResult
   ↓
ArtifactStore + ArtifactRepository
   ↓
TaskAttempt success/failure
```

### Execution plane

- `DockingBackend`: runtime-checkable computational boundary.
- `FakeDockingBackend`: deterministic backend used for orchestration tests.
- `DockingResult`: backend result containing zero or more output artifacts.
- `ArtifactStore`: byte-storage contract.
- `MemoryArtifactStore`: content-addressed in-memory blob store with deduplication.
- `Worker.run_once()`: claim, execute, persist output metadata, and finalize attempts.

Blob identity is based on content, while artifact identity is based on execution provenance. Two outputs with identical bytes can therefore share one blob without losing their distinct artifact records.

The current worker marks attempts failed when either backend execution or artifact persistence raises an exception. Failed attempts remain retryable through the task repository.

### Still intentionally absent

- AutoDock Vina integration
- receptor/ligand preparation tooling
- PostgreSQL
- S3/MinIO
- leases and heartbeats
- distributed worker orchestration
- score/ranking refinement

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Coverage is configured in `pyproject.toml` with a **95% minimum** and runs in CI on Python 3.11 through 3.14.
