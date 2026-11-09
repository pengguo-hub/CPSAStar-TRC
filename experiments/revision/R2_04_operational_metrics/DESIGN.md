# Fixed OD congestion modes and a saturated lifelong workload

## Question and contrasts

Two contrasts are kept distinct:

1. **Mode contrast:** within a map, fleet, arm and seed, compare intermediate or shared OD modes against dispersed. This evaluates the operational consequences of changing a geometry-defined input characteristic while holding the endpoint marginals and each request's loaded shortest distance fixed.
2. **Algorithm contrast:** within a map, fleet, OD mode and seed, compare Full against Control. This evaluates the original two soft congestion terms under exactly matched exogenous workloads.

Neither contrast establishes that the static score equals realized congestion. In particular, the static score cannot decrease from Control to Full because it is an identical precomputed input for the two arms. No post-run trajectory congestion measure is used as this study's explanatory variable.

## Frozen matrix and protocol

STANDARD: 30/50 AGVs; FRANSEN: 100/200; RING: 80/160. Three modes per map, two arms, formal seeds39–43, smoke seeds7–8. Each trial receives3000 tasks at t=0, keeps the original lifelong assignment/replanning loop and stops at500 simulation steps. There is no arrival rate, warmup, artificial trial timeout, active MAX_EXPAND cap, forced route or new lifelong engine. AGV speed is1 grid edge per step, as in the supplied baseline. A remaining backlog at500 is an observed outcome, not a failed trial.

The obstacle arrays come directly from the supplied R2-04 maps. **FRANSEN uses the exact endpoint lists and three permutations in R2-05's `configs/traffic_couplings.json`. STANDARD and RING use new fixed experimental service nodes on existing free cells.** They are not claimed to reproduce the original outbound-station distribution. No obstacle, lane or traversable cell is changed.

## Static score: all shortest paths, before planning

For origin i and assigned destination π(i), let Pᵢ be the set of all unweighted, four-neighbor shortest paths on the static obstacle map. Let V° omit every origin and destination and every free cell within graph distance1 of any such endpoint. Define

