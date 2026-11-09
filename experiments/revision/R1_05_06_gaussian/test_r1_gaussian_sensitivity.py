"""Reviewer 1, Comments 5-6: Gaussian-field parameter sensitivity.

Run from the experiment root or directly by file path, e.g.
    python Ablation_experiment/test_r1_gaussian_sensitivity.py

The experiment is OFAT (one factor at a time):
    L       in {0,1,2,3},     with T=1, sigma_l=2, sigma_t=2
    T       in {0,1,2,3},     with L=1, sigma_l=2, sigma_t=2
    sigma_l in {0.5,1,2,4},   with L=T=1, sigma_t=2
    sigma_t in {0.5,1,2,4},   with L=T=1, sigma_l=2

For fairness, the reported evaluation congestion metric uses ONE FIXED evaluator
(L=1, T=1, sigma_l=2, sigma_t=2) for every tested configuration. Therefore the
metric itself does not change when the tested Gaussian parameters change.
"""

import copy
import csv
import json
import math
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np

from experiments.revision.R1_05_06_gaussian.map_config import ALL_MAPS
from experiments.revision.R1_05_06_gaussian.task_generator import generate_test_tasks
from experiments.revision.R1_05_06_gaussian.CPS_A.path_planner import GridMap, IntegratedAGVPlanner


# ============================================================
# 1. Experiment settings: edit only this block if needed
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_ROOT = os.path.join(BASE_DIR, "result_R1_gaussian_sensitivity")

# Two representative loads for each map, aligned with the manuscript ablation study.
# The lower value is a high-load case; the higher value is a more congested case.
TASK_COUNTS = {
    "A": [50, 70],
    "B": [250, 280],
    "C": [150, 200],
}

# Keep the same map-specific heuristic setting as the manuscript experiments:
# Map A uses congestion look-ahead in h(s); Maps B/C use Manhattan h(s) only.
# For all three maps, the Gaussian congestion field remains in g(s).
LOOKAHEAD_BY_MAP = {
    "A": True,
    "B": False,
    "C": False,
}

# Start with the same five independent seeds as the existing ablation code.
# If computation budget allows, extend to list(range(42, 52)).
SEEDS = [42, 43, 44, 45, 46]

MAP_SIZE_OVERRIDE = {
    "A": (16, 11),
    "B": (20, 20),
    "C": (20, 20),
}

# Manuscript/reference Gaussian setting.
BASELINE = {
    "L": 1,
    "T": 1,
    "sigma_l": 2.0,
    "sigma_t": 2.0,
}

# OFAT values.
SWEEPS = {
    "L": [0, 1, 2, 3],
    "T": [0, 1, 2, 3],
    "sigma_l": [0.5, 1.0, 2.0, 4.0],
    "sigma_t": [0.5, 1.0, 2.0, 4.0],
}

# Fixed evaluator for AC, so cross-parameter AC is comparable.
EVAL_FIELD = {
    "L": 1,
    "T": 1,
    "sigma_l": 2.0,
    "sigma_t": 2.0,
    "delta": 1.0,
}

# ============================================================


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def infer_map_size(shelf_map: Dict, outbound_map: Dict) -> Tuple[int, int]:
    points = []
    for coords in list(shelf_map.values()) + list(outbound_map.values()):
        if isinstance(coords, list):
            points.extend(coords)
        else:
            points.append(coords)
    return max(p[0] for p in points) + 1, max(p[1] for p in points) + 1


def build_grid(map_key: str) -> Tuple[GridMap, Dict, Dict, int, int]:
    shelf_map, outbound_map, region_values = ALL_MAPS[map_key]
    width, height = MAP_SIZE_OVERRIDE.get(
        map_key, infer_map_size(shelf_map, outbound_map)
    )
    grid = GridMap(width=width, height=height, cell_size=1)

    for region_name, coords in shelf_map.items():
        value = region_values.get(region_name, 1)
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid.region_coordinate(x, y, value)

    return grid, shelf_map, outbound_map, width, height


