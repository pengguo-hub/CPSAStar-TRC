"""
test_guided_pibt.py
===================
Lifelong Guided-PIBT 测试脚本。
与 test_lifelong-2.py 风格完全一致，直接替换算法即可对比。

算法变体（对应论文表格）：
  guidance=True,  R_init=100, refine_iters=0   → GP-R100
  guidance=True,  R_init=100, refine_iters=10  → GP-R100-Re10
  guidance=False, R_init=100, refine_iters=0   → PIBT baseline
"""
from pathlib import Path as _RepositoryPath
_REPO_ROOT = _RepositoryPath(__file__).resolve().parents[4]

import time
import sys
import os
from datetime import datetime

pass  # Package imports replace process-wide import-path mutation.

from src.original_paper.experiment.Lifelong.benchmark_loader import BenchmarkLoader
from src.original_paper.experiment.Lifelong.Guide_Paths.guided_pibt.lifelong_runner import GuidedPIBTRunner

# =========================================================================
# 配置区
# =========================================================================
MAP_FILE  = str(_REPO_ROOT / 'data/original_paper/experiment/Lifelong/scenarios/random-64-10/random-64-64-10.map')
SCEN_FILE = str(_REPO_ROOT / 'data/original_paper/experiment/Lifelong/scenarios/random-64-10/scen-random/random-64-64-10-random-1.scen')

NUM_AGVS   = 1000
MAX_TASKS  = 1000
MAX_TIME   = 500     # 最大仿真步数（论文建议 (width+height)*5 = 640）
REPEAT     = 30

STRATEGY   = "random"
SEED       = 42

# Guided-PIBT 参数
R_INIT       = 100   # 每步最多 lazy-init 多少条 guide path（GP-R100）
REFINE_ITERS = 0    # 每步 LNS 迭代次数（Re10）；0=不精化
GUIDANCE     = True  # False=退化为纯 PIBT baseline
# =========================================================================

timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(timestamp)


def run_test():
    print("=" * 60)
    print("Lifelong Guided-PIBT 测试")
    print("=" * 60)

    # 1. 加载地图和任务
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
    print(f"算法变体     : GP-R{R_INIT}{'-Re'+str(REFINE_ITERS) if REFINE_ITERS>0 else ''}"
          f"{'' if GUIDANCE else ' (PIBT baseline)'}")
    print("-" * 60)

    # 2. 初始化 runner
    runner = GuidedPIBTRunner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        R_init=R_INIT,
        refine_iters=REFINE_ITERS,
        guidance=GUIDANCE,
    )

    # 3. 运行
    wall_start = time.time()
    completed, stats = runner.run(max_timesteps=MAX_TIME)
    wall_elapsed = time.time() - wall_start

    # 4. 结果输出（与 test_lifelong-2.py 格式一致）
    total_assigned = stats["tasks_assigned"]
    success_rate = (
        stats["tasks_completed"] / total_assigned * 100
        if total_assigned > 0 else 0.0
    )

    print("\n" + "=" * 60)
    print("实验结果")
    print("=" * 60)
    print(f"仿真时间步数       : {stats['timesteps']}")
    print(f"完成任务数         : {stats['tasks_completed']}")
    print(f"分配任务数         : {total_assigned}")
    print(f"任务成功率         : {success_rate:.1f}%")
    print(f"吞吐量             : {stats['throughput']:.4f} 任务/时间步")
    print(f"平均任务完成时间   : {stats['avg_task_time']:.1f} 时间步")
    print(f"平均取件时间       : {stats['avg_pickup_time']:.1f} 时间步")
    print(f"算法实际运行时间   : {wall_elapsed:.2f} 秒")
    print("-" * 60)

    return completed, stats, runner


if __name__ == "__main__":
    completed, stats, runner = run_test()
