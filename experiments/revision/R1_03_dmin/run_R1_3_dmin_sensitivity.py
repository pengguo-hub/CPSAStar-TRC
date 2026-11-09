from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from experiments.revision.R1_03_dmin.map_config import ALL_MAPS
from experiments.revision.R1_03_dmin.task_generator import generate_test_tasks
from experiments.revision.R1_03_dmin.CPS_A.path_planner import GridMap, IntegratedAGVPlanner

# ============================================================
# Reviewer 1 - Comment 3: d_min sensitivity
# Directly runnable self-contained experiment.
#
# Formal run:
#   python run_R1_3_dmin_sensitivity.py
#
# Small smoke test:
#   python run_R1_3_dmin_sensitivity.py --quick
# ============================================================

DMIN_VALUES = [1, 2, 3]
SEEDS = [42, 43, 44, 45, 46]

# Keep the same one-shot load settings used in the revision experiments.
TASK_COUNTS = {
    "A": [30, 70],
    "B": [150, 280],
    "C": [100, 200],
}

MAP_SIZE = {
    "A": (16, 11),
    "B": (20, 20),
    "C": (20, 20),
}

# Required heuristic convention:
# Map A: Manhattan + look-ahead congestion.
# Map B/C: Manhattan only.
USE_LOOKAHEAD_CONGESTION = {
    "A": True,
    "B": False,
    "C": False,
}

OUTPUT_ROOT_NAME = "result_R1_3_dmin_sensitivity"
ZIP_OUTPUT_NAME = "result_R1_3_dmin_sensitivity.zip"
SAVE_TASKS = True


def build_grid(map_key: str) -> Tuple[GridMap, Dict, Dict, int, int]:
    shelf_map, outbound_map, region_values = ALL_MAPS[map_key]
    width, height = MAP_SIZE[map_key]
    grid = GridMap(width=width, height=height, cell_size=1)

    for region_name, coords in shelf_map.items():
        value = region_values.get(region_name, 1)
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid.region_coordinate(x, y, value)

    return grid, shelf_map, outbound_map, width, height


