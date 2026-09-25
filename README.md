# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

The project separates scientific identity, planning, execution state, persistence contracts, and infrastructure so docking backends can be added without defining the domain around a particular CLI or database.

## Current architecture

### Domain model

- `DockingExperiment`: immutable scientific intent with content-addressed identity.
- `DockingBox`: explicit docking search-space definition.
- `PreparedReceptor` and `PreparedLigand`: prepared scientific artifact references.
- `DockingTask`: one independently executable receptor × ligand unit.
- `ExperimentRun`: one execution of an experiment.
- `TaskAttempt`: retry-aware execution state machine.
- `DockingPose`: immutable pose result metadata.
- `ArtifactMetadata`: immutable metadata for externally stored artifacts.

### Planning

- `TaskPlanner`: pure expansion of an experiment plus prepared inputs into deterministic tasks.
- `TaskManifest`: immutable, deterministically ordered execution contract.
- exact duplicate prepared inputs are deduplicated.
- task-ID collisions with conflicting provenance are rejected.

### Repository contracts

- `TaskRepository`: task registration, deterministic claiming, attempt completion, retry history.
- `ArtifactRepository`: idempotent artifact metadata registration and provenance lookup.
- in-memory adapters provide executable contract implementations without database dependencies.

Execution attempts are scoped to a `run_id`: success makes a task terminal for that run, while a new run may intentionally execute the same task again. Failed attempts are retryable with monotonically increasing attempt numbers.

The in-memory task repository provides process-local claim semantics. A future PostgreSQL adapter will preserve the same interface while implementing cross-worker atomic claims transactionally.

Artifact repositories store metadata only. Molecular files and docking outputs remain external immutable artifacts addressed by URI and checksum.

## Development

Install the development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
python -m pytest
```

Run tests with the same branch-coverage gate used by CI:

```bash
python -m pytest \
  --cov=moldock \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-report=html:htmlcov
```

Coverage is configured in `pyproject.toml` with a **95% minimum**. CI runs the suite on Python 3.11 through 3.14 and stores XML/HTML reports as build artifacts.
