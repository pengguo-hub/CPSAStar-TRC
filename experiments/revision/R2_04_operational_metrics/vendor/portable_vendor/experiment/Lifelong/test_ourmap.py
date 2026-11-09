"""
multi_algo_benchmark_custom_test.py

一次性跑完自定义地图上的四种 Lifelong MAPF 算法：
- 地图: STANDARD / FRANSEN / RING
- 算法: CPS_A / RHCR / Guided-PIBT / CMPP + A-CMTS
- 每个 (地图, AGV数量, 算法) 重复 N_RUNS 次
- 每完成一个 (地图, AGV数量, 算法) 就立即追加保存 CSV，防止中途异常导致结果丢失
"""

import time
import sys
import os
import csv
import statistics
from datetime import datetime

pass  # Package imports replace process-wide import-path mutation.

from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.custom_benchmark_loader import CustomBenchmarkLoader
from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.path_planner_lifelong import LifelongPlanner as CPS_A
from RHCR.rhcr_lifelong import RHCRPlanner
from Guide_Paths.guided_pibt.lifelong_runner import GuidedPIBTRunner
from CMPP.lifelong_cmpp_planner import LifelongPlanner as CMPPPlanner
from PIBT.plain_pibt_lifelong import PIBTLifelongPlanner

# =============================
# 全局配置
# =============================
MAP_AGV_LISTS = {
    "STANDARD": [10, 30, 50, 70, 90],
    "RING": [40, 80, 120, 160, 200],
    "FRANSEN": [50, 100, 150, 200, 250]
}

MAX_TASKS = 100
MAX_TIME = 500
MAX_CYCLES = 500
REPEAT = 30
SEED = 39
N_RUNS = 5
SPEED = 1.0

FORBID_OUTBOUND_INIT = False
PICKUP_STRATEGY = None
PICKUP_REGION = None

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_CSV = f"test_ourmaps_results_{TIMESTAMP}.csv"

RHCR_W = 10
RHCR_H = 5
RHCR_P = 1
RHCR_W_MAX = 30

GP_R_INIT = 100
GP_REFINE_ITERS = 0
GP_GUIDANCE = True


# =============================
# 公共输入构建
# =============================
def build_inputs(map_name: str, num_agvs: int, seed: int):
    loader = CustomBenchmarkLoader(map_name)
    return loader.load_all(
        num_agvs=num_agvs,
        speed=SPEED,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
        forbid_outbound_init=FORBID_OUTBOUND_INIT,
        pickup_strategy=PICKUP_STRATEGY,
        pickup_region=PICKUP_REGION,
    )


# =============================
# 单次运行封装
# =============================
def run_cpsa(map_name: str, num_agvs: int, seed: int):
    grid, agv_info, initial_positions, task_queue = build_inputs(map_name, num_agvs, seed)
    initial_total_tasks=len(task_queue)
    planner = CPS_A(
        grid,
        agv_info,
        initial_positions,
        task_queue,
        use_priority_replan=True,
    )

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    return throughput, success_rate, wall_elapsed, pure_planning_time


def run_rhcr(map_name: str, num_agvs: int, seed: int):
    grid, agv_info, initial_positions, task_queue = build_inputs(map_name, num_agvs, seed)
    initial_total = len(task_queue)

    planner = RHCRPlanner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        w=RHCR_W,
        h=RHCR_H,
        p=RHCR_P,
        w_max=RHCR_W_MAX,
        use_dynamic_horizon=False,
    )

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    return throughput, success_rate, wall_elapsed, pure_planning_time

def run_guided_pibt(map_name: str, num_agvs: int, seed: int):
    grid, agv_info, initial_positions, task_queue = build_inputs(map_name, num_agvs, seed)

    runner = GuidedPIBTRunner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        R_init=GP_R_INIT,
        refine_iters=GP_REFINE_ITERS,
        guidance=GP_GUIDANCE,
    )

    wall_start = time.perf_counter()
    _, stats = runner.run(max_timesteps=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - stats.get("assignment_time_s", 0)
    total_assigned = stats.get("tasks_assigned", 0)
    throughput = stats.get("throughput", 0.0)
    success_rate = (
        stats.get("tasks_completed", 0) / total_assigned * 100.0
        if total_assigned > 0 else 0.0
    )

    return throughput, success_rate, wall_elapsed, pure_planning_time


def run_cmpp(map_name: str, num_agvs: int, seed: int):
    grid, agv_info, initial_positions, task_queue = build_inputs(map_name, num_agvs, seed)

    planner = CMPPPlanner(
        grid=grid,
        agv_info=agv_info,
        init_pos=initial_positions,
        task_queue=task_queue,
        graph_step=2,
        omega=1.3,
        time_limit=0.1,
    )

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_cycles=MAX_CYCLES)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    return throughput, success_rate, wall_elapsed, pure_planning_time

