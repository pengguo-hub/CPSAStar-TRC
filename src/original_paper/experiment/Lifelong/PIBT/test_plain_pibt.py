import time
import sys
import os
from datetime import datetime

pass  # Package imports replace process-wide import-path mutation.

import importlib.util, sys, os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_module(module_name: str, file_name: str):
    path = os.path.join(_BASE_DIR, file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BenchmarkLoader = _load_module("benchmark_loader", "benchmark_loader.py").BenchmarkLoader
from src.original_paper.experiment.Lifelong.PIBT.plain_pibt_lifelong import PIBTLifelongPlanner

MAP_FILE = "random-64-10/random-64-64-10.map"
SCEN_FILE = "random-64-10/scen-random/random-64-64-10-random-1.scen"

NUM_AGVS = 1000
MAX_TASKS = 1000
MAX_TIME = 500
REPEAT = 30

STRATEGY = "random"
SEED = 40


def run_test():
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(timestamp)
    print("=" * 60)
    print("Plain PIBT Lifelong MAPD 测试")
    print("=" * 60)

    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, initial_positions, task_queue = loader.load_all(
        num_agvs=NUM_AGVS,
        speed=1.0,
        strategy=STRATEGY,
        seed=SEED,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
    )

    print(f"\n地图大小 : {grid.width} x {grid.height}")
    print(f"AGV 数量 : {NUM_AGVS}")
    print(f"任务总数 : {len(task_queue)}")
    print(f"初始化策略 : {STRATEGY}")
    print("-" * 60)

    planner = PIBTLifelongPlanner(
        grid=grid,
        agv_info=agv_info,
        initial_positions=initial_positions,
        task_queue=task_queue,
        seed=SEED,
        max_steps=MAX_TIME,
        print_every=10,
    )

    wall_start = time.time()
    completed, total_assigned = planner.run_lifelong(max_time=MAX_TIME)
    wall_elapsed = time.time() - wall_start
    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    success_rate = len(completed) / total_assigned * 100 if total_assigned > 0 else 0.0

    finish_times = []
    for agv_id, task in completed:
        if task.get('assigned_time') is not None and task.get('completed_time') is not None:
            duration = task['completed_time'] - task['assigned_time']
            finish_times.append(duration)
    avg_finish_time = sum(finish_times) / len(finish_times) if finish_times else 0.0

    print("\n" + "=" * 60)
    print("实验结果")
    print("=" * 60)
    print(f"仿真时间步数 : {planner.current_time}")
    print(f"完成任务数 : {len(completed)}")
    print(f"总分配任务数 : {total_assigned}")
    print(f"任务成功率 : {success_rate:.1f}%")
    print(f"吞吐量 : {throughput:.4f} 任务/时间步")
    print(f"平均任务完成时间 : {avg_finish_time:.1f} 时间步")
    print(f"算法运行时间 : {wall_elapsed:.2f} 秒")
    print(f"算法规划时间 : {pure_planning_time:.2f} 秒")
    print("-" * 60)

    return completed, planner


if __name__ == "__main__":
    run_test()
