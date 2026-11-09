# Experiment evidence

Original paper:42 one-shot JSON files contain1,310 algorithm-seed rows, usually seeds42–46. Loads are A10–100,B100–300,C100–200. Lifelong has179 aggregate rows covering6 maps, versus8 maps in Figure9:75 custom,40 warehouse,40 random64,24 room32. Ablation has384 aggregate rows (120/132/132), plus selected-results XLSX. No individual seed outcomes are recoverable from these aggregates.

| Study | Recorded conditions |
|---|---|
| R1.3 | d_min1,2,3; A30/70,B150/280,C100/200;90 rows |
| R1 Gaussian | L,T,sigma_l,sigma_t four-value sweeps; A50/70,B250/280,C150/200;480 rows; final plot selects70/280/200 |
| R1 δ | δ1–7; fleetsA90/B250/C200; horizon500;105 rows |
| R1 retry | R0,1,3,5,7,10; A50/70,B250/280,C150/200;180 rows |
| R2.02 |3 maps×2 loads×8 representations×5 seeds; rollback off;240 runs,40,000 task rows,15 instances |
| R2.03 |sigma_l×sigma_t,L×T,gamma×sigma_l,gamma×sigma_t,gamma×K;960 joint+1,170 cross rows; plus390 omega logical rows from330 unique saved runs (Map A50/70, seeds10000–10004) |
| R2.04 |A30/50,B100/200,C80/160×3 OD modes×Full/Control×5 seeds; horizon500;180 rows |
| R2.05 |14 conditions×5 seeds; horizon500;70 trials including15 Fransen200 replacements |
| R2.07 |A50/B150/C120×all16 S/L/P/R variants×5 seeds; backlog3000,horizon500;240 rows |

R2.04 Response plots use high fleets50/200/160 (90 rows); all180 rows remain. Pooled effects average9 condition differences inside each seed. The supplied attempts cover106 directories and105 selected payloads, not every final trial.

R2.05 axes include fleet10/30/50; arrival rates0.25/0.5/1/2; tiling at fixed fleet; tiling at fixed density; Fransen OD concentration. Fixed-density changes both fleet and nominal arrival rate. Final Fransen200 cases are backlogged, not the older small-fleet Poisson cases.

R2.07's supplied default plan is30 seeds/1,440 trials; saved seeds42–46 provide240 trials. Do not conflate planned and completed counts.

R1 separate result archives are canonical. d_min/retry inner and outer ZIPs match byte-for-byte; Gaussian member contents match; δ105 sorted numerical rows match despite75+30 versus combined organization. Never count duplicates as extra repetitions. Smoke/pilot/old diagnostics are retained inside exact source archives and excluded from canonical result accounting.
