"""
multi_algo_benchmark.py

统一跑多种 Lifelong MAPF 算法（CMPP, 原基线, Guided-PIBT, RHCR）。
- 使用 BenchmarkLoader 保证相同地图/任务/初始位置。
- 支持 AGV 数量遍历（例如 [100, 200, 300]）。
- 每个 (算法, AGV 数量) 组合重复 N_RUNS 次，取均值与标准差。
- 每个 AGV 数量跑完后立即追加到 CSV，防止中途出错全白跑。
"""

import time
import sys
import os
import csv
import statistics
from datetime import datetime

# 确保当前目录在 import 路径里（与现有脚本一致）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmark_loader import BenchmarkLoader
from CPS_A_lifelong.path_planner_lifelong import LifelongPlanner as CPS_A
from RHCR.rhcr_lifelong import RHCRPlanner
from Guide_Paths.guided_pibt.lifelong_runner import GuidedPIBTRunner
from CMPP.lifelong_cmpp_planner import LifelongPlanner as CMPPPlanner
from PIBT.plain_pibt_lifelong import PIBTLifelongPlanner

# =============================
# 全局配置（按需修改）
# =============================
MAP_FILE = "random-64-10/random-64-64-10.map"
SCEN_FILE = "random-64-10/scen-random/random-64-64-10-random-1.scen"

MAX_TASKS = 1000
MAX_TIME = 500   # 对原基线、RHCR、GP-PIBT
MAX_CYCLES = 500 # 对 CMPP + A-CMTS
REPEAT = 30

STRATEGY = "random"
SEED = 39

# 要扫的 AGV 数量列表，例如 [100, 200, 300]
AGV_LIST = [100, 200, 300, 400, 500,600,700,800,900,1000]

# 每个配置重复次数
N_RUNS = 5

# 输出 CSV 路径
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_CSV = f"multi_algo_results_{TIMESTAMP}.csv"

# RHCR 参数（目前用固定 w、禁用 w++，更贴论文主实验）
RHCR_W = 10
RHCR_H = 5
RHCR_P = 1
RHCR_W_MAX = 30

# Guided-PIBT 参数（可按你的实验需要调整）
GP_R_INIT = 100
GP_REFINE_ITERS = 0
GP_GUIDANCE = True  # True = Guided-PIBT, False = 退化为 PIBT


# =============================
# 统一的单次运行封装
# =============================

def run_cpsa (num_agvs: int, seed: int):
    """你的原 LifelongPlanner 基线（path_planner_lifelong.py）。

    返回: (throughput, success_rate, wall_time)
    """
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=num_agvs,
        speed=1.0,
        strategy=STRATEGY,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

    planner = CPS_A(grid, agv_info, initial_positions, task_queue, use_priority_replan=True)

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed-planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    return throughput, success_rate, wall_elapsed, pure_planning_time


def run_rhcr(num_agvs: int, seed: int):
    """RHCR（Python 复现版）。"""
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=num_agvs,
        speed=1.0,
        strategy=STRATEGY,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

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


def run_guided_pibt(num_agvs: int, seed: int):
    """Guided-PIBT / PIBT baseline。"""
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=num_agvs,
        speed=1.0,
        strategy=STRATEGY,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

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
    pure_planning_time = wall_elapsed - stats.get("assignment_time_s",0)
    total_assigned = stats.get("tasks_assigned", 0)
    throughput = stats.get("throughput", 0.0)
    success_rate = (
        stats.get("tasks_completed", 0) / total_assigned * 100.0
        if total_assigned > 0 else 0.0
    )

    return throughput, success_rate, wall_elapsed, pure_planning_time


def run_cmpp(num_agvs: int, seed: int):
    """CMPP + A-CMTS + PIBT（lifelong_cmpp_planner）。"""
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=num_agvs,
        speed=1.0,
        strategy=STRATEGY,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

    # 参数可根据 run_cmpp_lifelong-3.py 调整
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

def run_plain_pibt(num_agvs: int, seed: int):
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=num_agvs,
        speed=1.0,
        strategy=STRATEGY,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

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

# 将算法封装成一个名字->函数的字典，方便遍历
ALGORITHMS = {
    "cps_a": run_cpsa,
    # "rhcr": run_rhcr,
    "guided_pibt": run_guided_pibt,
    "cmpp": run_cmpp,
    "pibt": run_plain_pibt,
}


# =============================
# 主流程：遍历 AGV 数量 & 算法
# =============================

def main():
    print("输出结果将写入:", OUT_CSV)
    header = [
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

    # 如果文件不存在，先写表头
    if not os.path.exists(OUT_CSV):
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)

    for num_agvs in AGV_LIST:
        print("" + "=" * 60)
        print(f"AGV 数量 = {num_agvs}")
        print("=" * 60)

        for algo_name, algo_fn in ALGORITHMS.items():
            th_list = []
            succ_list = []
            wt_list = []
            pt_list = []

            print(f"--- 算法: {algo_name} ---")

            for run_idx in range(N_RUNS):
                seed = SEED + run_idx
                print(f"  Run {run_idx+1}/{N_RUNS} ...", end="", flush=True)
                try:
                    th, succ, wt, pt = algo_fn(num_agvs,seed)
                    th_list.append(th)
                    succ_list.append(succ)
                    wt_list.append(wt)
                    pt_list.append(pt)
                    print(f" done (throughput={th:.4f}, success={succ:.1f}%, wall={wt:.2f}s, pure={pt:.2f}s)")
                except Exception as e:
                    # 如果这一轮挂了，记录 NaN，但不中断整个 sweep
                    print(" FAILED:", e)

            if not th_list:
                # 所有 run 都挂了，写一行占位，便于后续排查
                row = [
                    num_agvs,
                    algo_name,
                    0,
                    "nan",
                    "nan",
                    "nan",
                    "nan",
                    "nan",
                    "nan",
                    "nan",
                    "nan",
                ]
            else:
                def _mean(xs):
                    return sum(xs) / len(xs) if xs else float("nan")

                def _std(xs):
                    return statistics.pstdev(xs) if len(xs) > 1 else 0.0

                row = [
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

            # 每个 (num_agvs, algo) 完成后立即追加到 CSV
            with open(OUT_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

            print("  -> 结果已写入 CSV")


if __name__ == "__main__":
    main()
