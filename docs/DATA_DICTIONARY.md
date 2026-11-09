# Data dictionary

| Fields | Meaning / limitation |
|---|---|
|seed|Recorded independent analysis block within study|
|task_seed,task_hash,workload_hash|Matching identifiers, unchanged|
|case,trial_id,variant|Native identifiers; duplicates are not extra runs|
|map A/B/C|STANDARD/FRANSEN/RING|
|task_count|One-shot requests, not lifelong fleet|
|num_agvs,fleet|Lifelong fleet size|
|success_rate|Usually fraction; plots may multiply100|
|throughput|Completed tasks per simulated step|
|planning_time,planning_seconds|Study-specific planning seconds|
|instrumented_pure_seconds|R2.07 loop-minus-assignment timing; Table4|
|original_formula_pure_seconds|Native loop-minus-assignment timing in R2.04/05|
|wall_time,wall_seconds|Broader elapsed time|
|R2.04 waiting_time,flow_time|Horizon-restricted, normalized over all3,000 requests|
|R2.05/07 waiting_time,flow_time|Completed-task measures; all-arrived/restricted alternatives separate|
|queue_length|Mean unassigned queue, not all unfinished requests|
|final_queue,backlog,unfinished|Distinct native accounting quantities|
|neutral_congestion_exposure|R2.02 neutral metric; task intersection required for reported contrasts|
|gaussian_AC/field exposure|Representation-dependent metric|
|R2.07 S,L,P,R|Binary smoothing/look-ahead/priority/rollback factors|
|R1 R|Multi-valued retry limit|
|status,eligible|Original completion/quality flags|
|code_hash,execution_hash|Historical execution identity, not portable source hash|
|summary n,runs,num_seeds|Reported aggregate sample count; not raw seed observations|

RESULTS_MANIFEST records each expanded result's hash,size,granularity,columns,rows,seeds. Observed condition tables are in statistics. Historical local paths in immutable provenance are nonexecuted evidence.
