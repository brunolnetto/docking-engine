# Astex Diverse benchmark specification

## Objective

Provide a smaller scientific regression suite for the docking engine using the
85-complex Astex Diverse set.

This suite is intended to run before the larger PoseBusters benchmark and to
detect scientific regressions in preparation, docking, pose export and
reference-pose recovery.

## Dataset

The harness expects the PoseBusters/PoseBench-style prepared representation:

```text
<dataset_root>/<case_id>/<case_id>_protein.pdb
<dataset_root>/<case_id>/<case_id>_ligand.sdf
```

The pinned source in `manifest.json` is Zenodo record 8278563, which includes
the Astex Diverse complexes used by the PoseBusters study.

The original Astex Diverse set contains 85 protein-ligand complexes. A full
run therefore requires exactly 85 discovered cases.

## Protocol

For consistency with the primary PoseBusters engine benchmark, the initial
Astex regression protocol uses:

- cognate-ligand redocking
- rigid receptor
- Meeko 0.8.0 preparation
- AutoDock Vina 1.2.7
- 25 Å cubic search space
- box center at the crystallographic ligand heavy-atom geometric center
- seed 42
- exhaustiveness 8
- 9 requested modes
- PoseBusters 0.6.5 `redock` evaluation

This is an engine regression protocol over Astex. It is **not** a reproduction
of the original GOLD experiments and must not be compared directly with their
published success percentages.

## Metrics

Scientific metrics:

- Top-1 RMSD <= 2 Å
- Top-3 RMSD <= 2 Å
- Top-5 RMSD <= 2 Å
- Top-9 RMSD <= 2 Å
- PB-valid
- combined Top-1 RMSD <= 2 Å and PB-valid
- median Top-1 RMSD

Engine metrics:

- engine execution success
- end-to-end evaluability
- failures by stage
- median evaluable-case runtime

No composite scientific score is defined.

## Regression role

Astex is the fast scientific regression layer. The complete PoseBusters set
remains the primary pose-quality product benchmark.
