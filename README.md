# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

## Current execution flow

```text
TaskRepository
      │
      ▼
 Worker
      │
      ▼
DockingInputResolver
      │
      ▼
DockingExecutionRequest
      │
      ▼
DockingBackend
      │
      ├── FakeDockingBackend
      └── VinaBackend
      │
      ▼
DockingResult
      │
      ▼
ArtifactStore + ArtifactRepository
```

### Vina adapter

`VinaBackend` is a CLI adapter around AutoDock Vina. It receives already prepared receptor/ligand PDBQT bytes, a resolved docking box, and a constrained parameter mapping. It writes temporary PDBQT inputs, invokes Vina, captures stdout/stderr, and returns the raw output PDBQT as a docking artifact.

Supported Vina parameters in this initial adapter:

- `exhaustiveness`
- `num_modes`
- `energy_range`
- `seed`
- `cpu`
- `verbosity`

The adapter deliberately does not yet parse Vina scores. Raw PDBQT output remains the source artifact for the next scientific-results layer.

### Input resolution

`DockingInputResolver` separates task identity from executable scientific inputs. The in-memory implementation maps prepared receptor/ligand IDs, search-space IDs, and experiment parameters into a `DockingExecutionRequest`.

This prevents backends from reaching directly into repositories or object storage.

### Testing

The Vina subprocess boundary is injected through a runner function, so CI verifies command construction, error handling, and output capture without requiring AutoDock Vina to be installed.

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Coverage is configured in `pyproject.toml` with a 95% minimum and runs in CI on Python 3.11 through 3.14.
