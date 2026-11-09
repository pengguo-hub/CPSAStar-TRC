"""
lacam2 Python 包
对应 C++ guided-lacam2 的 one-shot MAPF 求解器

公开接口：
  Instance  — 问题实例（地图 + 起点/终点）
  solve()   — 主求解函数
  Objective — 优化目标枚举
  Deadline  — 时间限制
  is_feasible_solution, print_stats, make_log — 后处理工具
"""

from .graph import Vertex, Graph, Config, is_same_config, config_hash
from .instance import Instance, Solution
from .dist_table import DistTable
from .planner import Objective, Deadline, solve
from .post_processing import (
    is_feasible_solution,
    get_makespan,
    get_sum_of_costs,
    get_sum_of_loss,
    print_stats,
    make_log,
)

__all__ = [
    "Vertex", "Graph", "Config", "is_same_config", "config_hash",
    "Instance", "Solution",
    "DistTable",
    "Objective", "Deadline", "solve",
    "is_feasible_solution", "get_makespan", "get_sum_of_costs",
    "get_sum_of_loss", "print_stats", "make_log",
]
