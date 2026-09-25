# docking-engine

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
2. Search-space dimensions must be positive.
3. Scientifically relevant experiment changes change the experiment ID.
4. Experiments are immutable.
5. Task IDs are deterministic.
6. Run completion cannot precede run start.
7. Attempts transition `PENDING -> RUNNING -> SUCCEEDED|FAILED`.
8. Failed attempts require an error.
9. Pose ranks start at 1.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

The commit history for this first slice intentionally follows RED -> GREEN TDD.
