"""
test_rhcr.py - RHCR 对比测试脚本
接口与 test_lifelong.py 完全一致，确保实验对比公平。
"""
from pathlib import Path as _RepositoryPath
_REPO_ROOT = _RepositoryPath(__file__).resolve().parents[4]
import time
import sys
import os
from datetime import datetime

pass  # Package imports replace process-wide import-path mutation.

from src.original_paper.experiment.Lifelong.benchmark_loader import BenchmarkLoader
from src.original_paper.experiment.Lifelong.RHCR.rhcr_lifelong import RHCRPlanner

# =========================================================================
# 配置区：与 test_lifelong.py 保持完全一致
# =========================================================================
MAP_FILE  = str(_REPO_ROOT / 'data/original_paper/experiment/Lifelong/scenarios/random-64-10/random-64-64-10.map')
SCEN_FILE = str(_REPO_ROOT / 'data/original_paper/experiment/Lifelong/scenarios/random-64-10/scen-random/random-64-64-10-random-1.scen')

NUM_AGVS  = 100
MAX_TASKS = 1000
MAX_TIME  = 500
REPEAT    = 30

STRATEGY  = "random"
SEED      = 39

# RHCR 超参数（对应论文推荐设置）
W       = 10   # time horizon w
H       = 5    # replanning period h（必须 h <= w）
P       = 1    # deadlock threshold p
W_MAX   = 30   # 动态扩展上限
# =========================================================================

def run_test():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(timestamp)
    print("=" * 60)
    print("RHCR Lifelong MAPF 对比测试")
    print(f"  参数: w={W}, h={H}, p={P}, w_max={W_MAX}")
    print("=" * 60)

    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs  = NUM_AGVS,
        speed     = 1.0,
        strategy  = STRATEGY,
        seed      = SEED,
        max_tasks = MAX_TASKS,
        repeat    = REPEAT,
    )

    print(f"\n地图大小 : {grid.width} x {grid.height}")
    print(f"AGV 数量 : {NUM_AGVS}")
    print(f"任务总数 : {len(task_queue)}")
    print(f"初始化策略 : {STRATEGY}")
    print("-" * 60)

    planner = RHCRPlanner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        w=W, h=H, p=P, w_max=W_MAX,
        use_dynamic_horizon=False
    )
    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    print("\n" + "=" * 60)
    print("实验结果")
    print("=" * 60)
    print(f"仿真时间步数       : {planner.current_time}")
    print(f"完成任务数         : {len(completed)}")
    print(f"总分配任务数         : {total_assigned}")
    print(f"任务成功率         : {success_rate:.1f}%")
    print(f"吞吐量             : {throughput:.4f} 任务/时间步")
    print(f"实际运行时间   : {wall_elapsed:.2f} 秒")
    print(f"规划时间      : {pure_planning_time:.2f} 秒")
    print("-" * 60)

    return completed, planner


if __name__ == "__main__":
    run_test()