\[
q_i(v)=\frac{\#\{p\in P_i:v\in p\}}{|P_i|},\qquad
S(\pi)=\frac{1}{\binom{8}{2}}\sum_{i<j}\sum_{v\in V^\circ}q_i(v)q_j(v).
\]

S is the mean expected number of shared internal vertices for two distinct OD motifs with independent uniformly sampled shortest paths. It is **not** a probability of collision, a normalized percentage, a temporal exposure measure, an internal reservation-field value, or a count of actual blocked vehicles. Paths traversing a shared vertex in opposite directions also contribute. It does not include overlap between repetitions of the same OD motif. The score is used to order modes **within a map**; absolute scores are not calibrated across maps or fleets.

Fleet size and OD overlap are separate factors. Increasing N changes the number of potentially active vehicles, while changing the permutation changes their spatial demand pattern. The static S itself is intentionally independent of N. More vehicles therefore do not mechanically increase this score, and no formula equates vehicle count with realized traffic congestion. Their interaction is evaluated through observed performance.

Shortest-path counts are calculated by BFS from each endpoint. For a shortest-path vertex v, the probability equals count(origin→v) × count(v→destination) / count(origin→destination). Thus no arbitrary single-shortest-path tie-break determines a mode's score. The resulting paths are never supplied to CPS-A*.

## Permutation selection and controls

There are8 fixed origins and8 fixed destinations per map. Each mode is a bijection between these sets. A permutation is admissible only if the vector of eight origin-specific shortest distances exactly matches the frozen reference vector. All40320 permutations are enumerated, then:

- dispersed: admissible minimum S;
- shared: admissible maximum S;
- intermediate: admissible S nearest the midpoint of the minimum and maximum.

FRANSEN directly reuses the R2-05 choice. For STANDARD and RING, three predefined geometry-only endpoint candidates per map were screened for the greatest score span divided by mean loaded shortest distance. Within each endpoint candidate, permutations were grouped by their exact origin-specific distance vector; the group with the largest normalized span and at least three admissible permutations was selected. The best endpoint candidate was then retained. Candidate details are recorded in `provenance/geometry_candidates.json`; `provenance/reproduce_geometry_candidates.py` reproduces this screening without simulations. This selection preceded the smoke runs and used no Full/Control performance values. No endpoint, permutation or horizon was changed after inspecting smoke performance. `verify_inputs.py` independently recomputes all scores and the three chosen levels for the final fixed endpoint sets.

| Map | Feasible permutations | Distance vector by origin | Dispersed S | Intermediate S | Shared S |
|---|---:|---|---:|---:|---:|
| STANDARD | 8 | 14,8,12,10,10,12,8,14 | 0.428571 | 0.785714 | 1.428571 |
| FRANSEN | 16 | 16,16,16,16,21,21,21,21 | 0.725940 | 1.153159 | 1.659697 |
| RING | 16 | 20,20,20,20,20,20,20,20 | 2.222973 | 2.912343 | 3.481945 |

The machine-readable `configs/od_patterns.json` is authoritative; all72 OD entries, coordinates and distances are also listed in `validation/input_checks/OD_PAIRINGS.csv`.

## Task lists, matching and initial positions

Each task list contains375 consecutive blocks, each with one request from each of the8 origins. Within each block, origins are randomly permuted using an isolated `Random(seed+701)` generator. Each origin and destination therefore appears exactly375 times. Request IDs, origin order, release times and per-request intrinsic shortest distances are identical across modes and fleets for the same map and seed; only the matched destination changes between modes. The list is supplied to the original task queue in one operation.

The original allocator is retained; supplying all tasks does not mean assigning all3000 tasks to vehicles at once. The native dispatcher examines its original candidate queue and chooses assignments. Pickup approach travel, future reassignments and realized route length remain endogenous outcomes; they are not artificially matched.

Initial cells exclude the common endpoint buffer defined above. Remaining free cells are shuffled with `Random(seed+101)`; the first N cells initialize N AGVs. Initial positions are exactly matched across modes and arms. Lower-fleet positions are a prefix of higher-fleet positions. Initial parking capacities are70/300/256 for STANDARD/FRANSEN/RING, sufficient for50/200/160 agents. Frozen workload hashes and their components are written before execution.

## Full and Control

Full retains the supplied CPS-A* soft wait-action congestion coefficient1 and the local congestion priority coefficient0.5. Control suppresses these two reads using the unchanged `mechanism.py`. Control still computes the congestion field and retains the same reservation tables, conflict checks, age/base priority terms, rollback, assignment, MAX_WAIT=2 and original planner modules. This is a joint ablation of two soft terms, not a comparison against another routing algorithm and not a separate manipulation of congestion exposure.

## Analysis plan

The independent unit is seed. There is no time-step pseudoreplication. Report each condition's Full and Control means, Δ=Full−Control, paired95% t interval, n, and relative difference to Control. Positive throughput Δ is favorable; negative waiting/flow/queue Δ is favorable. Mode contrasts preserve within-seed pairing and are separate comparisons; no repeated dispersed baseline is pooled as an independent observation.

The output includes exact two-sided sign-flip p values and Holm correction across four primary endpoints per comparison. The paired t p value is supplementary. With five nonzero paired differences the smallest attainable exact two-sided p value is0.0625; five seeds support effect estimation but have limited power for significance claims. Smoke n=2 is a functionality and effect-scale check, not formal inference. No data-dependent seed extension or favorable-condition selection is implemented.

The audit verifies each complete trial before pairing, retains failed and partial runs without zero imputation, and never removes an unfavorable complete run. The main figure uses valid Full/Control pairs. The separate mode comparisons require complete matching seeds for that specific within-arm comparison.

## Claim supported by this design

A defensible result sentence has the form: “Under preassigned OD patterns with increasing static shortest-path overlap, the Full/Control throughput difference was [measured effect], accompanied by [waiting/flow/queue effects], with [cross-map pattern].” Whether the effect is beneficial, small or reversed is determined by the formal data. A rise in static S does not guarantee a monotonic decline in every performance metric: S omits timing, pickup approaches, dispatch order, dynamic rerouting and reservation interactions. These are part of the system being tested.
