# Omega interaction analysis (Map A only)

All numerical values below are calculated from `omega_interactions_summary.csv`; no values are manually entered.
Formal seeds: 10000--10004. Loads: N=50 and N=70. The heatmap uses N=70.

## High-load success-rate changes relative to baseline

| Interaction | Mean SR range across cells | Delta range vs baseline |
|---|---:|---:|
| `omega_sigma_l` | 70.3--78.3% | -4.6 to +3.4 pp |
| `omega_sigma_t` | 72.9--77.1% | -2.0 to +2.3 pp |
| `omega_K` | 70.6--78.9% | -4.3 to +4.0 pp |

## Interpretation guidance

- Positive delta means the tested setting has a higher mean success rate than the formal baseline; negative delta means lower.
- The black box in the heatmap marks the baseline cell (omega=50 and sigma_l=2, sigma_t=2, or K=20 as appropriate).
- These are five-seed descriptive means with bootstrap 95% confidence intervals in the supplementary plots. Do not describe differences as statistically significant without a paired inferential test.
- This experiment is restricted to Map A because the R1-aligned implementation enables the omega-weighted look-ahead congestion term only on Map A. Maps B and C use Manhattan distance only in h(s).
- The omega candidates (10, 50, 100) are selected from the manuscript's declared omega candidate list; sigma candidates reuse the R1 Gaussian sweep; K candidates reuse the manuscript's update-interval ablation values.
