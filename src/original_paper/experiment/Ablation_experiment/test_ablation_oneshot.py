import os
import csv
import json
import time
import math
from datetime import datetime
from typing import Dict, Any, List, Tuple

from src.original_paper.experiment.Ablation_experiment.map_config import ALL_MAPS
from src.original_paper.experiment.Ablation_experiment.task_generator import generate_test_tasks
from src.original_paper.experiment.Ablation_experiment.CPS_A.path_planner import GridMap, IntegratedAGVPlanner as CPS_A
from src.original_paper.experiment.Ablation_experiment.CPS_A_NC.path_planner import IntegratedAGVPlanner as CPS_A_NC
from src.original_paper.experiment.Ablation_experiment.CPS_A_NS.path_planner import IntegratedAGVPlanner as CPS_A_NS
from src.original_paper.experiment.Ablation_experiment.CPS_A_NG.path_planner import IntegratedAGVPlanner as CPS_A_NG
from src.original_paper.experiment.Ablation_experiment.CPS_A_NL.path_planner import IntegratedAGVPlanner as CPS_A_NL
from src.original_paper.experiment.Ablation_experiment.CPS_A_NR.path_planner import IntegratedAGVPlanner as CPS_A_NR
from src.original_paper.experiment.Ablation_experiment.CPS_A_NU.path_planner import IntegratedAGVPlanner as CPS_A_NU
from src.original_paper.experiment.Ablation_experiment.CPS_A_NSNL.path_planner import IntegratedAGVPlanner as CPS_A_NSNL
# ============================================================
# 用户配置区
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_ROOT = os.path.join(BASE_DIR, "result_0505test")
MAP_KEY = ["A"]
TASK_COUNTS_LIST = list(range(10, 101, 10))
SEEDS = [42, 43, 44, 45, 46]
PICKUP_REGION = None
SAVE_RESERVATIONS_JSON = False
SAVE_TASKS_JSON = True

# 如果不手动指定，会自动从地图配置推断
MAP_SIZE_OVERRIDE = {
    "A": (16, 11),
    "B": (20, 20),
    "C": (20, 20),
}

PLANNER_BUILDERS = {
    "CPS-A": lambda grid: CPS_A(grid=grid),
    "CPS-A-NC": lambda grid: CPS_A_NC(grid=grid),
    "CPS-A-NS": lambda grid: CPS_A_NS(grid=grid),
    "CPS-A-NG": lambda grid: CPS_A_NG(grid=grid),
    "CPS-A-NL": lambda grid: CPS_A_NL(grid=grid),
    "CPS_A_NSNL": lambda grid: CPS_A_NSNL(grid=grid),
    "CPS-A-NR": lambda grid: CPS_A_NR(grid=grid),
    "CPS-A-NU-1": lambda grid : CPS_A_NU(grid=grid,UPDATE_COUNT=1),
    "CPS-A-NU-10": lambda grid : CPS_A_NU(grid=grid,UPDATE_COUNT=10),
    "CPS-A-NU-20": lambda grid : CPS_A_NU(grid=grid,UPDATE_COUNT=20),
    "CPS-A-NU-30": lambda grid : CPS_A_NU(grid=grid,UPDATE_COUNT=30),
    "CPS-A-NU-40": lambda grid : CPS_A_NU(grid=grid,UPDATE_COUNT=40),
}
# ============================================================


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))


