# Statistical definitions — R2.6

Five seed blocks are independent units. Tasks, map-condition rows and factorial variants are not independent replications. Sample SD uses ddof=1;95% t CI = mean ± t(0.975,4) SD/sqrt(5). Paired differences are formed within matched seed before summarization.

| Study | Convention |
|---|---|
| R1 d_min |100×(d1−d3 success), percentage points |
| R1 Gaussian |L3−L1 planning seconds |
| R1 δ |Single-condition mean atδ3; not paired test |
| R2.02 success |100×(Gaussian−comparator), percentage points |
| R2.02 exposure |Intersect successful task IDs within seed, then100×(comparator−Gaussian)/comparator |
| R2.03 |Same study/map/load/seed baseline differences; every cell retained |
| R2.04 pooled |Full−Control across9 high-fleet conditions, averaged within seed; n=5 |
| R2.05 |Named case differences within seed; Table2 single-condition means/CIs |
| R2.07 |On−off averaged over nuisance factors within map/seed; S×L is difference of conditional S effects |

Figure13 uses planning_seconds; Table4 uses instrumented_pure_seconds (loop time minus assignment). Both definitions are retained in R2_07_conditional_metric_definitions.csv. They are not interchangeable.

All2^5 sign combinations are enumerated for the two-sided paired sign-flip test; minimum p=2/32=0.0625. A t interval excluding zero does not imply this discrete test has p<0.05. Added Holm families are explicitly audit-defined selected-contrast families, not claimed historical prespecification. The supplied R2.07 plot separately defines its own main/interaction/conditional families and bootstrap/Wilcoxon sensitivity analyses.

R2.02's supplied script states bootstrap CI while Response states SD; its ±4pp axis clips +5.79/+6.20pp effects. The statistics module is now included and the supplied CI pipeline runs on temporary copies of the raw data. The source CI plot retains its original fixed axis limits; The labeled reconstruction uses sample SD, common-successful-task matching and automatic y limits.

Original lifelong/ablation aggregates cannot yield paired seed CIs or p values. No seed records were reconstructed. R2.03 cell matching is an audit of reported values, not a prespecified test of post hoc maxima. Different R1/R2 parameter settings remain separate.
