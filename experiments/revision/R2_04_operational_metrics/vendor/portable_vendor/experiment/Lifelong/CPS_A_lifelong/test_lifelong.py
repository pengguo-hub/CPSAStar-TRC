import time
import sys
import os
from datetime import datetime
# ── 确保当前目录在 import 路径里 ──
pass  # Package imports replace process-wide import-path mutation.

from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.benchmark_loader import BenchmarkLoader
from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.path_planner_lifelong import LifelongPlanner

# =========================================================================
# 配置区：修改这里的参数
# =========================================================================
MAP_FILE  = "random-64-10/random-64-64-10.map"  # MovingAI .map 文件路径
SCEN_FILE = "random-64-10/scen-random/random-64-64-10-random-1.scen"  # MovingAI .scen 文件路径

NUM_AGVS   = 1000    # AGV 数量
MAX_TASKS  = 1000    # 任务总数（跑完这些任务后统计指标）
MAX_TIME = 500  # 安全上限，不让程序死循环
REPEAT = 30

STRATEGY = "random"   # 初始位置策略：'random' 或 'from_scen'
SEED     = 40         # 随机种子，保证可复现
# =========================================================================
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(timestamp)

def run_test():
    print("=" * 60)
    print("Lifelong MAPF 测试")
    print("=" * 60)

    # ── 1. 加载地图和任务 ──
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=NUM_AGVS,
        speed=1.0,
        strategy=STRATEGY,
        seed=SEED,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

    print(f"\n地图大小     : {grid.width} x {grid.height}")
    print(f"AGV 数量     : {NUM_AGVS}")
    print(f"任务总数     : {len(task_queue)}")
    print(f"初始化策略   : {STRATEGY}")
    print("-" * 60)

    planner = LifelongPlanner(grid, agv_info, initial_positions, task_queue, use_priority_replan=True)

    wall_start = time.perf_counter()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.perf_counter() - wall_start
    pure_planning_time = wall_elapsed-planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = (len(completed) / total_assigned * 100.0) if total_assigned > 0 else 0.0

    print("\n" + "=" * 60)
    print("实验结果")
    print("=" * 60)
    print(f"仿真时间步数       : {planner.current_time:.1f}")
    print(f"完成任务数         : {len(completed)}")
    print(f"总分配任务数         : {len(total_assigned)}")
    print(f"任务成功率         : {success_rate:.1f}%")
    print(f"吞吐量             : {throughput:.4f} 任务/时间步")
    print(f"代码总运行时间   : {wall_elapsed:.2f} 秒")
    print(f"规划时间： {pure_planning_time:.2f} 秒")
    print("-" * 60)

    return completed, planner

if __name__ == "__main__":
    completed, planner = run_test()