def run_plain_pibt(map_name:str, num_agvs: int, seed: int):
    grid, agv_info, initial_positions, task_queue = build_inputs(map_name, num_agvs, seed)

    planner = PIBTLifelongPlanner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        seed=seed,
        max_steps=MAX_TIME,
        print_every=10,
    )

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = len(completed) / total_assigned * 100 if total_assigned > 0 else 0.0

    return throughput, success_rate, wall_elapsed, pure_planning_time

ALGORITHMS = {
    "cps_a": run_cpsa,
    "rhcr": run_rhcr,
    "guided_pibt": run_guided_pibt,
    "cmpp": run_cmpp,
    "pibt":run_plain_pibt,
}


# =============================
# 主流程
# =============================
# =============================
# 主流程
# =============================
def main():
    print("输出结果将写入:", OUT_CSV)

    header = [
        "map_name",
        "num_agvs",
        "algo",
        "runs",
        "throughput_mean",
        "throughput_std",
        "success_mean",
        "success_std",
        "puretime_mean",
        "puretime_std",
        "walltime_mean",
        "walltime_std",
    ]

    if not os.path.exists(OUT_CSV):
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)

    # ← 必须保留三层循环：地图 → AGV数量 → 算法
    for map_name, agv_list in MAP_AGV_LISTS.items():
        print("\n" + "#" * 80)
        print(f"开始地图: {map_name}")
        print("#" * 80)

        for num_agvs in agv_list:
            print("\n" + "=" * 60)
            print(f"地图 = {map_name} | AGV 数量 = {num_agvs}")
            print("=" * 60)

            for algo_name, algo_fn in ALGORITHMS.items():
                th_list = []
                succ_list = []
                wt_list = []
                pt_list = []

                print(f"--- 算法: {algo_name} ---")

                for run_idx in range(N_RUNS):
                    seed = SEED + run_idx
                    print(f" Run {run_idx + 1}/{N_RUNS} | seed={seed} ...", end="", flush=True)
                    try:
                        th, succ, wt, pt = algo_fn(map_name, num_agvs, seed)  # ← 传 map_name
                        th_list.append(th)
                        succ_list.append(succ)
                        wt_list.append(wt)
                        pt_list.append(pt)
                        print(f" done (throughput={th:.4f}, success={succ:.1f}%, wall={wt:.2f}s, pure={pt:.2f}s)")
                    except Exception as e:
                        print(" FAILED:", e)

                if not th_list:
                    row = [
                        map_name,
                        num_agvs,
                        algo_name,
                        0,
                        "nan", "nan",
                        "nan", "nan",
                        "nan", "nan",
                        "nan", "nan",
                    ]
                else:
                    def _mean(xs):
                        return sum(xs) / len(xs) if xs else float("nan")

                    def _std(xs):
                        return statistics.pstdev(xs) if len(xs) > 1 else 0.0

                    row = [
                        map_name,  # ← 必须有！
                        num_agvs,
                        algo_name,
                        len(th_list),
                        f"{_mean(th_list):.6f}",
                        f"{_std(th_list):.6f}",
                        f"{_mean(succ_list):.6f}",
                        f"{_std(succ_list):.6f}",
                        f"{_mean(pt_list):.6f}",
                        f"{_std(pt_list):.6f}",
                        f"{_mean(wt_list):.6f}",
                        f"{_std(wt_list):.6f}",
                    ]

                with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)

                print(f" -> 当前结果已写入 CSV: map={map_name}, num_agvs={num_agvs}, algo={algo_name}")

    print("\n全部实验完成。结果文件:", OUT_CSV)


if __name__ == "__main__":
    main()
