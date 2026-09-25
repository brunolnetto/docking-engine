# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

## Leased execution lifecycle

Execution is split into three responsibilities:

```text
LeasedWorkerRunner
    │
    ├── claim task + lease
    ├── start heartbeat
    │
    ▼
TaskExecutor
    │
    ├── resolve prepared inputs
    ├── execute docking backend
    ├── persist artifacts
    └── interpret scientific results
    │
    ▼
LeasedWorkerRunner
    ├── stop heartbeat
    └── succeed / fail attempt
```

`LeaseHeartbeat` renews the attempt lease on a background daemon thread. The heartbeat interval must be positive and shorter than the lease duration.

If heartbeat renewal fails, the attempt cannot be committed as successful. The runner re-reads the latest attempt state before finalization so a repository-side lease-expiry transition is preserved.

`LeasedWorkerRunner.stop()` is graceful: it prevents future claims but does not cancel the currently executing task.

`Worker` remains as a compatibility facade around the leased runner.

## Storage boundary

The execution runner depends only on repository protocols, so the lifecycle is independent of the persistence implementation. This is intended to support the upcoming DuckLake concurrency spike and repository adapter.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```