def load_agv_info(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"没有找到 AGV 信息文件: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        agv_data = json.load(f)
    for agv_id, info in agv_data.items():
        if isinstance(info.get("position"), list):
            info["position"] = tuple(info["position"])
        if "type" in info:
            info["type"] = str(info["type"]).strip()
    return agv_data


def infer_map_size(shelf_map: Dict, outbound_map: Dict) -> Tuple[int, int]:
    all_points = []
    for coords in list(shelf_map.values()) + list(outbound_map.values()):
        if isinstance(coords, list):
            all_points.extend(coords)
        else:
            all_points.append(coords)
    max_x = max(p[0] for p in all_points)
    max_y = max(p[1] for p in all_points)
    return max_x + 1, max_y + 1


def build_grid(map_key: str) -> Tuple[GridMap, Dict, Dict, Dict, int, int]:
    shelf_map, outbound_map, region_values = ALL_MAPS[map_key]
    width, height = MAP_SIZE_OVERRIDE.get(map_key, infer_map_size(shelf_map, outbound_map))
    grid = GridMap(width=width, height=height, cell_size=1)

    for region_name, coords in shelf_map.items():
        value = region_values.get(region_name, 1)
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid.region_coordinate(x, y, value)

    return grid, shelf_map, outbound_map, region_values, width, height


def build_waypoints_map(test_tasks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    waypoints_map = {}
    for task in test_tasks:
        waypoints_map[task["agv_id"]] = {
            "task_id": task["task_id"],
            "agv_position": task["agv_position"],
            "source": task["source"],
            "destination": task["destination"],
            "waypoints": [task["agv_position"], task["source"], task["destination"]],
            "constraints": task["constraints"],
        }
    return waypoints_map

def count_wait_steps(path: List[Tuple[int, int]]) -> int:
    if len(path) < 2:
        return 0
    return sum(1 for i in range(1, len(path)) if path[i] == path[i - 1])

def reconstruct_smoothed_dict_from_paths(
    grid: GridMap,
    paths: Dict[str, List[Tuple[int, int]]],
    planner: Any,
    k_space: int = 1,
    m_time: int = 1,
    sigma_space: float = 2.0,
    sigma_time: float = 2.0,
    delta: float = 1.0,
) -> Dict[Tuple[int, int, int], float]:
    import numpy as np

    if planner is None:
        return {}

    # 1) 如果该变体本身就有平滑后的冲突场，直接返回
    smoothed_dict = None
    if hasattr(planner, "conflict_updater") and planner.conflict_updater is not None:
        smoothed_dict = getattr(planner.conflict_updater, "smoothed_dict", None)

    if smoothed_dict is not None and isinstance(smoothed_dict, dict) and len(smoothed_dict) > 0:
        return smoothed_dict.copy()

    # 2) 否则，从 ticket_manager.node_reservations 读取 reservation，再统一做高斯平滑
    occupancy = {}
    for (node, t), agv_dict in planner.ticket_manager.node_reservations.items():
        if not agv_dict:
            continue
        x, y = node
        slot = int(float(t) // delta)
        occupancy[(int(x), int(y), int(slot))] = 1

    if not occupancy:
        return {}

    gaussian_kernel = {}
    for dx in range(-k_space, k_space + 1):
        for dy in range(-k_space, k_space + 1):
            for ds in range(-m_time, m_time + 1):
                weight = np.exp(
                    -(dx * dx) / (2 * sigma_space ** 2)
                    - (dy * dy) / (2 * sigma_space ** 2)
                    - (ds * ds) / (2 * sigma_time ** 2)
                )
                gaussian_kernel[(dx, dy, ds)] = weight

    points_to_smooth = set()
    for (x, y, slot) in occupancy.keys():
        for dx in range(-k_space, k_space + 1):
            for dy in range(-k_space, k_space + 1):
                for ds in range(-m_time, m_time + 1):
                    points_to_smooth.add((x + dx, y + dy, slot + ds))

    smoothed_dict = {}
    for (cx, cy, cslot) in points_to_smooth:
        total = 0.0
        wsum = 0.0

        for dx in range(-k_space, k_space + 1):
            for dy in range(-k_space, k_space + 1):
                for ds in range(-m_time, m_time + 1):
                    key = (cx + dx, cy + dy, cslot + ds)
                    count = occupancy.get(key, 0)
                    w = gaussian_kernel[(dx, dy, ds)]
                    total += count * w
                    wsum += w

        smoothed_dict[(cx, cy, cslot)] = total / wsum if wsum > 0 else 0.0

    return smoothed_dict

def compute_system_congestion_ratio(
    grid: GridMap,
    paths: Dict[str, List[Tuple[int, int]]],
    planner: Any = None,
) -> Dict[str, Any]:
    occupied_points = set()
    for path in paths.values():
        for t, pos in enumerate(path):
            occupied_points.add((int(pos[0]), int(pos[1]), int(t)))

    if len(occupied_points) == 0:
        return {
            "average_congestion": 0.0,
            "num_occupied_points": 0,
        }

    smoothed_dict = reconstruct_smoothed_dict_from_paths(grid=grid, paths=paths, planner=planner)
    # 在占用点上取平均值
    total = 0.0
    count = 0
    for key in occupied_points:
        total += smoothed_dict.get(key, 0.0)
        count += 1

    avg_congestion = total / count if count > 0 else 0.0

    return {
        "average_congestion": avg_congestion,
        "num_occupied_points": count,
    }


def save_json(path: str, data: Any) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_csv_row(csv_path: str, row: Dict[str, Any], fieldnames: List[str]) -> None:
    ensure_dir(os.path.dirname(csv_path))
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_single_experiment(
    planner_name: str,
    planner_builder,
    grid: GridMap,
    waypoints_map: Dict[str, Dict[str, Any]],
    map_key: str,
    task_count: int,
    seed: int,
    save_dir: str,
) -> Dict[str, Any]:
    planner = planner_builder(grid)

    start_time = time.time()
    try:
        result_paths = planner.batch_plan(parsed_tasks=waypoints_map)
        run_success = True
        error_message = ""
    except Exception as e:
        result_paths = {}
        run_success = False
        error_message = repr(e)
    planning_time = time.time() - start_time

    success_count = sum(1 for agv_id in waypoints_map if agv_id in result_paths and result_paths[agv_id])
    total_tasks = len(waypoints_map)
    success_rate = success_count / total_tasks if total_tasks > 0 else 0.0

    total_path_length = sum(len(result_paths[agv_id]) for agv_id in result_paths if result_paths[agv_id])
    average_path_length = total_path_length / success_count if success_count > 0 else 0.0

    total_waits = sum(count_wait_steps(result_paths[agv_id]) for agv_id in result_paths if result_paths[agv_id])
    average_waits = total_waits / success_count if success_count > 0 else 0.0

    congestion_stats = compute_system_congestion_ratio(grid=grid, paths=result_paths, planner=planner)

    run_record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "planner": planner_name,
        "map_key": map_key,
        "task_count": task_count,
        "seed": seed,
        "planning_time": round(planning_time, 6),
        "success_rate": round(success_rate, 6),
        "success_count": int(success_count),
        "total_tasks": int(total_tasks),
        "total_path_length": int(total_path_length),
        "average_path_length": round(average_path_length, 6),
        "total_waits": int(total_waits),
        "average_waits": round(average_waits, 6),
        "run_success": bool(run_success),
        "error_message": error_message,
        **congestion_stats,
    }

    base_name = f"{sanitize_filename(planner_name)}__{sanitize_filename(map_key)}__tasks_{task_count}__seed_{seed}"
    save_json(os.path.join(save_dir, f"{base_name}__metrics.json"), run_record)
    save_json(os.path.join(save_dir, f"{base_name}__paths.json"), result_paths)

    if SAVE_RESERVATIONS_JSON and hasattr(planner, "ticket_manager"):
        tm = planner.ticket_manager
        reservation_dump = {
            "node_reservations": [
                {
                    "position": [key[0][0], key[0][1]],
                    "time": key[1],
                    "agvs": value,
                }
                for key, value in tm.node_reservations.items()
            ],
            "edge_reservations": [
                {
                    "from": [key[0][0], key[0][1]],
                    "to": [key[1][0], key[1][1]],
                    "time": key[2],
                    "agvs": value,
                }
                for key, value in tm.edge_reservations.items()
            ],
        }
        save_json(os.path.join(save_dir, f"{base_name}__reservations.json"), reservation_dump)

    return run_record

def summarize_group(rows, planner_name, map_key, task_count) -> Dict[str, Any]:
    if not rows:
        return {
            "planner": planner_name,
            "map_key": map_key,
            "task_count": task_count,
            "num_seeds": 0,
        }

    def mean_and_std(key: str):
        vals = [float(r[key]) for r in rows]
        n = len(vals)
        mean = sum(vals) / n
        if n > 1:
            var = sum((v - mean) ** 2 for v in vals) / (n - 1)
            std = math.sqrt(var)
        else:
            std = 0.0
        return round(mean, 6), round(std, 6)

    mpt, spt = mean_and_std("planning_time")
    msr, ssr = mean_and_std("success_rate")
    mac, sac = mean_and_std("average_congestion")
    mapl, sapl = mean_and_std("average_path_length")
    maw, saw = mean_and_std("average_waits")

    return {
        "planner": planner_name,
        "map_key": map_key,
        "task_count": task_count,
        "num_seeds": len(rows),
        "mean_planning_time": mpt,
        "std_planning_time": spt,
        "mean_success_rate": msr,
        "std_success_rate": ssr,
        "mean_average_congestion": mac,
        "std_average_congestion": sac,
        "mean_average_path_length": mapl,
        "std_average_path_length": sapl,
        "mean_average_waits": maw,
        "std_average_waits": saw,
    }


def main() -> None:
    ensure_dir(OUTPUT_ROOT)

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = os.path.join(OUTPUT_ROOT, f"run_{MAP_KEY}_{run_timestamp}")
    raw_dir = os.path.join(run_root, "raw")
    summary_dir = os.path.join(run_root, "summary")
    ensure_dir(raw_dir)
    ensure_dir(summary_dir)

    if SAVE_TASKS_JSON:
        ensure_dir(os.path.join(run_root, "tasks"))

    seed_csv = os.path.join(summary_dir, "seed_results.csv")
    summary_csv = os.path.join(summary_dir, "summary_results.csv")

    seed_fieldnames = [
        "planner",
        "map_key",
        "task_count",
        "seed",
        "success_rate",  # 成功率
        "planning_time",
        "average_congestion",  # AC: 平均拥堵
        "average_path_length",  # APL
        "average_waits",  # AW
    ]

    summary_fieldnames = [
        "planner", "map_key", "task_count", "num_seeds",
        "mean_planning_time", "std_planning_time",
        "mean_success_rate", "std_success_rate",
        "mean_average_congestion", "std_average_congestion",
        "mean_average_path_length", "std_average_path_length",
        "mean_average_waits", "std_average_waits",
    ]

    grouped_rows = {}

    for map_key in MAP_KEY:
        grid_template, shelf_map, outbound_map, _, width, height = build_grid(map_key)

        for task_count in TASK_COUNTS_LIST:
            task_dir = os.path.join(raw_dir, sanitize_filename(map_key), f"tasks_{task_count}")
            ensure_dir(task_dir)

            for seed in SEEDS:
                print(f"\n[Map]={map_key},[task_count]={task_count},[seed]={seed}\n")
                test_tasks = generate_test_tasks(
                    n_tasks=task_count,
                    shelf_map=shelf_map,
                    outbound_zones=outbound_map,
                    grid_width=width,
                    grid_height=height,
                    seed=seed,
                    pickup_region=PICKUP_REGION,
                    pickup_strategy='inner' if map_key == 'RING' else None,
                )
                waypoints_map = build_waypoints_map(test_tasks)

                if SAVE_TASKS_JSON:
                    save_json(
                        os.path.join(run_root, "tasks", f"{sanitize_filename(map_key)}__tasks_{task_count}__seed_{seed}.json"),
                        test_tasks,
                    )

                for planner_name, planner_builder in PLANNER_BUILDERS.items():
                    grid, _, _, _, _, _ = build_grid(map_key)
                    run_record = run_single_experiment(
                        planner_name=planner_name,
                        planner_builder=planner_builder,
                        grid=grid,
                        waypoints_map=waypoints_map,
                        map_key=map_key,
                        task_count=task_count,
                        seed=seed,
                        save_dir=task_dir,
                    )
                    row_for_csv = {k: run_record[k] for k in seed_fieldnames}
                    append_csv_row(seed_csv, row_for_csv, seed_fieldnames)
                    grouped_rows.setdefault((planner_name, map_key, task_count), []).append(run_record)
                    print(
                        f"planner={planner_name}"
                        f"success_rate={run_record['success_rate']:.4f} time={run_record['planning_time']:.4f}s "
                        f"SCR={run_record['average_congestion']:.4f}"
                    )

    summary_json = {}
    for key, rows in grouped_rows.items():
        planner_name, map_key, task_count = key
        summary_row = summarize_group(rows, planner_name, map_key, task_count)
        append_csv_row(summary_csv, summary_row, summary_fieldnames)
        summary_json.setdefault(planner_name, {}).setdefault(map_key, {})[str(task_count)] = summary_row

    save_json(os.path.join(summary_dir, "summary_results.json"), summary_json)
    save_json(
        os.path.join(run_root, "run_config.json"),
        {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "output_root": OUTPUT_ROOT,
            "map_keys": MAP_KEY,
            "task_counts_list": TASK_COUNTS_LIST,
            "seeds": SEEDS,
            "pickup_region": PICKUP_REGION,
            "planner_names": list(PLANNER_BUILDERS.keys()),
        },
    )

    print(f"\n所有实验完成，结果保存在: {run_root}")


if __name__ == "__main__":
    main()
