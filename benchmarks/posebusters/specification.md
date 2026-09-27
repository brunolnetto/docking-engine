# PoseBusters benchmark specification

## Objective

Measure whether the full docking-engine pipeline can reproduce a known
classical docking baseline over a diverse external dataset, while preserving
engine reliability, reproducibility and provenance.

This benchmark is not the 1IEP smoke test. It is an external scientific
quality gate.

## Dataset

Primary source: Zenodo record 8278563, `posebusters_paper_data.zip`.

The Chemical Science benchmark analysis uses 308 recent protein-ligand
complexes for the PoseBusters Benchmark set. The archive also contains
additional paper data, so the benchmark runner must validate the selected
case count rather than assuming every extracted directory belongs to the
308-case evaluation subset.

Expected case layout:

```text
<dataset_root>/<case_id>/<case_id>_protein.pdb
<dataset_root>/<case_id>/<case_id>_ligand.sdf
```

## Docking protocol

For the published Vina comparison:

- cognate-ligand redocking
- rigid receptor
- Vina search space: 25 Å x 25 Å x 25 Å cube
- box center: geometric center of crystallographic ligand heavy atoms
- top-ranked Vina pose is the primary prediction
- PoseBusters `redock` evaluation

The benchmark manifest pins the engine-side versions and stochastic
parameters used by our reproducibility run. If these differ from the paper,
the report must label the result as an engine baseline rather than a direct
paper reproduction.

## Primary metrics

1. Engine completion rate.
2. Top-1 symmetry-aware heavy-atom RMSD <= 2 Å.
3. PB-valid rate.
4. Combined Top-1 RMSD <= 2 Å and PB-valid rate.
5. Median top-1 RMSD.
6. Median case runtime.

## Secondary metrics

- failures by stage: dataset, preparation, docking, export, evaluation
- top-N native-like recovery
- score/rank distributions
- interaction-fingerprint recovery after the crystal-reference interaction
  evaluator is added

## Product gates

The first complete benchmark run establishes the repository baseline.

After that baseline exists:

- execution success must not regress by more than 1 percentage point
- Top-1 RMSD <= 2 Å must not regress by more than 2 percentage points
- combined RMSD/PB-valid must not regress by more than 2 percentage points
- idempotent reruns must create no duplicate attempts or observations

No gate may compare our run directly with the published Vina percentage unless
the preparation and docking protocol are demonstrably equivalent.
