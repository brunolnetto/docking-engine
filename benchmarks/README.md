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


## Astex Diverse fast regression suite

`astex/` defines the 85-complex Astex Diverse suite as the smaller scientific
regression layer. It uses the same cognate-redocking engine protocol and
reference-pose evaluation semantics as the primary PoseBusters benchmark, so
failures can be reproduced through the shared `benchmarks/redocking.py`
harness rather than a separate implementation.

The initial Astex protocol is intentionally an engine regression protocol, not
a reproduction of the original GOLD study. Published Astex success percentages
must therefore not be used as repository regression gates.

Run a prepared Astex dataset with:

```bash
python benchmarks/astex/run_benchmark.py \
  --dataset-root <astex_diverse_set> \
  --output-root <output>
```

For local harness checks, `--limit N` permits a partial run. An authoritative
regression baseline requires the complete 85-case suite.
