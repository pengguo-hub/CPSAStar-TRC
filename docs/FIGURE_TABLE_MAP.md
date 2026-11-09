# Figure and table map

## Figures accompanying this submission

The following paths refer to the 15 author-provided PDFs currently included in `figures/`. Response numbering follows the existing response mapping; R2.4 files are identified by content because three separately named PDFs are supplied. The PDFs are submission figures, not assertions of byte-identical output from the repository plotting scripts.

| Item | File path from repository root |
|---|---|
| Original manuscript Fig. 9: supplied lifelong comparison | `figures/original_paper/lifelong/lifelong.pdf` |
| Original manuscript Fig. 6: one-shot comparison, Map A | `figures/original_paper/one_shot/e1_mapa.pdf` |
| Original manuscript Fig. 6: one-shot comparison, Map B | `figures/original_paper/one_shot/e1_mapb.pdf` |
| Original manuscript Fig. 6: one-shot comparison, Map C | `figures/original_paper/one_shot/e1_mapc.pdf` |
| Legend for the one-shot comparison panels | `figures/original_paper/one_shot/legend.pdf` |
| Response Fig. 1: minimum-distance sensitivity | `figures/revision/R1_03_dmin/R1.3.pdf` |
| Response Fig. 2: Gaussian parameter sensitivity | `figures/revision/R1_05_06_gaussian/R1.5_1.6.pdf` |
| Response Fig. 3: delta sensitivity | `figures/revision/R1_07_08_delta/R1.7_1.8.pdf` |
| Response Fig. 4: retry-limit sensitivity | `figures/revision/R1_09_retry_limit/R1.9.pdf` |
| Response Fig. 7: joint and cross-parameter interactions | `figures/revision/R2_03/R2.3.pdf` |
| R2.4: main operational-metrics figure | `figures/revision/R2_04_operational_metrics/R2.4.pdf` |
| R2.4: congestion-exposure effects | `figures/revision/R2_04_operational_metrics/R2.4_congestion_exposure_effects.pdf` |
| R2.4: Full-Control comparison including pooled conditions | `figures/revision/R2_04_operational_metrics/R2.4_full_control.pdf` |
| Response Fig. 12: scalability | `figures/revision/R2_05_scalability/R2.5.pdf` |
| Response Fig. 13: four-factor ablation | `figures/revision/R2_07_factorial_ablation/R2.7.pdf` |

## Analysis and plotting locations

| Evidence | Plotting entry or location | Default output directory |
|---|---|---|
| Original one-shot/lifelong | `python -m plotting.original_paper.replot_available` | `figures/original_paper/` (available data subsets) |
| R1.3 | `python scripts/replot.py R1_03` | `figures/revision/R1_03_dmin/` |
| R1.5/1.6 | `python scripts/replot.py R1_05_06` | `figures/revision/R1_05_06_gaussian/` |
| R1.7/1.8 | `python scripts/replot.py R1_07_08` | `figures/revision/R1_07_08_delta/` |
| R1.9 | `python scripts/replot.py R1_09` | `figures/revision/R1_09_retry_limit/` |
| R2.02 CI | `python scripts/replot.py R2_02_CI` | `figures/revision/R2_02_representation/supplied_CI/` |
| R2.03 joint/cross | `python scripts/replot.py R2_03` | `figures/revision/R2_03_parameter_interactions/` |
| R2.03 omega | `python scripts/replot.py R2_03_omega` | `figures/revision/R2_03_omega_interactions/` |
| R2.04 main | `python scripts/replot.py R2_04_main` | `figures/revision/R2_04_operational_metrics/main/` |
| R2.04 pooled | `python scripts/replot.py R2_04_pooled` | `figures/revision/R2_04_operational_metrics/pooled/` |
| R2.05 | `python scripts/replot.py R2_05` | `figures/revision/R2_05_scalability/` |
| R2.07 | `python scripts/replot.py R2_07` | `figures/revision/R2_07_factorial_ablation/`; CSV fallback uses `core_csv_replot/` |

Generated filenames retain the supplied scripts' naming conventions. In particular, the submitted `R2_03/R2.3.pdf` and the plotting output directory `R2_03_parameter_interactions/` are different locations. No automatic rename or replacement mapping is implemented. `python scripts/replot.py all` runs all eleven registered revision plotting targets, including targets not represented in the submitted PDF selection.

R2.02 figures (previous Response Figs. 5-6) and a separate omega-interaction figure (previous Response Fig. 8) are not included in this figure selection. Their absence from this directory does not remove their underlying code or saved results. The R2.02 CI plots and separately labeled SD reconstruction use different error-bar conventions.

## Table evidence

| Item | Evidence location or definition |
|---|---|
| Original manuscript Tables 4-6 | `results/original_paper/ablation/`: supplied summary tables and selected spreadsheet evidence |
| Response Table 1 | R2.03 observed parameter grids and manifests, including omega results |
| Response Table 2 | Final R2.05 trial rows and statistical summaries |
| Response Table 3 | R2.07 conditional smoothing effects, averaging nuisance factors within each seed |
| Response Table 4 | R2.07 rollback counts and `instrumented_pure_seconds` |
| Reported numerical comparisons | `statistics/response_numeric_checks.csv` |

Stored original-paper data support the available replot subsets; inclusion of an author-provided figure does not add missing per-seed or benchmark data. See experiment-specific documentation for inputs and analysis definitions.