def build_waypoints_map(tasks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}
    for task in tasks:
        result[task["agv_id"]] = {
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
    return result


def count_wait_steps(path: List[Tuple[int, int]]) -> int:
    return sum(path[i] == path[i - 1] for i in range(1, len(path)))


def make_config(sweep_name: str, value: float) -> Dict[str, float]:
    cfg = dict(BASELINE)
    cfg[sweep_name] = value
    return cfg


def build_planner(
    grid: GridMap, cfg: Dict[str, float], map_key: str
) -> IntegratedAGVPlanner:
    return IntegratedAGVPlanner(
        grid=grid,
        k_space=int(cfg["L"]),
        m_time=int(cfg["T"]),
        sigma_space=float(cfg["sigma_l"]),
        sigma_time=float(cfg["sigma_t"]),
        use_lookahead_congestion=LOOKAHEAD_BY_MAP[map_key],
    )


def reconstruct_fixed_eval_field(planner: IntegratedAGVPlanner) -> Dict[Tuple[int, int, int], float]:
    """Reconstruct one common Gaussian field from final reservations.

    IMPORTANT: this uses EVAL_FIELD for every tested configuration. It avoids the
    invalid comparison in which each tested sigma/L/T also changes the evaluation
    metric itself.
    """
    L = int(EVAL_FIELD["L"])
    T = int(EVAL_FIELD["T"])
    sigma_l = float(EVAL_FIELD["sigma_l"])
    sigma_t = float(EVAL_FIELD["sigma_t"])
    delta = float(EVAL_FIELD["delta"])

    occupancy: Dict[Tuple[int, int, int], int] = {}
    for (node, t), agv_dict in planner.ticket_manager.node_reservations.items():
        if not agv_dict:
            continue
        x, y = node
        slot = int(float(t) // delta)
        occupancy[(int(x), int(y), slot)] = len(agv_dict)

    if not occupancy:
        return {}

    kernel = {}
    for dx in range(-L, L + 1):
        for dy in range(-L, L + 1):
            for dt in range(-T, T + 1):
                kernel[(dx, dy, dt)] = math.exp(
                    -(dx * dx + dy * dy) / (2.0 * sigma_l * sigma_l)
                    - (dt * dt) / (2.0 * sigma_t * sigma_t)
                )

    points = set()
    for x, y, slot in occupancy:
        for dx in range(-L, L + 1):
            for dy in range(-L, L + 1):
                for dt in range(-T, T + 1):
                    points.add((x + dx, y + dy, slot + dt))

    field = {}
    for cx, cy, cslot in points:
        total = 0.0
        wsum = 0.0
        for dx in range(-L, L + 1):
            for dy in range(-L, L + 1):
                for dt in range(-T, T + 1):
                    w = kernel[(dx, dy, dt)]
                    total += occupancy.get((cx + dx, cy + dy, cslot + dt), 0) * w
                    wsum += w
        field[(cx, cy, cslot)] = total / wsum if wsum else 0.0
    return field


def compute_fixed_average_congestion(
    paths: Dict[str, List[Tuple[int, int]]],
    planner: IntegratedAGVPlanner,
) -> float:
    field = reconstruct_fixed_eval_field(planner)
    if not field:
        return 0.0

    values = []
    for path in paths.values():
        if not path:
            continue
        for t, (x, y) in enumerate(path):
            slot = int(t // EVAL_FIELD["delta"])
            values.append(field.get((int(x), int(y), slot), 0.0))

    return float(np.mean(values)) if values else 0.0


def run_one(
    map_key: str,
    task_count: int,
    seed: int,
    tasks: List[Dict[str, Any]],
    sweep_name: str,
    sweep_value: float,
) -> Dict[str, Any]:
    cfg = make_config(sweep_name, sweep_value)
    grid, _, _, _, _ = build_grid(map_key)
    planner = build_planner(grid, cfg, map_key)
    waypoints_map = build_waypoints_map(copy.deepcopy(tasks))

    t0 = time.perf_counter()
    error = ""
    try:
        paths = planner.batch_plan(parsed_tasks=waypoints_map)
    except Exception as exc:
        paths = {}
        error = repr(exc)
    planning_time = time.perf_counter() - t0

    success_count = sum(bool(paths.get(aid)) for aid in waypoints_map)
    total_tasks = len(waypoints_map)
    success_rate = success_count / total_tasks if total_tasks else 0.0

    successful_paths = [p for p in paths.values() if p]
    average_path_length = (
        float(np.mean([len(p) for p in successful_paths])) if successful_paths else 0.0
    )
    average_waits = (
        float(np.mean([count_wait_steps(p) for p in successful_paths]))
        if successful_paths
        else 0.0
    )
    average_congestion_fixed = compute_fixed_average_congestion(paths, planner)

    return {
        "map": map_key,
        "task_count": task_count,
        "seed": seed,
        "sweep": sweep_name,
        "value": sweep_value,
        "L": cfg["L"],
        "T": cfg["T"],
        "sigma_l": cfg["sigma_l"],
        "sigma_t": cfg["sigma_t"],
        "use_lookahead_congestion": LOOKAHEAD_BY_MAP[map_key],
        "success_rate": success_rate,
        "planning_time": planning_time,
        "average_path_length": average_path_length,
        "average_waits": average_waits,
        "average_congestion_fixed": average_congestion_fixed,
        "error": error,
    }


def mean_std_ci95(values: List[float]) -> Tuple[float, float, float]:
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr)) if len(arr) else 0.0
    if len(arr) <= 1:
        return mean, 0.0, 0.0
    std = float(np.std(arr, ddof=1))
    ci95 = 1.96 * std / math.sqrt(len(arr))
    return mean, std, ci95


def summarize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metrics = [
        "success_rate",
        "planning_time",
        "average_path_length",
        "average_waits",
        "average_congestion_fixed",
    ]
    groups: Dict[Tuple[str, int, str, float], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (row["map"], row["task_count"], row["sweep"], float(row["value"]))
        groups.setdefault(key, []).append(row)

    output = []
    for (map_key, task_count, sweep, value), group in sorted(groups.items()):
        item = {
            "map": map_key,
            "task_count": task_count,
            "sweep": sweep,
            "value": value,
            "n": len(group),
        }
        for metric in metrics:
            mean, std, ci95 = mean_std_ci95([r[metric] for r in group])
            item[f"mean_{metric}"] = mean
            item[f"std_{metric}"] = std
            item[f"ci95_{metric}"] = ci95
        output.append(item)
    return output


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    ensure_dir(os.path.dirname(path))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(OUTPUT_ROOT, f"run_{run_stamp}")
    ensure_dir(run_dir)

    # Save exactly what was run.
    with open(os.path.join(run_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "task_counts": TASK_COUNTS,
                "lookahead_by_map": LOOKAHEAD_BY_MAP,
                "seeds": SEEDS,
                "baseline": BASELINE,
                "sweeps": SWEEPS,
                "fixed_eval_field": EVAL_FIELD,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    all_rows: List[Dict[str, Any]] = []

    for map_key, task_counts in TASK_COUNTS.items():
        _, shelf_map, outbound_map, width, height = build_grid(map_key)

        for task_count in task_counts:
            for seed in SEEDS:
                # Generate ONCE, then reuse the exact same task set for every parameter value.
                tasks = generate_test_tasks(
                    n_tasks=task_count,
                    shelf_map=shelf_map,
                    outbound_zones=outbound_map,
                    grid_width=width,
                    grid_height=height,
                    seed=seed,
                    pickup_region=None,
                    pickup_strategy="inner" if map_key == "C" else None,
                )

                for sweep_name, values in SWEEPS.items():
                    for value in values:
                        print(
                            f"[map={map_key} tasks={task_count} seed={seed}] "
                            f"{sweep_name}={value}"
                        )
                        row = run_one(
                            map_key=map_key,
                            task_count=task_count,
                            seed=seed,
                            tasks=tasks,
                            sweep_name=sweep_name,
                            sweep_value=value,
                        )
                        all_rows.append(row)
                        print(
                            "  SR={:.3f}, time={:.3f}s, APL={:.2f}, waits={:.2f}, AC_fixed={:.4f}".format(
                                row["success_rate"],
                                row["planning_time"],
                                row["average_path_length"],
                                row["average_waits"],
                                row["average_congestion_fixed"],
                            )
                        )
                        # Incremental save: a long run is not lost if interrupted.
                        write_csv(os.path.join(run_dir, "seed_results.csv"), all_rows)

    summary_rows = summarize(all_rows)
    write_csv(os.path.join(run_dir, "summary_results.csv"), summary_rows)

    print("\nFinished.")
    print("Raw seed results:", os.path.join(run_dir, "seed_results.csv"))
    print("Summary results :", os.path.join(run_dir, "summary_results.csv"))


if __name__ == "__main__":
    main()
