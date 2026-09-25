# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

## Execution resilience

Task attempts now carry an execution lease:

- `heartbeat_at`
- `lease_expires_at`

A running attempt with an active lease cannot be reclaimed. When the lease expires, the repository marks that attempt failed with `lease expired` and may create the next attempt according to the configured `RetryPolicy`.

`RetryPolicy(max_attempts=N)` bounds attempts within a run.

The in-memory repository provides these semantics under a process-local lock. A PostgreSQL implementation can preserve the same contract with transactional claiming and row locking.

Workers can renew ownership through:

```python
repo.heartbeat(
    attempt_id,
    worker_id="worker-1",
    at=now,
    lease_duration=timedelta(minutes=5),
)
```

Terminal attempts clear lease state.

## Current architecture

```text
Experiment
  ↓
TaskPlanner
  ↓
TaskRepository
  ↓ claim + lease
Worker
  ↓
DockingBackend
  ↓
Artifact + Scientific Results
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Coverage is configured in `pyproject.toml` with a 95% minimum and runs in CI on Python 3.11 through 3.14.
