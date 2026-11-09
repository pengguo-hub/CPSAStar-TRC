# R2-03 supplementary experiment: look-ahead weight interactions (Map A only)

This folder contains **only the additional omega interaction study** and the source modules needed to rerun it. It does not include or rerun the previously completed R2-03 interactions (`sigma_l x sigma_t`, `L x T`, `gamma x sigma_l`, `gamma x sigma_t`, or `gamma x K`).

## What is tested

The R1-aligned implementation enables the omega-weighted look-ahead congestion term only on **Map A**. Maps B and C use Manhattan distance only in the heuristic, so omega has no active effect there. The experiment is therefore restricted to Map A and covers three pairwise interactions:

| Study | Varied parameters | Fixed Gaussian/update settings | Grid |
|---|---|---|---:|
| `omega_sigma_l` | `omega = {10, 50, 100}`; `sigma_l = {0.5, 1, 2, 4}` | `sigma_t=2`, `L=T=1`, `K=20` | 3 x 4 |
| `omega_sigma_t` | `omega = {10, 50, 100}`; `sigma_t = {0.5, 1, 2, 4}` | `sigma_l=2`, `L=T=1`, `K=20` | 3 x 4 |
| `omega_K` | `omega = {10, 50, 100}`; `K = {1, 10, 20, 30, 40}` | `L=T=1`, `sigma_l=sigma_t=2` | 3 x 5 |

The omega values are selected from the candidate values listed in the manuscript's parameter table; the sigma values reuse the R1 Gaussian sweep; K values reuse the manuscript's update-interval ablation settings. All other parameters remain at the R2-03 executable-source baseline:

`alpha=1.0, beta=0.5, gamma=5.0, omega=50.0, L=T=1, sigma_l=sigma_t=2.0, K=20`.

**Baseline note:** the current executable-source baseline uses `beta=0.5`, while later prose in the manuscript states `beta=1.0`. This package follows the same executable-source baseline as the existing R2-03 runs and does not silently alter it.

## Formal protocol and run count

- Map: A only, with look-ahead congestion enabled.
- Task loads: `N=50` and `N=70`.
- Seeds: `10000, 10001, 10002, 10003, 10004`.
- Within each `(Map A, task load, seed)`, the exact task list from the completed R2-03 run is reused across all configurations. Each configuration starts from empty reservations and plans the complete one-shot task batch.
- Logical study cells: `(12 + 12 + 15) x 2 loads x 5 seeds = 390` rows.
- Unique configurations: 33 per task-load-seed combination, because overlapping baseline/parameter cells are reused across studies.
- **Expected actual planner executions: `33 x 2 x 5 = 330`.**
- Existing R1 five-seed data are not pooled with these new seeds.

The paired task files for seeds 10000--10004 are included under `results_omega_interactions/shared_tasks/`. They were copied from the completed R2-03 task cache so these trials use the same Map-A instances as the other R2-03 interaction experiments.

## Run instructions

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Engineering smoke test (8 small executions; **not formal evidence**):

```bash
python run_omega_interactions.py --smoke --seed-start 10000 --output smoke_omega
```

Formal experiment (330 unique full-batch one-shot CPS-A executions):

```bash
python run_omega_interactions.py --seeds 5 --seed-start 10000 --output results_omega_interactions
```

Generate publication-facing plots from the formal CSVs:

```bash
python plot_omega_interactions.py --input results_omega_interactions --output omega_interaction_figures
```

The plot script deliberately rejects smoke output and checks the seed set, loads, Map A-only scope, look-ahead activation, five-seed summaries, and paired task hashes before plotting.

## Outputs

- `results_omega_interactions/omega_interactions_manifest.json`: configuration grid and expected run counts.
- `results_omega_interactions/omega_interactions_raw_results.csv`: run-level rows for each study cell and seed.
- `results_omega_interactions/omega_interactions_summary.csv`: means, standard deviations, and bootstrap 95% CIs.
- `results_omega_interactions/omega_interactions_completion_status.json`: execution and protocol validation.
- `results_omega_interactions/runs/`: cached per-configuration execution records.
- `omega_interaction_figures/01_response_letter/Figure_R2_03_Response_Omega_Interactions.{png,pdf}`: high-load success-rate delta heatmaps for the three omega interactions.
- `omega_interaction_figures/03_supplementary/`: R1-style line plots for success rate, planning time, and average path length across both loads.
- `omega_interaction_figures/ANALYSIS_OMEGA_INTERACTIONS.md`: concise interpretation generated from the actual result CSV.
- `RESPONSE_LATEX.tex`: suggested LaTeX response paragraph and figure environment using the actual formal results.

The heatmap reports `mean success rate(setting) - mean success rate(formal baseline)` in percentage points. Blue is higher than baseline; red is lower; the black box marks the baseline cell. Supplementary figures show five-seed means and bootstrap 95% confidence intervals. Differences are descriptive; do not call them statistically significant without a paired inferential test.
