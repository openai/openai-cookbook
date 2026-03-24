# 3 Pairwise Harness

This harness expresses pairwise judging in Evals over normalized PR records.

Dataset preparation reuses the normalized benchmark record from Level 2, then caches:

- one baseline review
- one candidate review

The Evals run creates or reuses the eval version matching the current local harness config, judges the two reviews side by side, and aggregates `baseline`, `candidate`, and `tie` outcomes locally after the run finishes.
