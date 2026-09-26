# Real Vina E2E fixtures

These molecular inputs are vendored from the official AutoDock Vina
`basic_docking` example at upstream commit:

`3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645`

Files:

- `1iep_receptorH.pdb` — hydrogenated mouse c-Abl receptor used by the tutorial.
- `1iep_ligand.sdf` — Imatinib (STI) 3D ligand used by the tutorial.

Upstream repository: `ccsb-scripps/AutoDock-Vina`.

The documented Vina search box is:

- center: `15.190, 53.903, 16.917`
- size: `20, 20, 20`

The fixtures are intentionally stored locally so the real E2E workflow has
no network dependency at execution time.
