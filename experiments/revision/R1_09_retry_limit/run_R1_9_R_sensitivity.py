import os
import sys
import csv
import json
import time
import math
import copy
import random
import shutil
from datetime import datetime
from statistics import mean, stdev

# Make imports independent of the current working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    pass  # Package imports replace process-wide import-path mutation.

from experiments.revision.R1_09_retry_limit.map_config import ALL_MAPS
from experiments.revision.R1_09_retry_limit.CPS_A.path_planner import GridMap, IntegratedAGVPlanner




def is_point_on_shelf(x, y, shelf_map):
    """Same shelf test used by the original one-shot task generator."""
    target = (x, y)
    for coords in shelf_map.values():
        if isinstance(coords, list):
            if target in coords:
                return True
        elif isinstance(coords, tuple):
            if target == coords:
                return True
    return False


def sample_free_point(grid_width, grid_height, shelf_map):
    """Same free-cell sampling rule used by the original task generator."""
    while True:
        x = random.randint(0, grid_width - 1)
        y = random.randint(0, grid_height - 1)
        if is_point_on_shelf(x, y, shelf_map):
            continue
        return [x, y]


def generate_valid_pickup_positions(shelf_map, grid_width, grid_height):
    """Free cells directly adjacent (4-neighborhood) to shelf cells."""
    shelf_set = set()
    for coords in shelf_map.values():
        if isinstance(coords, list):
            shelf_set.update(coords)
        elif isinstance(coords, tuple):
            shelf_set.add(coords)

    pickup_positions = set()
    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    for sx, sy in shelf_set:
        for dx, dy in directions:
            nx, ny = sx + dx, sy + dy
            if not (0 <= nx < grid_width and 0 <= ny < grid_height):
                continue
            if (nx, ny) not in shelf_set:
                pickup_positions.add((nx, ny))
    return list(pickup_positions)


def generate_test_tasks(n_tasks, shelf_map, outbound_zones,
                        grid_width, grid_height, seed=None):
    """
    Reproduces the task-generation logic used by
    Ablation_experiment/task_generator.py for these A/B/C experiments.
    """
    if seed is not None:
        random.seed(seed)

    valid_pickups = generate_valid_pickup_positions(
        shelf_map, grid_width, grid_height
    )
    if not valid_pickups:
        raise ValueError("No valid pickup position found.")

    outbound_list = []
    for coords in outbound_zones.values():
        outbound_list.extend(coords)

    tasks = []
    used_positions = set()

    for i in range(n_tasks):
        task_id = i + 1
        agv_id = f"AGV-{i + 1:03d}"

        while True:
            pos = tuple(sample_free_point(grid_width, grid_height, shelf_map))
            if pos not in used_positions:
                used_positions.add(pos)
                break

        source = list(random.choice(valid_pickups))
        destination = random.choice(outbound_list)
        priority = random.choices(
            ["emergency", "high", "normal"], weights=[1, 2, 7]
        )[0]

        tasks.append({
            "task_id": task_id,
            "agv_id": agv_id,
            "agv_position": list(pos),
            "source": source,
            "destination": destination,
            "constraints": {
                "priority": priority,
                "time_limit": None,
            },
        })

    return tasks


# ============================================================
# R1.9 experiment configuration
# ============================================================
# R = maximum number of bounded-rollback/replanning attempts per failed AGV.
R_VALUES = [0, 1, 3, 5, 7, 10]

# Keep EXACTLY the same map-specific h(s) setting used in the final R1.5/R1.6 experiments.
# A: Manhattan + congestion look-ahead
# B/C: Manhattan only
# Note: the Gaussian current-congestion term in g(s) remains enabled on all three maps.
LOOKAHEAD_BY_MAP = {
    "A": True,
    "B": False,
    "C": False,
}

# Use the same representative dense one-shot loads as the existing
# ablation / Gaussian-sensitivity experiments.
TASK_COUNTS = {
    "A": [50, 70],
    "B": [250, 280],
    "C": [150, 200],
}