def build_waypoints_map(test_tasks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {}
    for task in test_tasks:
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


def mean_std_ci95(values: Sequence[float]) -> Tuple[float, float, float]:
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(vals) / n
    if n == 1:
        return mean, 0.0, 0.0
    variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
    std = math.sqrt(variance)
    ci95 = 1.96 * std / math.sqrt(n)
    return mean, std, ci95


def count_wait_steps(path: List[Tuple[int, int]]) -> int:
    if len(path) < 2:
        return 0
    return sum(path[i] == path[i - 1] for i in range(1, len(path)))


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def evaluate_paths(paths: Dict[str, List[Tuple[int, int]]], total_tasks: int) -> Dict[str, float]:
    successful = [p for p in paths.values() if p]
    success_count = len(successful)
    success_rate = success_count / total_tasks if total_tasks else 0.0
    avg_path_length = (
        sum(len(p) for p in successful) / success_count if success_count else 0.0
    )
    avg_wait_steps = (
        sum(count_wait_steps(p) for p in successful) / success_count
        if success_count else 0.0
    )
    return {
        "success_count": success_count,
        "total_tasks": total_tasks,
        "success_rate": success_rate,
        "average_path_length": avg_path_length,
        "average_wait_steps": avg_wait_steps,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a tiny smoke test only. Omit this flag for the formal experiment.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    output_root = script_dir / OUTPUT_ROOT_NAME

    if args.quick:
        dmin_values = [1, 2]
        seeds = [42]
        task_counts = {"A": [8], "B": [10], "C": [10]}
    else:
        dmin_values = DMIN_VALUES
        seeds = SEEDS
        task_counts = TASK_COUNTS

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    tasks_dir = run_dir / "tasks"
    if SAVE_TASKS:
        tasks_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "formal_run": not args.quick,
        "d_min_values": dmin_values,
        "seeds": seeds,
        "task_counts": task_counts,
        "high_load_for_plot": {"A": 70, "B": 280, "C": 200},
        "heuristic": {
            "A": "Manhattan + look-ahead congestion",
            "B": "Manhattan only",
            "C": "Manhattan only",
        },
        "d_min_rule": "candidate rejected when Manhattan distance to another same-time reservation is < d_min",
        "unchanged_CPS_A_settings": {
            "gamma_current_congestion_in_g": 5.0,
            "omega_lookahead": 50.0,
            "L": 1,
            "T": 1,
            "sigma_l": 2.0,
            "sigma_t": 2.0,
            "delta": 1,
            "field_update_interval": 20,
            "rollback_R": 5,
        },
    }
    (run_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    seed_rows: List[Dict[str, Any]] = []

    for map_key in ["A", "B", "C"]:
        _, shelf_map, outbound_map, width, height = build_grid(map_key)

        for task_count in task_counts[map_key]:
            for seed in seeds:
                # Generate once, then reuse exactly the same task instance
                # for every d_min value in this (map, load, seed) block.
                test_tasks = generate_test_tasks(
                    n_tasks=task_count,
                    shelf_map=shelf_map,
                    outbound_zones=outbound_map,
                    grid_width=width,
                    grid_height=height,
                    seed=seed,
                )
                base_waypoints = build_waypoints_map(test_tasks)

                if SAVE_TASKS:
                    task_file = tasks_dir / f"Map_{map_key}_{task_count}_seed_{seed}.json"
                    task_file.write_text(
                        json.dumps(test_tasks, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                for d_min in dmin_values:
                    grid, _, _, _, _ = build_grid(map_key)
                    planner = IntegratedAGVPlanner(
                        grid=grid,
                        d_min=d_min,
                        use_lookahead_congestion=USE_LOOKAHEAD_CONGESTION[map_key],
                    )

                    tasks = copy.deepcopy(base_waypoints)
                    print(
                        f"[Map {map_key}] tasks={task_count}, seed={seed}, d_min={d_min}",
                        flush=True,
                    )

                    t0 = time.perf_counter()
                    error = ""
                    try:
                        paths = planner.batch_plan(parsed_tasks=tasks)
                    except Exception as exc:
                        paths = {}
                        error = repr(exc)
                    planning_time = time.perf_counter() - t0

                    metrics = evaluate_paths(paths, task_count)
                    seed_rows.append(
                        {
                            "map": map_key,
                            "task_count": task_count,
                            "seed": seed,
                            "d_min": d_min,
                            "lookahead_in_heuristic": USE_LOOKAHEAD_CONGESTION[map_key],
                            **metrics,
                            "planning_time": planning_time,
                            "error": error,
                        }
                    )

                    print(
                        f"  success={metrics['success_rate']:.2%}, "
                        f"APL={metrics['average_path_length']:.2f}, "
                        f"wait={metrics['average_wait_steps']:.2f}, "
                        f"time={planning_time:.3f}s",
                        flush=True,
                    )

    seed_fields = [
        "map", "task_count", "seed", "d_min", "lookahead_in_heuristic",
        "success_count", "total_tasks", "success_rate",
        "average_path_length", "average_wait_steps", "planning_time", "error",
    ]
    write_csv(run_dir / "seed_results.csv", seed_rows, seed_fields)

    summary_rows: List[Dict[str, Any]] = []
    for map_key in ["A", "B", "C"]:
        for task_count in task_counts[map_key]:
            for d_min in dmin_values:
                rows = [
                    r for r in seed_rows
                    if r["map"] == map_key
                    and r["task_count"] == task_count
                    and r["d_min"] == d_min
                ]

                sr_m, sr_s, sr_ci = mean_std_ci95([r["success_rate"] for r in rows])
                apl_m, apl_s, apl_ci = mean_std_ci95([r["average_path_length"] for r in rows])
                wait_m, wait_s, wait_ci = mean_std_ci95([r["average_wait_steps"] for r in rows])
                pt_m, pt_s, pt_ci = mean_std_ci95([r["planning_time"] for r in rows])

                summary_rows.append({
                    "map": map_key,
                    "task_count": task_count,
                    "d_min": d_min,
                    "n_runs": len(rows),
                    "success_mean": sr_m,
                    "success_std": sr_s,
                    "success_ci95": sr_ci,
                    "average_path_length_mean": apl_m,
                    "average_path_length_std": apl_s,
                    "average_path_length_ci95": apl_ci,
                    "average_wait_steps_mean": wait_m,
                    "average_wait_steps_std": wait_s,
                    "average_wait_steps_ci95": wait_ci,
                    "planning_time_mean": pt_m,
                    "planning_time_std": pt_s,
                    "planning_time_ci95": pt_ci,
                })

    summary_fields = [
        "map", "task_count", "d_min", "n_runs",
        "success_mean", "success_std", "success_ci95",
        "average_path_length_mean", "average_path_length_std", "average_path_length_ci95",
        "average_wait_steps_mean", "average_wait_steps_std", "average_wait_steps_ci95",
        "planning_time_mean", "planning_time_std", "planning_time_ci95",
    ]
    write_csv(run_dir / "summary_results.csv", summary_rows, summary_fields)

    zip_path = script_dir / ZIP_OUTPUT_NAME
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in run_dir.rglob("*"):
            if f.is_file():
                arc = Path(OUTPUT_ROOT_NAME) / run_dir.name / f.relative_to(run_dir)
                zf.write(f, arc.as_posix())

    print("\nDone.")
    print("Run directory:", run_dir)
    print("Result ZIP:", zip_path)


if __name__ == "__main__":
    main()
