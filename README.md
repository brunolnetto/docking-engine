# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

This initial version intentionally has no RDKit, Vina, database, scheduler, or object-store dependency. The goal is to establish scientific and execution semantics before infrastructure is introduced.

## Domain model

- `DockingExperiment`: immutable scientific intent with content-addressed identity.
- `DockingBox`: explicit docking search-space definition.
- `DockingTask`: one independently executable prepared receptor × prepared ligand unit.
- `ExperimentRun`: one execution of an experiment.
- `TaskAttempt`: retry-aware execution state machine.
- `DockingPose`: immutable result metadata pointing to an external artifact.

## Invariants

The tests specify that:

1. Content IDs are deterministic and mapping-order independent.
2. Search-space coordinates are finite and dimensions are finite and positive.
3. Scientifically relevant experiment changes change the experiment ID.
4. Experiments and nested experiment parameters are immutable.
5. Task IDs are deterministic.
6. Run completion cannot precede run start.
7. Attempts transition `PENDING -> RUNNING -> SUCCEEDED|FAILED`.
8. Attempt timestamps and errors must match the attempt status.
9. Failed attempts require a non-blank error.
10. Pose ranks start at 1.

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

Coverage is configured in `pyproject.toml` with a **95% minimum**. CI runs the suite on Python 3.11 through 3.14, publishes the coverage table to the GitHub Actions job summary, and stores XML/HTML reports as build artifacts for 14 days.
