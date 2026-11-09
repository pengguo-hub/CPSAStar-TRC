"""
run_cmpp_lifelong.py
CMPP + A-CMTS + PIBT 终身规划测试入口。

与 test_lifelong.py 使用完全相同的 BenchmarkLoader 参数，
保证地图、AGV 初始位置、任务队列与其他算法对比时初始条件一致。
"""

import sys
import os
import time
from datetime import datetime

pass  # Package imports replace process-wide import-path mutation.

from src.original_paper.experiment.Lifelong.CMPP.benchmark_loader import BenchmarkLoader
from src.original_paper.experiment.Lifelong.CMPP.lifelong_cmpp_planner import LifelongPlanner

# ============================================================================
# 配置（与 test_lifelong.py 保持一致）
# ============================================================================
MAP_FILE  = "random-64-10/random-64-64-10.map"
SCEN_FILE = "random-64-10/scen-random/random-64-64-10-random-1.scen"

NUM_AGVS   = 1000
MAX_TASKS  = 1000
MAX_CYCLES = 500
REPEAT     = 30

STRATEGY   = "random"
SEED       = 42        # 与 test_lifelong.py 保持相同

# CMPP 参数（论文推荐值）
GRAPH_STEP = 2         # 稀疏图采样步长
OMEGA      = 1.3       # 次优因子
TIME_LIMIT = 1.0       # 每步 A-CMTS 时间上限（秒）
# ============================================================================


def main():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(timestamp)
    print("=" * 60)
    print("CMPP + A-CMTS + PIBT 终身规划测试")
    print("=" * 60)

    # ── 1. 加载地图和任务（与对比算法使用相同 BenchmarkLoader）──────────
    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=NUM_AGVS,
        speed=1.0,
        strategy=STRATEGY,
        seed=SEED,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

    print(f"\n地图尺寸       : {grid.width} x {grid.height}")
    print(f"AGV 数量       : {NUM_AGVS}")
    print(f"加载任务数     : {len(task_queue)}")
    print(f"初始化策略     : {STRATEGY}  seed={SEED}")
    print(f"CMPP 稀疏图步长: {GRAPH_STEP}")
    print(f"A-CMTS omega   : {OMEGA}  time_limit={TIME_LIMIT}s")
    print("-" * 60)

    # ── 2. 创建终身规划器 ────────────────────────────────────────────────
    planner = LifelongPlanner(
        grid=grid,
        agv_info=agv_info,
        init_pos=initial_positions,
        task_queue=task_queue,
        graph_step=GRAPH_STEP,
        omega=OMEGA,
        time_limit=TIME_LIMIT,
    )

    # ── 3. 运行仿真 ──────────────────────────────────────────────────────
    wall_start = time.time()
    completed, failed = planner.run_lifelong(max_cycles=MAX_CYCLES)
    wall_elapsed = time.time() - wall_start

    # ── 4. 统计指标 ──────────────────────────────────────────────────────
    total_assigned = len(completed) + len(failed)
    success_rate = len(completed) / total_assigned * 100 if total_assigned > 0 else 0.0
    throughput = planner.get_throughput()

    print("\n" + "=" * 60)
    print("实验结果")
    print("=" * 60)
    print(f"仿真步数         : {planner.total_steps}")
    print(f"完成任务数       : {len(completed)}")
    print(f"失败任务数       : {len(failed)}")
    print(f"任务成功率       : {success_rate:.1f}%")
    print(f"吞吐量           : {throughput:.4f} 任务/步")
    print(f"算法实际运行时间 : {wall_elapsed:.2f} 秒")
    print("-" * 60)

    if completed:
        print("\n前5个完成任务：")
        for i, (agv_id, task) in enumerate(completed[:5]):
            print(f"  {i+1}. AGV={agv_id}  "
                  f"pickup={task['pickup']}  dropoff={task['dropoff']}")

    if failed:
        print(f"\n失败任务（前5个）：")
        for i, (agv_id, task) in enumerate(failed[:5]):
            print(f"  {i+1}. AGV={agv_id}  "
                  f"pickup={task.get('pickup')}  dropoff={task.get('dropoff')}")


if __name__ == "__main__":
    main()
