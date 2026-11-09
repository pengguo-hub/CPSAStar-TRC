# R2-03 — Gaussian spatiotemporal parameter sensitivity

This package contains only the Reviewer-2 R2-03 parameter-sensitivity evidence.
It uses the **one-shot CPS-A** source from `experiment.zip/CPS_A/` and does **not** use `Astar_base`, a frozen background, or a Lifelong planner.

## 1. Experimental protocol

For each `(map, task_count, seed)` a task list is generated once. Every parameter cell receives exactly the same task list and starts from a fresh, empty CPS-A reservation table. Thus parameter changes are allowed to alter paths, reservations, congestion fields, rollback decisions, and all subsequent planning — which is the effect being measured.

### Task loads — same as completed R1 Gaussian sensitivity

| Map | Formal task counts |
|---|---|
| A | 50, 70 |
| B | 250, 280 |
| C | 150, 200 |

There are therefore **6 map-load combinations**, not 3.

### Heuristic protocol — same as R1

- Map A: `h = Manhattan + omega * look-ahead congestion`.
- Map B/C: `h = Manhattan` only.
- All maps: `g` retains `gamma * current Gaussian congestion`.

## 2. Baseline

`alpha=1.0, beta=0.5, gamma=5.0, omega=50.0, L=1, T=1, sigma_l=2.0, sigma_t=2.0, K=20`.

The manuscript Table 3 and executable one-shot source use beta=0.5; later manuscript prose says beta=1.0. R2-03 follows the executable one-shot source and records the discrepancy rather than silently switching.

## 3. Evidence layers

### Existing R1 evidence — not rerun
`existing_R1_evidence/`: one-factor L / T / sigma_l / sigma_t results, 5 old seeds (42–46).

### Joint spatiotemporal sensitivity
- `sigma_l x sigma_t`: 4 x 4 grid, with L=T=1.
- `L x T`: 4 x 4 grid, with sigma_l=sigma_t=2.
- They share one identical baseline cell, so there are 31 unique configurations per map-load-seed.

Formal actual executions: `31 x 6 map-loads x 5 seeds = 930`.

### Cross-parameter interactions
- `gamma x sigma_l`: 3 x 4.
- `gamma x sigma_t`: 3 x 4.
- supplementary `gamma x K`: 3 x 5.

Because overlapping configurations are cached/reused, these 39 logical cells reduce to **33 unique configurations** per map-load-seed.

Formal actual executions: `33 x 6 map-loads x 5 seeds = 990`.

### Total new R2-03 executions
`930 + 990 = 1,920` actual complete one-shot CPS-A executions.

The logical study tables contain 2,130 rows because shared cells appear in each relevant study table; they are not rerun.

## 4. Run

Install:
```bash
python -m pip install -r requirements.txt
```

Smoke (engineering validation only):
```bash
python run_all_experiments.py --stage all --smoke --seed-start 10000 --output smoke_R2_03
```

Formal:
```bash
python run_all_experiments.py --stage all --seeds 5 --seed-start 10000 --output results_R2_03
```

R1 single-factor experiments are never rerun by the `all` command.

## 5. Main files

- `run_all_experiments.py`: recommended top-level entry.
- `run.py`: joint Gaussian grids.
- `run_parameter_interactions.py`: gamma-sigma_l, gamma-sigma_t, gamma-K.
- `config.py`: baseline, task loads, candidate grids, map-specific look-ahead switches.
- `instances.py`: paired task generation/cache only; **no planner/background generation**.
- `controlled_planner.py`: full one-shot CPS-A batch coordination and local rollback.
- `controlled_search.py`: minimally parameterized single-AGV CPS-A search.
- `field_strategies.py`: passes L/T/sigma_l/sigma_t into the original Gaussian updater.
- `vendor/CPS_A/`: original one-shot CPS-A source retained for provenance.
