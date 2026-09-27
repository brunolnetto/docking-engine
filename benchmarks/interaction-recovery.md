# Native interaction-recovery benchmark

## Objective

Measure whether the engine's Top-1 docked pose recovers the receptor-residue
interaction fingerprint observed for the crystallographic ligand.

This benchmark complements RMSD. A pose can be geometrically close while
losing important interactions, or geometrically different while preserving a
subset of the reference interaction pattern.

## Reference construction

For each benchmark case:

1. prepare the receptor with the same pinned Meeko protocol used for docking;
2. prepare the crystallographic ligand with the same pinned Meeko protocol;
3. run the production `PoseInteractionAnalyzer` over the prepared
   crystallographic geometry;
4. run the same analyzer over engine-ranked pose 1;
5. convert both observations to residue-level fingerprints;
6. compare each interaction family independently.

The fingerprint key is:

```text
interaction family + receptor chain + residue name + residue number
```

Atom-pair multiplicity is deliberately collapsed. The benchmark measures
whether a residue-level interaction feature is recovered, not how many atom
pairs happened to satisfy the same geometric cutoff.

## Current families

The benchmark covers exactly the interaction families implemented by the
engine today:

- heavy-atom contact;
- hydrophobic contact;
- geometry-qualified hydrogen bond;
- putative salt bridge.

Future pi stacking, pi-cation, halogen-bond, metal-coordination and
water-mediated families should be added only when the production analyzer
implements them.

## Metrics

Per family:

- TP;
- FP;
- FN;
- precision;
- recall;
- F1;
- Jaccard.

Dataset summaries micro-aggregate TP/FP/FN within each family. They do not
collapse families into an overall interaction score.

When both reference and prediction have no observations for a family,
precision/recall/F1/Jaccard are `n/a`, not 1.0.

## Interpretation constraints

- salt bridges retain the existing **putative** partial-charge semantics;
- fingerprint recovery is not molecular-dynamics occupancy;
- reference interactions are defined on the engine's prepared representation,
  not claimed as an independent experimental interaction annotation;
- this benchmark tests consistency with crystallographic geometry under the
  engine's interaction definitions.
