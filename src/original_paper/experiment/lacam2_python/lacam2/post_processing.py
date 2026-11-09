"""
post_processing.py
对应 C++ 的 post_processing.hpp / post_processing.cpp

包含：
  is_feasible_solution()        — 检查解的合法性（无碰撞、连通性、起终点）
  get_makespan()                — 计算 makespan
  get_path_cost()               — 单智能体路径代价
  get_sum_of_costs()            — SoC
  get_sum_of_loss()             — SoL
  get_makespan_lower_bound()    — makespan 下界
  get_sum_of_costs_lower_bound()— SoC 下界
  print_stats()                 — 打印统计信息
  make_log()                    — 写日志文件
"""

from __future__ import annotations
import math
import os
import re
from typing import TYPE_CHECKING

from .graph import is_same_config
from .dist_table import DistTable

if TYPE_CHECKING:
    from .instance import Instance, Solution


# ======================================================================
# 可行性检查
# ======================================================================

def is_feasible_solution(ins: "Instance", solution: "Solution", verbose: int = 0) -> bool:
    """
    对应 C++ is_feasible_solution()
    检查：
      1. 起点匹配
      2. 终点匹配
      3. 每步移动连通性（只能移到邻居或原地）
      4. 顶点冲突（同一时间步两智能体在同一格）
      5. 交换冲突（两智能体互换位置）
    """
    if not solution:
        return True

    # 起点检查
    if not is_same_config(solution[0], ins.starts):
        if verbose >= 1:
            print("invalid starts")
        return False

    # 终点检查
    if not is_same_config(solution[-1], ins.goals):
        if verbose >= 1:
            print("invalid goals")
        return False

    T = len(solution)
    N = ins.N

    for t in range(1, T):
        for i in range(N):
            v_i_from = solution[t - 1][i]
            v_i_to   = solution[t][i]
            # 连通性：必须在邻居中或保持原地
            if v_i_from is not v_i_to and v_i_from not in v_i_to.neighbor:
                if verbose >= 1:
                    print(f"invalid move: agent {i} at t={t}")
                return False

            # 冲突检查
            for j in range(i + 1, N):
                v_j_from = solution[t - 1][j]
                v_j_to   = solution[t][j]
                # 顶点冲突
                if v_j_to is v_i_to:
                    if verbose >= 1:
                        print(f"vertex conflict: agents {i},{j} at t={t}")
                    return False
                # 交换冲突
                if v_j_to is v_i_from and v_j_from is v_i_to:
                    if verbose >= 1:
                        print(f"edge conflict: agents {i},{j} at t={t}")
                    return False

    return True


# ======================================================================
# 指标计算
# ======================================================================

def get_makespan(solution: "Solution") -> int:
    """对应 C++ get_makespan()：路径时间步数减 1"""
    if not solution:
        return 0
    return len(solution) - 1


def get_path_cost(solution: "Solution", i: int) -> int:
    """
    对应 C++ get_path_cost()
    单智能体 i 的路径代价 = 最后一次离开目标之后的时间步数
    （即去掉末尾连续在目标处的等待步后的长度）
    """
    makespan = len(solution)
    goal = solution[-1][i]
    c = makespan
    while c > 0 and solution[c - 1][i] is goal:
        c -= 1
    return c


def get_sum_of_costs(solution: "Solution") -> int:
    """对应 C++ get_sum_of_costs()"""
    if not solution:
        return 0
    N = len(solution[0])
    return sum(get_path_cost(solution, i) for i in range(N))


def get_sum_of_loss(solution: "Solution") -> int:
    """
    对应 C++ get_sum_of_loss()
    SoL = 每个智能体在「尚未永久到达目标」期间每步的损耗之和
    具体：对每个时间步 t in [1,T)，若 (t-1) 或 t 时刻智能体不在最终目标处，计 +1
    """
    if not solution:
        return 0
    N = len(solution[0])
    T = len(solution)
    c = 0
    for i in range(N):
        goal = solution[-1][i]
        for t in range(1, T):
            if solution[t - 1][i] is not goal or solution[t][i] is not goal:
                c += 1
    return c


