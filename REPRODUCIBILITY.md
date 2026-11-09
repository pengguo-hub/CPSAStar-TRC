# Reproduction guide

Run commands from the repository root unless a different working directory is specified. Install analysis and PDF-checking dependencies:

```bash
python -m pip install -r requirements-analysis.txt -r requirements-validation.txt
```

The full code import validator additionally requires experiment dependencies, including PyTorch for the predictor modules. See requirements files in the relevant experiment directories. `validation/environment.json` records a checking environment, not a requirement to match a historical execution environment.

## Analyze saved results and check files

```bash
python -m scripts.validate
python scripts/audit_statistics.py
python scripts/index_results.py
python scripts/validate_figures.py
```

These commands compile/import source, analyze saved results, index result files, and check figure readability. They do not run full experiments. Do not use `--help` as a safety check on legacy experiment runners: some do not parse command-line options.

## Submission figures and regenerated plots

The submitted `figures/` directory contains 15 PDFs selected and named by the author. Current filenames are listed in [docs/FIGURE_TABLE_MAP.md](docs/FIGURE_TABLE_MAP.md). R2.02 and a separate omega-interaction figure are not included in this selection; their saved data and plotting code remain in the repository.

Plotting code retains its original output paths and naming conventions. Running a plotting command may create additional directories and PDFs/PNGs and does not automatically rename its outputs to the submitted filenames. Replot in a working copy to preserve the submission figure selection. This documentation update does not establish pixel-level or numerical identity between an author-provided PDF and a regenerated plot.



| Target | Command |
|---|---|
| Original Fig6 and available Fig9 subsets | `MPLBACKEND=Agg python -m plotting.original_paper.replot_available` |
| Response Fig1 | `python scripts/replot.py R1_03` |
| Fig2 | `python scripts/replot.py R1_05_06` |
| Fig3 | `python scripts/replot.py R1_07_08` |
| Fig4 | `python scripts/replot.py R1_09` |
| Figs5–6 labeled SD reconstruction | `python plotting/revision/R2/R2_2/reconstruction/reconstruct_response_sd.py` |
| Fig7 | `python scripts/replot.py R2_03` |
| Fig8 | `python scripts/replot.py R2_03_omega` |
| R2.02 supplied CI plots/tables | `python scripts/replot.py R2_02_CI` |
| Figs9–10 | `python scripts/replot.py R2_04_main` |
| Fig11 including global pooled row | `python scripts/replot.py R2_04_pooled` |
| Fig12 | `python scripts/replot.py R2_05` |
| Fig13 (core CSV fallback when payload archive is absent) | `python scripts/replot.py R2_07` |
| Fig13 from core CSV only | `MPLBACKEND=Agg python -m plotting.revision.R2.R2_7.final.replot_from_core_csv` |

`python scripts/replot.py all` runs eleven revision plotting jobs, including R2.02 CI and R2.03 omega. It automatically uses the core-CSV R2.07 path when the large payload archive is absent. The core-CSV R2.07 wrapper reuses supplied effect/figure functions and checks all240 rows, but does not re-read request-level payloads. Error bars retain each supplied script's convention; R1 retry uses CI columns. R2.02 reconstruction explicitly uses sample SD. Font fallback can change rendering; Times New Roman was unavailable.


## Running experiments

These commands launch experiments. Use experiment-specific README files to prepare inputs and dependencies before running them.

- Original one-shot: `python -m src.original_paper.experiment.test_new` — blocked by missing Astar_congestion/Fransen modules and unresolved planner/agv_info reference. Supplied CPS_A/Astar_base AGV files are retained, but equivalence to that external reference is not assumed.
- Original custom lifelong: `python -m src.original_paper.experiment.Lifelong.test_ourmap`; missing benchmark assets limit complete original replication.
- R1.3: `python -m experiments.revision.R1_03_dmin.run_R1_3_dmin_sensitivity`.
- R1 Gaussian: `python -m experiments.revision.R1_05_06_gaussian.test_r1_gaussian_sensitivity`.
- R1 δ: `python -m experiments.revision.R1_07_08_delta.r1_delta_sensitivity`.
- R1 retry: `python -m experiments.revision.R1_09_retry_limit.run_R1_9_R_sensitivity`.
- R2.02: from `experiments/revision/R2_02_representation`, use the supplied `run_representation_experiment.py`; formal historical/learned references must first be prepared. See the local README and SOURCE_README.
- R2.03: from `experiments/revision/R2_03_parameter_interactions`, `python run_all_experiments.py --stage all --seeds 5 --seed-start 10000 --output ../../../../outputs/R2_03_new`.
- R2.03 omega: from that directory’s `R2_03_omega_interactions` subfolder, `python run_omega_interactions.py --seeds 5 --seed-start 10000 --output ../../../../../outputs/R2_03_omega_new`.
- R2.04 saved seeds: `python -m experiments.revision.R2_04_operational_metrics.run --formal --suite all --seeds 5 --seed-start 39 --output outputs/R2_04_new`.
- R2.05 standard cases: `python -m experiments.revision.R2_05_scalability.run --formal --output outputs/R2_05_base_new`.
- R2.05 Fransen replacement: `python -m experiments.revision.R2_05_scalability.run_fransen_backlog --all --output outputs/R2_05_fransen_new`.
- R2.07 saved subset: `python -m experiments.revision.R2_07_factorial_ablation.run --formal --seeds 5 --seed-start 42 --output outputs/R2_07_new`.

R2.05's final archive contains15 Fransen200/backlog3000/horizon500 replacements. The standard runner's older Fransen cases differ; the replacement runner and replacement audit are authoritative. No automatic merge procedure is invented. R2.07's default config plans30 seeds/1,440 trials; the saved evidence is5 seeds/240 trials. Neither config was silently rewritten.

Historical result code_hash/execution_hash values identify historical execution. Public manifests carry repackaged hashes plus supplied hashes. Raw historical metadata remains untouched.


## Optional file checksums

A root-level `SHA256SUMS.txt` is optional and is not required by the experiment, analysis, or plotting entry points. This submission configuration does not require it or include `python scripts/verify_hashes.py` in the workflow. If an older copy remains after replacing figures or documentation, remove it or regenerate it before using that optional checker.

This applies only to the root-level file checksum list. Preserve historical `code_hash`, `source_digest`, source-verification manifests, and hashes in raw experimental records.
