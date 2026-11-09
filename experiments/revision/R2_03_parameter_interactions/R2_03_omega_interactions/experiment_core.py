"""One complete paired one-shot CPS-A execution for a single parameter configuration."""
import time
from controlled_planner import ControlledPlanner
from instances import build_grid, parsed_tasks, agv_info
from evaluation import evaluate_run

def run_trial(instance, config):
    config.validate()
    map_name = instance["map"]
    tasks = instance["tasks"]
    grid = build_grid(map_name)
    planner = ControlledPlanner(grid, agv_info(tasks, config), map_name, config)
    t0 = time.perf_counter()
    planner.batch_plan(parsed_tasks(tasks))
    elapsed = time.perf_counter() - t0
    metrics = evaluate_run(grid, tasks, planner, elapsed)
    return {
        **metrics,
        "map": map_name,
        "task_count": int(instance["task_count"]),
        "seed": int(instance["seed"]),
        "task_hash": instance["task_hash"],
        "use_lookahead_congestion": bool(planner.segment_planner.use_lookahead_congestion),
        "alpha": config.alpha,
        "beta": config.beta,
        "gamma": config.gamma,
        "omega": config.omega,
        "L": config.L,
        "T": config.T,
        "sigma_l": config.sigma_l,
        "sigma_t": config.sigma_t,
        "update_interval": config.update_interval,
    }
