# Provenance and changes relative to the supplied R2-04 package

## Preserved baseline

`provenance/r204_baseline_files.json` records SHA-256 values copied from the supplied `R2-04_ready_to_run.zip`. The unchanged set includes every vendored Python source, `integration/path_planner_lifelong.py`, `original_runtime.py`, `mechanism.py` and `recorder_base.py`. `run.py` verifies these bytes before any experiment. `verify_sources.py` also verifies the original-source manifest and the supplied integration hooks. The baseline gate is explicitly a source-identity gate; it is not represented as a newly established algorithm-equivalence theorem.

The original Lifelong engine calls, segment planner, reservation machinery, conflict-field updater, ticket manager and rollback remain in use. There is no one-shot substitute and no `lifelong_engine.py`. Existing read-only task/position hooks are reused. Full/Control remains the same joint soft-term intervention as the supplied R2-04 package.

## New experiment layer

- `workload.py`: fixed OD permutations, balanced3000-request initial queue, current fleet sizes and matched initial positions.
- `configs/od_patterns.json`: frozen service nodes, per-origin distance vector, all three coupling permutations and static overlap scores.
- `configs/experiment.json`: one coherent protocol definition,18conditions, smoke7–8 and formal39–43.
- `observations.py`: read-only500-step, all-request endpoints; no post-run spatial exposure calculation. The fixed-horizon keep-alive prevents premature termination if all tasks were ever completed early.
- `run.py`: frozen protocol validation, source-identity gate, full matrix as default; original no-timeout, immutable-attempt and checked-resume execution retained.
- `provenance.py`: source identity includes OD configuration; completion validation uses the new static score and fixed-cohort metrics.
- `verify_inputs.py`, `analyze.py`, `plot_results.py`, `postprocess.py`, `verify_package.py`: input validation, independent recorded-event audit, paired statistics, figure generation and package verification. These do not change planning decisions.

`exposure.py` is retained from the original package for provenance compatibility but is not called by the new observer. Legacy metadata fields `arrival_rate` and `concentration` are null; their presence in CSV does not activate an arrival or concentration model.

## Reference use

R2-05 supplies the FRANSEN static OD coupling definition only; its arrival-rate experiments are not imported. STANDARD/RING service nodes were selected before smoke using static geometry only. The all-at-once task input uses the same native task-queue style as the original experiment Lifelong baseline. The current R2-04 package, rather than R2-05 or a rewritten planner, supplies the executable CPS-A* baseline.

Original uploaded code/results are not modified. The prior R2-04 formal data are not used as new-run samples. Formal seeds39–43 are only prepared and checked in this package's validation, never executed by the assistant.
