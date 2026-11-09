"""
guided_pibt 包
==============
对应 GitHub: nobodyczcz/Guided-PIBT/guided-pibt/

包含 Lifelong MAPF 的完整实现：
  shared_env.py       — SharedEnv / ActionModel（对应 C++ SharedEnv.h, ActionModel.h）
  mapf_planner.py     — MAPFPlanner（核心：online guide path + PIBT，对应 MAPFPlanner.cpp）
  competition_system.py — CompetitionSystem（仿真主循环 + 任务分配）
  lifelong_runner.py  — 对接 BenchmarkLoader 的高层入口

使用方式：
    from guided_pibt.lifelong_runner import GuidedPIBTRunner
    runner = GuidedPIBTRunner(grid, agv_info, initial_positions, task_queue)
    completed, stats = runner.run(max_timesteps=3200)
"""

from .lifelong_runner import GuidedPIBTRunner

__all__ = ["GuidedPIBTRunner"]
