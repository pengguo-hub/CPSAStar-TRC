# CPS-A*: Code and data for manuscript TRC-26-01887 (under review)

**Manuscript:** Spatiotemporal Potential Field-Based Proactive Coordination for Large-Scale Congested Multi-AGV Systems

**Authors:** Peng Guo, Jun Huang, Yuchen Jiang, Jianbin Xin, and Andrea D'Ariano

**Manuscript ID:** TRC-26-01887

This repository accompanies the manuscript under review and provides implementation code, saved experimental results, and analysis and plotting scripts for the original manuscript and its revision. Original-paper experiments and revision experiments are organized separately.

## Start

Extract the repository and open a terminal in the project root, where this README is located. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for dependency requirements, experiment-specific entry points, and figure-generation commands.

To validate the code, analyze saved results, and check the supplied figure files:

```bash
python -m scripts.validate
python scripts/audit_statistics.py
python scripts/index_results.py
python scripts/validate_figures.py
```

These commands validate code and figure files and analyze saved results; they do not rerun full experiments. They refresh reports, statistical summaries, and result indexes.

The current `figures/` directory contains 15 submission PDFs. To regenerate plots from saved results, use the commands in [REPRODUCIBILITY.md](REPRODUCIBILITY.md). Plotting scripts retain their existing output names and can produce additional files; they do not automatically reproduce the selection and filenames of the submission PDFs. Use a working copy for replotting. The current file mapping is in [docs/FIGURE_TABLE_MAP.md](docs/FIGURE_TABLE_MAP.md).

For R2.07, the plotting entry point uses the saved core CSV results when the larger payload archive is unavailable.

To run an individual experiment, follow the README in its directory under `experiments/revision/`. Experiment entry points are separate from the saved-result analysis commands above.

## Layout

| Directory | Contents |
|---|---|
| `src/original_paper/experiment/` | Original-paper planners, comparison methods, map definitions, supplied AGV inputs, and predictor weights |
| `experiments/revision/` | R1 and R2 experiment code, configurations, dependencies, and experiment-specific instructions |
| `results/original_paper/` | Saved one-shot results and lifelong and ablation summaries from the original-paper experiments |
| `results/revision/` | Saved revision results, task instances, workloads, job definitions, configurations, and completion records |
| `data/derived/` | Derived supporting inputs used by analysis and plotting scripts |
| `plotting/` | Figure-generation scripts, alternative plots, and explicitly labeled reconstructions |
| `figures/original_paper/` | Original-paper figures provided with this submission |
| `figures/revision/` | Revision figures provided with this submission |
| `statistics/` | Statistical summaries, paired comparisons, confidence intervals, and numerical comparison tables |
| `scripts/` | Repository-level tools for validation, result indexing, statistical analysis, and plotting |
| `provenance/` | Source archives, file mappings, and retained source and execution snapshots |
| `validation/` | Validation reports and execution logs for repository checks |
| `docs/` | Experiment descriptions, metric definitions, statistical methods, and supporting documentation |

Revision code and results use matching experiment directory identifiers. For example, R2.04 code is in `experiments/revision/R2_04_operational_metrics/`, and its saved results are in `results/revision/R2_04_operational_metrics/`.

Input instances and task specifications are retained with the relevant experiments, typically in directories named `instances/`, `shared_tasks/`, `workloads/`, or `configs/`. `RESULTS_MANIFEST.csv` indexes the saved result files and their locations.

## Revision evidence

The table summarizes the revised experimental evidence accompanying this submission. Values correspond to the current revision and may be updated during review.

Counts refer to analysis rows, rather than numbers of independent repetitions. Task-level records are distinguished from run-level records. R2.03 includes shared configurations represented in multiple study tables; these rows should not be counted as additional independent runs.

| Review item | Directory identifier | Saved analysis rows | Random seeds |
|---|---|---|---|
| R1.3 | `R1_03_dmin` | 90 | 42–46 |
| R1.5 / R1.6 | `R1_05_06_gaussian` | 480 | 42–46 |
| R1.7 / R1.8 | `R1_07_08_delta` | 105 | 39–43 |
| R1.9 | `R1_09_retry_limit` | 180 | 42–46 |
| R2.2 | `R2_02_representation` | 240 run-level rows; 40,000 task-level rows | 42–46 |
| R2.3 | `R2_03_parameter_interactions` | 2,130 joint/cross-interaction rows; 390 omega-interaction rows | 10000–10004 |
| R2.4 | `R2_04_operational_metrics` | 180 | 39–43 |
| R2.5 | `R2_05_scalability` | 70 | 1001–1005 |
| R2.7 | `R2_07_factorial_ablation` | 240 | 42–46 |

Reviewer 2 Comment 6 concerns statistical reporting across the experiments. The corresponding analyses are provided in `statistics/`, with methods described in [docs/STATISTICS.md](docs/STATISTICS.md).

This repository supports review of the revised manuscript and may be updated during the review process. Experiment-specific instructions and accompanying documentation describe the available inputs, saved results, and reproduction procedures.

## License

No license has been assigned yet. Redistribution and reuse terms will be decided upon publication.
