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


## Normalization note

The upstream `1iep_receptorH.pdb` snapshot places atom 3429 (SER A 438 HB2)
immediately after the header while atoms 3428 and 3430 remain in the SER 438
residue block. The vendored fixture moves that unchanged atom record back
between atoms 3428 and 3430 so receptor residue ordering is canonical for the
real Meeko preparation path. No coordinates, atom identity, charge, occupancy,
or B-factor values are changed.
