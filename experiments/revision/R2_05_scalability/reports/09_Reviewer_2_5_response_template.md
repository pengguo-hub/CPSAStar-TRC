# Reviewer 2, Comment 5 — pre-results template

**Not submission-ready. Formal trials have not been run. Do not insert smoke values.**

> 5. Strengthen the scalability analysis by systematically varying fleet size, map size, task arrival rate, and congestion level.

Thank you for this suggestion. We have prepared a controlled scalability study based on the archived Lifelong CPS-A* implementation. The study retains its original search, reservation rules, greedy task matching, pickup–delivery transitions, and failure requeueing. An explicit release interface supports open-demand experiments, and passive records capture task lifetimes and timing. The original backlogged baseline is evaluated separately from open-demand workloads.

The design varies (i) fleet size, 10/30/50 AGVs on Map A (16×11); (ii) map dimensions, 16×11/32×22/48×33 at 30 AGVs and a fixed arrival intensity of 0.5 requests per step; (iii) proportional expansion to 30/120/270 AGVs with arrival intensities of 0.5/2.0/4.5; (iv) arrival intensity, 0.25/0.5/1.0/2.0 at 30 AGVs; and (v) three matched OD couplings on the unchanged FRANSEN map. All trials span 500 simulation steps with no warm-up. The formal seed set is 1001–1005. No search-expansion limit or per-trial wall-clock timeout is imposed.

[After formal execution: report the number of valid trials out of 70, all incomplete trials and their reasons, and the per-condition sample sizes. Cite the raw-audit table.]

[Insert the formal fleet, map, arrival, and traffic results with 95% confidence intervals across independent seeds. Distinguish completed/released fraction from the original completed/net-assigned success rate. Report cumulative batch planning time, original pure time, and end-to-end wall time separately.]

For the traffic-demand experiment, release times, the origin sequence, initial vehicle positions, origin-specific reference transport distances, and destination marginal counts are matched. We measure realized short-headway cell-sharing exposure outside service-point neighbourhoods. The input labels describe fixed OD pairings; they are not assumed to establish ordered realized congestion levels. [Report the observed response and paired uncertainty. If it is non-monotonic, disclose that outcome and avoid a low/medium/high congestion claim.]

The evidence concerns the archived simulation implementation and its measured computational behavior. It does not establish a new physical collision-correctness guarantee or unrestricted large-scale real-time performance. [Insert final figure/table identifiers, manuscript section and line references, and a conclusion supported by the formal results.]

After all 70 trials pass the raw-data audit, `python postprocess.py --input results_formal` creates the numerical draft from formal data. The author must review its interpretation and replace manuscript cross-reference placeholders before submission.
