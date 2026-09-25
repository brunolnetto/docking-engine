# docking-engine

[![CI](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/brunolnetto/docking-engine/actions/workflows/ci.yml)

Domain-first foundations for a reproducible molecular docking execution system.

## Execution and scientific-result flow

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
DockingBackend (Vina / Fake)
      │
      ▼
raw backend artifact
      │
      ├── ArtifactStore
      ├── ArtifactRepository
      │
      ▼
ScientificResultInterpreter
      │
      ▼
Pose + PoseScore + PoseRanking
```

### Scientific result semantics

Pose geometry, score, and ranking are separate identities.

- `Pose` identifies a specific geometry derived from a raw backend artifact.
- `PoseScore` records a typed scoring observation, including method and version.
- `PoseRanking` records an ordering under a particular ranking method.

This allows the same pose geometry to be rescored or reranked later without changing its pose identity.

### Vina result parsing

`VinaResultParser` parses numbered PDBQT `MODEL` blocks and their `REMARK VINA RESULT` records into:

- one `Pose` per model
- one `VINA_AFFINITY` score per pose
- one Vina-affinity ranking per pose
- RMSD lower/upper bounds as score metadata

The raw PDBQT remains the immutable source artifact.

### Artifact storage

Blob storage and scientific provenance remain separate. `ArtifactStore.read(uri)` allows interpreters to retrieve bytes without depending on storage-specific URI parsing.

### Testing

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Coverage is configured in `pyproject.toml` with a 95% minimum and runs in CI on Python 3.11 through 3.14.
