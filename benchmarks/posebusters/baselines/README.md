# PoseBusters baselines

Two kinds of reference data live here and they must not be conflated.

## Published references

`vina-paper.json` records approximate values reported in the literature. It is
contextual evidence only. It is not a repository regression baseline unless the
entire published protocol has been independently shown to be equivalent.

## Repository-measured baseline

The first authoritative engine baseline must be recorded from a complete
308-case run using the pinned `manifest.json`.

Record it with:

```bash
python benchmarks/regression.py record \
  --summary <run>/summary.json \
  --engine-cases <run>/engine_cases.json \
  --manifest benchmarks/posebusters/manifest.json \
  --source-commit "$(git rev-parse HEAD)" \
  --output benchmarks/posebusters/baselines/engine-v1.json
```

The recorder refuses partial runs and verifies both evaluated and engine case
counts against the manifest. Do not hand-author metric values.

Once an authoritative baseline exists, compare a complete current run with:

```bash
python benchmarks/regression.py compare \
  --baseline benchmarks/posebusters/baselines/engine-v1.json \
  --summary <run>/summary.json \
  --engine-cases <run>/engine_cases.json \
  --manifest benchmarks/posebusters/manifest.json \
  --output <run>/regression.json
```

Current default regression tolerances are:

- engine execution success: at most 1 percentage point drop
- Top-1 RMSD <= 2 Å: at most 2 percentage points drop
- combined Top-1 RMSD <= 2 Å and PB-valid: at most 2 percentage points drop

A manifest hash mismatch is a protocol change, not a regression comparison.
Establish a new baseline lineage instead of comparing non-equivalent runs.
