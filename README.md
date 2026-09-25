# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

The project intentionally separates scientific identity, planning, execution, and infrastructure so docking backends can be added without defining the domain model around a particular CLI.

## Current architecture

### Domain model

- `DockingExperiment`: immutable scientific intent with content-addressed identity.
- `DockingBox`: explicit docking search-space definition.
- `PreparedReceptor`: reference to a receptor artifact produced by a known preparation recipe.
- `PreparedLigand`: reference to a ligand artifact produced by a known preparation recipe.
- `DockingTask`: one independently executable prepared receptor × prepared ligand unit.
- `ExperimentRun`: one execution of an experiment.
- `TaskAttempt`: retry-aware execution state machine.
- `DockingPose`: immutable result metadata pointing to an external artifact.

### Planning

- `TaskPlanner`: pure expansion of an experiment plus prepared inputs into deterministic tasks.
- `TaskManifest`: immutable, deterministically ordered execution contract.
- duplicate prepared inputs are deduplicated only when their complete provenance is identical.
- task-ID collisions with conflicting provenance are rejected.
- completed task IDs can be filtered without mutating the manifest.

The planner performs no docking, storage, scheduling, or network I/O.

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