SEEDS = [42, 43, 44, 45, 46]

MAP_SIZE = {
    "A": (16, 11),
    "B": (20, 20),
    "C": (20, 20),
}

OUTPUT_ROOT = os.path.join(BASE_DIR, "result_R1_9_R_sensitivity")
# ============================================================


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def build_grid(map_key):
    """Build exactly the same obstacle grid used by the one-shot ablation code."""
    shelf_map, outbound_map, region_values = ALL_MAPS[map_key]
    width, height = MAP_SIZE[map_key]
    grid = GridMap(width=width, height=height, cell_size=1)

    for region_name, coords in shelf_map.items():
        value = region_values.get(region_name, 1)
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid.region_coordinate(x, y, value)

    return grid, shelf_map, outbound_map, width, height


def build_waypoints_map(tasks):
    """Convert generated tasks to the input format expected by CPS-A*."""
    waypoints_map = {}
    for task in tasks:
        waypoints_map[task["agv_id"]] = {
            "task_id": task["task_id"],
            "agv_position": task["agv_position"],
            "source": task["source"],
            "destination": task["destination"],
            "waypoints": [
                task["agv_position"],
                task["source"],
                task["destination"],
            ],
            "constraints": task["constraints"],
        }
    return waypoints_map


def run_one(map_key, task_count, seed, r_value, base_waypoints):
    """Run one independent CPS-A* instance with a specified R."""
    grid, _, _, _, _ = build_grid(map_key)

    planner = IntegratedAGVPlanner(
        grid=grid,
        max_replan_per_agv=r_value,
        use_lookahead=LOOKAHEAD_BY_MAP[map_key],
    )

    # batch_plan changes waypoint lists to tuples, so each R must receive
    # its own deep copy to ensure a strictly controlled comparison.
    waypoints = copy.deepcopy(base_waypoints)

    t0 = time.perf_counter()
    try:
        paths = planner.batch_plan(parsed_tasks=waypoints)
        run_ok = True
        error = ""
    except Exception as exc:
        paths = {}
        run_ok = False
        error = repr(exc)
    planning_time = time.perf_counter() - t0

    success_count = sum(
        1 for agv_id in base_waypoints
        if agv_id in paths and paths[agv_id]
    )
    success_rate = success_count / task_count if task_count else 0.0

    return {
        "map": map_key,
        "task_count": task_count,
        "seed": seed,
        "R": r_value,
        "success_count": success_count,
        "total_tasks": task_count,
        "success_rate": success_rate,
        "planning_time": planning_time,
        "rollback_count": getattr(planner, "rollback_count", 0),
        "failed_search_count": getattr(planner, "failed_search_count", 0),
        "run_ok": int(run_ok),
        "error": error,
    }


def append_csv(path, row, fieldnames):
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def ci95(values):
    """95% normal-approximation CI half-width, used only for plotting/reporting."""
    if len(values) <= 1:
        return 0.0
    return 1.96 * stdev(values) / math.sqrt(len(values))


def summarize(rows):
    success = [r["success_rate"] for r in rows]
    times = [r["planning_time"] for r in rows]
    rollbacks = [r["rollback_count"] for r in rows]
    failed_searches = [r["failed_search_count"] for r in rows]

    return {
        "map": rows[0]["map"],
        "task_count": rows[0]["task_count"],
        "R": rows[0]["R"],
        "n_runs": len(rows),
        "success_mean": mean(success),
        "success_std": stdev(success) if len(success) > 1 else 0.0,
        "success_ci95": ci95(success),
        "planning_time_mean": mean(times),
        "planning_time_std": stdev(times) if len(times) > 1 else 0.0,
        "planning_time_ci95": ci95(times),
        "rollback_mean": mean(rollbacks),
        "rollback_std": stdev(rollbacks) if len(rollbacks) > 1 else 0.0,
        "failed_search_mean": mean(failed_searches),
        "failed_search_std": stdev(failed_searches) if len(failed_searches) > 1 else 0.0,
    }




