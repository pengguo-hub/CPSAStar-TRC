# R2-02 causal-isolation matrix

The central design is a two-axis isolation:

| Question | Fixed | Changed |
|---|---|---|
| Why exact information? | planner, hard reservations, Gaussian kernel, gamma/omega, task set/order | congestion information source |
| Why Gaussian? | planner, hard reservations, exact reservation source, gamma/omega, task set/order | kernel/decay representation |

## Information-source family

`gaussian` ↔ `historical_gaussian` ↔ `learned_gaussian`

All three use the same numerical Gaussian smoother after a raw occupancy representation is obtained.

## Kernel family

`raw` ↔ `gaussian` ↔ `exponential` ↔ `linear` ↔ `uniform`

All five obtain congestion from the same currently committed reservation table.

## Shared planner invariants

- fixed turn penalty: 0.5
- no beta runtime parameter
- alpha=1.0, gamma=5.0
- Map A: Manhattan + congestion look-ahead, omega=50
- Maps B/C: Manhattan heuristic only
- same hard reservation conflict rules
- same wait action and MAX_WAIT
- same update interval
- same timeout
- same rollback switch within a suite
- direct one-shot planning from an empty reservation table

## Data separation

Formal test seeds: 42–46 by default (or the same five formal seeds used elsewhere in the paper).

Reference/calibration seeds: default 10000–10029.

The preparation script rejects overlap. Historical and learned labels are generated with a collision-only version of the same controlled planner, not with Gaussian CPS-A, avoiding circular construction of the indirect baselines.
