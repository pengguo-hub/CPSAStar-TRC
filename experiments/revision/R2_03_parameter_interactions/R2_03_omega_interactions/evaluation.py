"""R1-aligned run metrics for a complete one-shot CPS-A batch."""
import numpy as np
from vendor.CPS_A.Conflict_Field_Updater import ConflictFieldUpdater
from vendor.CPS_A.Ticket_Manager import TicketManager

RUN_METRICS = [
    "success_rate", "planning_time", "average_path_length",
    "average_waits", "average_congestion_fixed", "average_turns",
]

def records_from_planner(planner):
    records = {}
    for aid, path in planner.paths.items():
        records[aid] = {
            "path": [tuple(p) for p in path],
            "times": list(planner.agv_tasks[aid]["times"]),
        }
    return records

def fixed_gaussian(grid, records):
    updater = ConflictFieldUpdater(
        grid, TicketManager(), delta=1, k_space=1, m_time=1, sigma_space=2.0, sigma_time=2.0
    )
    for aid, item in records.items():
        updater.accumulate_path(item["path"], item["times"], aid)
    if updater.pending_paths:
        updater.batch_update_from_paths()
        updater.finalize_batch_update()
    return updater.smoothed_dict

def validate_joint_paths(grid, records):
    nodes = {}
    reverse_edges = {}
    for aid, item in records.items():
        path, times = item["path"], item["times"]
        if not path or len(path) != len(times):
            raise AssertionError("Invalid path/time lengths")
        for i, (p, t) in enumerate(zip(path, times)):
            if not (0 <= p[0] < grid.width and 0 <= p[1] < grid.height and grid.grid[p[1], p[0]] == 0):
                raise AssertionError("Path enters invalid grid cell")
            key = (p, float(t))
            if key in nodes:
                raise AssertionError(f"Node conflict {aid} with {nodes[key]}")
            nodes[key] = aid
            if i:
                prev, prev_t = path[i-1], float(times[i-1])
                if float(t) - prev_t != 1.0:
                    raise AssertionError("Unexpected time step")
                if abs(p[0]-prev[0]) + abs(p[1]-prev[1]) > 1:
                    raise AssertionError("Nonlocal move")
                if p != prev:
                    edge = (prev, p, prev_t)
                    rev = (p, prev, prev_t)
                    if rev in reverse_edges:
                        raise AssertionError("Reverse-edge conflict")
                    reverse_edges[edge] = aid
    return True

def evaluate_run(grid, tasks, planner, planning_time):
    records = records_from_planner(planner)
    validate_joint_paths(grid, records)
    fixed_field = fixed_gaussian(grid, records)
    lengths, waits, turns, ac = [], [], [], []
    for aid, item in records.items():
        path, times = item["path"], item["times"]
        moves = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(path, path[1:])]
        nonzero = [m for m in moves if m != (0,0)]
        lengths.append(sum(abs(dx)+abs(dy) for dx,dy in moves))
        waits.append(sum(m == (0,0) for m in moves))
        turns.append(sum(a != b for a,b in zip(nonzero, nonzero[1:])))
        if path:
            ac.append(float(np.mean([fixed_field.get((p[0],p[1],int(t)),0.0) for p,t in zip(path,times)])))
    def mean_or_nan(a):
        return float(np.mean(a)) if a else float("nan")
    return {
        "success_count": len(records),
        "success_rate": len(records) / len(tasks),
        "planning_time": float(planning_time),
        "average_path_length": mean_or_nan(lengths),
        "average_waits": mean_or_nan(waits),
        "average_congestion_fixed": mean_or_nan(ac),
        "average_turns": mean_or_nan(turns),
        "rollbacks": int(planner.rollback_count),
        "failed_searches": int(planner.failed_search_count),
        "field_updates": int(planner.field_update_count),
        "search_expansions": int(planner.segment_planner.expansions),
        "lookahead_evaluations": int(planner.segment_planner.lookahead_evaluations),
    }
