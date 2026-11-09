# Metric definitions and censoring

Let M=3000 requests, H=500 simulation steps, release rᵢ=0, completion cᵢ (undefined if unfinished), and eᵢ=min(cᵢ,H), with eᵢ=H for unfinished tasks. For each request, the recorder partitions its observed lifetime [rᵢ,eᵢ) into **unassigned queue time Qᵢ**, **assigned stationary time Aᵢ**, and **assigned movement time Dᵢ**. A request can be requeued; every such queue interval is included. Assignment includes travel toward pickup and toward dropoff. Idle unassigned AGVs do not add request waiting time.

| Output column | Definition | Interpretation and unit |
|---|---|---|
| `throughput` | completed requests /500 | tasks per simulation step |
| `waiting_time` | Σ(Qᵢ+Aᵢ)/3000 | Restricted total waiting, steps per supplied request |
| `flow_time` | Σ(eᵢ−rᵢ)/3000 | Restricted mean flow time through500, steps per supplied request |
| `queue_length` | Σₜ unassigned_queue(t) /500 | Mean unassigned task queue, tasks |
| `static_congestion_potential` | frozen S(π) in DESIGN.md | Expected shared internal vertices per distinct OD pair; input variable |

**These time endpoints differ from completed-only waiting/flow and from the old R2-04 followup100 protocol.** They use all3000 predetermined tasks and the complete500-step window. They are not estimates of the eventual untruncated mean time to complete all3000 tasks. An uncompleted task remains right-censored; its completion and untruncated flow time stay null in the ledger. No unobserved outcome is filled with zero.

Assigned stationary time records every step where an assigned AGV's position does not change, including planning-related waiting, reservation waiting and other native nonmovement. It is not labeled exclusively as congestion-caused delay. Likewise, queue length is the number of unassigned tasks, not the count of vehicles queued at an intersection.

The two primary time endpoints intentionally retain the large backlog. A sizeable throughput gain may produce a much smaller percentage change in mean waiting/flow because many requests are still waiting at500. This is a property of the requested fixed3000-task, fixed500-step design. Dropping unfinished tasks to enlarge the apparent effect would change the population being compared.

## Exact identities and interpretation

Every request satisfies Qᵢ+Aᵢ+Dᵢ=eᵢ−rᵢ. Consequently,

\[
\overline F_H=\overline W_H+\overline D_H,
\qquad
\overline F_H=\frac{H}{M}(\overline Q+\overline{\mathrm{assigned\ WIP}}).
\]

The second equality uses the average count of assigned, unfinished requests. This is a finite-window accounting identity for the fixed initial batch; no steady-state assumption is needed. Thus queue length and restricted flow time are strongly related, and four favorable endpoints do not constitute four statistically independent proofs. They are external operational outcomes, separate from the planner's internal congestion-field cost.

## Auxiliary columns

- `queue_waiting_time` = ΣQᵢ/M; `execution_stall_time` = ΣAᵢ/M; `movement_time` = ΣDᵢ/M.
- `assigned_wip`: mean number of assigned unfinished tasks; `active_stalled_queue`: mean number of assigned AGVs stationary during the next step. The latter describes a count of stationary assigned vehicles, not a spatially delineated traffic queue.
- `mean_active_fraction`: mean assigned AGVs divided by fleet size. An active AGV may be stationary; this is task occupancy, not moving utilization.
- `completed_only_flow`, `completed_only_total_waiting`, `completed_only_service_time` and `completed_only_stall_time`: descriptions of tasks completed within500; the completion cohort may differ between arms, so these are auxiliary and not substituted for the fixed-cohort primary metrics.
- `planning_attempts`, `planning_failures`, `requeues`: native planning and task-lifecycle events, useful for explaining service performance. A failed path attempt within a successfully completed500-step trial is not a failed trial.
- Wall-clock/planning timing columns are available but not central to the throughput comparison. Throughput is normalized by simulation time, not CPU time.

## Independent audit

`analyze.py` checks frozen sources, workload hashes, selected-attempt receipts and all500 intervals. It reconstructs queue membership and assignments from release/assignment/requeue/pickup/completion events, compares them with each timeline record and all501 position frames, and recomputes Qᵢ,Aᵢ,Dᵢ and core metrics. It verifies endpoint positions at pickup/completion, task conservation, exact per-request time balance and the two aggregate identities above. This audits recorded operations; it is not a new collision-safety certification of the unchanged planner.

Incomplete observations are audited separately and excluded from the affected paired estimate. Both sides' records remain present. The main plot uses paired arm samples; error bars are95% t intervals across independent seeds, not across the500 correlated time steps. The paired-difference interval in CSV is the inferential comparison; overlap of two marginal mean error bars is not a paired significance test.
