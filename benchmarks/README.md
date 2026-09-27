# Scientific benchmarks

This directory contains reproducible, external scientific benchmarks for the
engine. Benchmark code is intentionally kept outside the installable
`moldock` package so benchmark dependencies and datasets do not become
runtime dependencies.

## Benchmark policy

Scientific quality and engine quality are reported separately.

Scientific metrics:
- top-1 symmetry-aware heavy-atom RMSD <= 2 Å
- top-N RMSD <= 2 Å
- PoseBusters PB-valid rate
- combined RMSD <= 2 Å and PB-valid rate

Engine metrics:
- case completion rate
- preparation failure rate
- docking failure rate
- evaluation failure rate
- median runtime
- restart/idempotency failures

A benchmark result is comparable with a published baseline only when the
dataset, search-space definition, preparation policy, engine/version and
evaluation semantics match.

## Current benchmark

`posebusters/` implements the first product benchmark. The published
PoseBusters protocol uses a 25 Å cubic Vina search box centered on the
geometric center of the crystallographic ligand heavy atoms.

Dataset source:
- Zenodo record 8278563
- archive: `posebusters_paper_data.zip`
- benchmark subset: 308 complexes used in the Chemical Science paper

The benchmark runner expects the extracted dataset layout:

```text
posebusters_benchmark_set/
  <complex_id>/
    <complex_id>_protein.pdb
    <complex_id>_ligand.sdf
```

See `posebusters/specification.md` for the protocol and acceptance criteria.

## Benchmark outputs

A PoseBusters benchmark run writes three machine-readable artifacts and one
scientist-facing artifact:

- `engine_cases.json` — engine execution outcome and failure stage per case
- `evaluated_cases.json` — reference-pose RMSD and PB-valid result per evaluable case
- `summary.json` — aggregate scientific and engine metrics
- `report.md` — human-readable benchmark report with protocol, results,
  failure accounting, provenance and interpretation guardrails

The report deliberately keeps the published Vina result as contextual
reference metadata. It does not compute a regression delta against that value
unless protocol equivalence has been established.