def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(OUTPUT_ROOT, f"run_{timestamp}")
    ensure_dir(run_dir)

    raw_csv = os.path.join(run_dir, "raw_results.csv")
    summary_csv = os.path.join(run_dir, "summary_results.csv")
    config_json = os.path.join(run_dir, "config.json")

    config = {
        "experiment": "R1.9 bounded-rollback retry-limit sensitivity",
        "R_values": R_VALUES,
        "task_counts": TASK_COUNTS,
        "seeds": SEEDS,
        "original_R": 5,
        "lookahead_by_map": LOOKAHEAD_BY_MAP,
        "note": (
            "Only R is varied. The map-specific heuristic setting is kept identical "
            "to the final R1.5/R1.6 experiments: A uses congestion look-ahead in h(s), "
            "B/C use Manhattan-only h(s); all three maps retain Gaussian congestion in g(s). "
            "Map layout, task generator, Gaussian field parameters, and update interval are unchanged."
        ),
    }
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    raw_fields = [
        "map", "task_count", "seed", "R",
        "success_count", "total_tasks", "success_rate",
        "planning_time", "rollback_count", "failed_search_count",
        "run_ok", "error",
    ]

    all_rows = []

    for map_key in ["A", "B", "C"]:
        _, shelf_map, outbound_map, width, height = build_grid(map_key)

        for task_count in TASK_COUNTS[map_key]:
            for seed in SEEDS:
                # Generate the task set ONCE and reuse it for every R value.
                tasks = generate_test_tasks(
                    n_tasks=task_count,
                    shelf_map=shelf_map,
                    outbound_zones=outbound_map,
                    grid_width=width,
                    grid_height=height,
                    seed=seed,
                )
                base_waypoints = build_waypoints_map(tasks)

                for r_value in R_VALUES:
                    print(
                        f"[Map {map_key}] tasks={task_count:3d} "
                        f"seed={seed} R={r_value} ...",
                        flush=True,
                    )
                    row = run_one(
                        map_key=map_key,
                        task_count=task_count,
                        seed=seed,
                        r_value=r_value,
                        base_waypoints=base_waypoints,
                    )
                    all_rows.append(row)
                    append_csv(raw_csv, row, raw_fields)
                    print(
                        f"    success={100*row['success_rate']:.2f}% "
                        f"time={row['planning_time']:.3f}s "
                        f"rollbacks={row['rollback_count']}"
                    )

    summary_rows = []
    for map_key in ["A", "B", "C"]:
        for task_count in TASK_COUNTS[map_key]:
            for r_value in R_VALUES:
                rows = [
                    r for r in all_rows
                    if r["map"] == map_key
                    and r["task_count"] == task_count
                    and r["R"] == r_value
                ]
                summary_rows.append(summarize(rows))

    summary_fields = [
        "map", "task_count", "R", "n_runs",
        "success_mean", "success_std", "success_ci95",
        "planning_time_mean", "planning_time_std", "planning_time_ci95",
        "rollback_mean", "rollback_std",
        "failed_search_mean", "failed_search_std",
    ]
    for row in summary_rows:
        append_csv(summary_csv, row, summary_fields)

    # Package the whole result folder so the standalone plotting script can read it directly.
    zip_base = os.path.join(BASE_DIR, "result_R1_9_R_sensitivity")
    zip_path = shutil.make_archive(
        zip_base,
        "zip",
        root_dir=BASE_DIR,
        base_dir="result_R1_9_R_sensitivity",
    )

    print("\nR1.9 experiment completed.")
    print(f"Results: {run_dir}")
    print(f"Summary: {summary_csv}")
    print(f"ZIP    : {zip_path}")


if __name__ == "__main__":
    main()
