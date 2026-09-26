# Real Meeko → Vina report

This example executes the full offline scientific path using the official
AutoDock Vina 1IEP/Imatinib tutorial inputs:

```text
PDB + SDF
→ Meeko receptor/ligand preparation
→ FilesystemArtifactStore
→ DuckLake planning/execution state
→ AutoDock Vina
→ VinaResultInterpreter
→ durable RunManifest
→ Markdown + JSON report
```

Requirements:

- Python project installed with `ducklake` and `meeko` extras.
- Meeko 0.8.0 command-line tools on `PATH`.
- AutoDock Vina 1.2.7 `vina` executable on `PATH`.

Run:

```bash
python examples/real_vina_report.py \
  --workspace .moldock/1iep \
  --run-id 1iep-vina-1
```

Outputs:

```text
.moldock/1iep/reports/1iep-vina-1.md
.moldock/1iep/reports/1iep-vina-1.json
```

Running the same command again with the same inputs and `run-id` reuses the
successful docking task. The report is reconstructed from durable DuckLake
state and the persisted run manifest.