def get_makespan_lower_bound(ins: "Instance", dist_table: DistTable) -> int:
    """对应 C++ get_makespan_lower_bound()：各智能体 BFS 距离的最大值"""
    lb = 0
    for i in range(ins.N):
        lb = max(lb, dist_table.get(i, ins.starts[i].id))
    return lb


def get_sum_of_costs_lower_bound(ins: "Instance", dist_table: DistTable) -> int:
    """对应 C++ get_sum_of_costs_lower_bound()：各智能体 BFS 距离之和"""
    return sum(dist_table.get(i, ins.starts[i].id) for i in range(ins.N))


# ======================================================================
# 打印统计
# ======================================================================

def print_stats(
    verbose: int,
    ins: "Instance",
    solution: "Solution",
    comp_time_ms: float,
) -> None:
    """对应 C++ print_stats()"""
    if verbose < 1:
        return

    dist_table = DistTable(ins)
    makespan       = get_makespan(solution)
    makespan_lb    = get_makespan_lower_bound(ins, dist_table)
    sum_of_costs   = get_sum_of_costs(solution)
    soc_lb         = get_sum_of_costs_lower_bound(ins, dist_table)
    sum_of_loss    = get_sum_of_loss(solution)

    def ceil2(x: float) -> float:
        return math.ceil(x * 100) / 100

    ms_ub  = ceil2(makespan / makespan_lb)    if makespan_lb > 0 else float("inf")
    soc_ub = ceil2(sum_of_costs / soc_lb)     if soc_lb > 0 else float("inf")
    sol_ub = ceil2(sum_of_loss / soc_lb)      if soc_lb > 0 else float("inf")

    print(
        f"solved: {comp_time_ms:.1f}ms"
        f"\tmakespan: {makespan} (lb={makespan_lb}, ub={ms_ub})"
        f"\tsum_of_costs: {sum_of_costs} (lb={soc_lb}, ub={soc_ub})"
        f"\tsum_of_loss: {sum_of_loss} (lb={soc_lb}, ub={sol_ub})"
    )


# ======================================================================
# 日志输出
# ======================================================================

_R_MAP_NAME = re.compile(r".+/(.+)")


def make_log(
    ins: "Instance",
    solution: "Solution",
    output_name: str,
    comp_time_ms: float,
    map_name: str,
    seed: int,
    additional_info: str,
    log_short: bool = False,
) -> None:
    """
    对应 C++ make_log()
    输出与可视化工具兼容的日志文件
    """
    # 提取地图文件名（去掉路径前缀）
    m = _R_MAP_NAME.match(map_name)
    map_recorded_name = m.group(1) if m else map_name

    dist_table = DistTable(ins)

    get_x = lambda k: k % ins.G.width
    get_y = lambda k: k // ins.G.width

    with open(output_name, "w") as log:
        log.write(f"agents={ins.N}\n")
        log.write(f"map_file={map_recorded_name}\n")
        log.write("solver=planner\n")
        log.write(f"solved={int(bool(solution))}\n")
        log.write(f"soc={get_sum_of_costs(solution)}\n")
        log.write(f"soc_lb={get_sum_of_costs_lower_bound(ins, dist_table)}\n")
        log.write(f"makespan={get_makespan(solution)}\n")
        log.write(f"makespan_lb={get_makespan_lower_bound(ins, dist_table)}\n")
        log.write(f"sum_of_loss={get_sum_of_loss(solution)}\n")
        log.write(f"sum_of_loss_lb={get_sum_of_costs_lower_bound(ins, dist_table)}\n")
        log.write(f"comp_time={comp_time_ms:.3f}\n")
        log.write(f"seed={seed}\n")
        log.write(additional_info)

        if log_short:
            return

        # 起点
        log.write("starts=")
        for i in range(ins.N):
            k = ins.starts[i].index
            log.write(f"({get_x(k)},{get_y(k)}),")
        log.write("\n")

        # 终点
        log.write("goals=")
        for i in range(ins.N):
            k = ins.goals[i].index
            log.write(f"({get_x(k)},{get_y(k)}),")
        log.write("\n")

        # 路径
        log.write("solution=\n")
        for t, config in enumerate(solution):
            log.write(f"{t}:")
            for v in config:
                log.write(f"({get_x(v.index)},{get_y(v.index)}),")
            log.write("\n")
