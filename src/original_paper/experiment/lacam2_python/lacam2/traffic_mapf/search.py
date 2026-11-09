"""
search.py
对应 C++ traffic_mapf/search.hpp + search.cpp

提供：
  a_star_of()           : 流量感知 A*（FOCAL_SEARCH=2 模式）
                          对应 C++ aStarOF()
  single_shortest_path(): 贪心最短路（用于快速初始化）
                          对应 C++ singleShortestPath()

论文配置（硬编码）：
  FOCAL_SEARCH=2, OBJECTIVE=O_VC
"""

from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING

from .types import (
    Int4, OBJ, OBJECTIVE, FOCAL_SEARCH, MAX_TIMESTEP,
)
from .utils import get_d, get_neighbor_locs, manhattan_distance
from .search_node import SNode, MemoryPool, re_of, re_f, re_jam, cmp_less_f, cmp_less_jam
from .heap import PQueueMinOF, PQueueMinJam, PQueueMinF
from .heuristics import get_heuristic, init_heuristic

if TYPE_CHECKING:
    from .types import SharedEnvironment, HeuristicTable


# ===========================================================================
# FOCAL_SEARCH 辅助：将 OPEN 中 f <= f_bound 的节点迁移至 FOCAL
# ===========================================================================

def _update_focal(
    open_q: "PQueue",
    focal: "PQueue",
    f_min: int,
    f_bound: int,
) -> None:
    """
    对应 C++ void update_focal(pqueue_min_f& open, pqueue_min_jam& focal, ...)
    将 open 队列顶部 f <= f_bound 的节点全部移入 focal
    """
    if open_q.empty():
        return
    while not open_q.empty() and open_q.top().get_f() <= f_bound:
        focal.push(open_q.pop())


# ===========================================================================
# a_star_of（论文 Algorithm 2 / FindPaths 中的单智能体搜索）
# ===========================================================================

def a_star_of(
    env: "SharedEnvironment",
    flow: List[Int4],
    ht: "HeuristicTable",
    traffic: List[int],
    traj: List[int],
    mem: MemoryPool,
    start: int,
    goal: int,
) -> SNode:
    """
    对应 C++ s_node aStarOF(...)

    流量感知 A*，实现论文 F2 配置：
      - FOCAL_SEARCH=2：使用两个队列（OPEN 按 f 排序，FOCAL 按 (op_flow, vertex_flow+f, -g) 排序）
      - OBJECTIVE=O_VC：op_flow = Σ (flow[curr→next]+1) * flow[next→curr]（对向流代价）
                        all_vertex_flow = Σ (total_vertex_flow-1)/2（顶点拥堵，仅 FOCAL 模式）
      - traffic[next] != -1 时跳过特定方向的邻居（单向道约束）

    参数：
      env     : SharedEnvironment
      flow    : Int4 列表（全局流量表）
      ht      : 目标 goal 对应的 HeuristicTable（若 empty() 则用 Manhattan 距离）
      traffic : 单向道约束（-1 = 无约束）
      traj    : 输出轨迹（按位置序列）
      mem     : 内存池（调用前无需 reset，内部自动 reset）
      start   : 起始 location
      goal    : 目标 location

    返回：goal 节点的 s_node（含 g, op_flow, all_vertex_flow, depth 等代价信息）
    """
    mem.reset()

    # 起点启发式
    if ht.empty():
        h = manhattan_distance(start, goal, env)
    else:
        h = get_heuristic(ht, env, traffic, flow, start)

    root = mem.generate_node(start, 0, h, 0, 0, 0)

    # 特殊情况：已在目标
    if start == goal:
        traj.clear()
        traj.append(start)
        return SNode(start, 0, 0, 0, 1)

    # FOCAL_SEARCH=2 分支
    f_min = h
    f_bound = f_min * FOCAL_SEARCH
    open_q = PQueueMinF()    # 按 f 排序
    focal = PQueueMinJam()   # 按 (op_flow, vertex_flow+f) 排序

    open_q.push(root)

    goal_node: Optional[SNode] = None
    neighbors = [0, 0, 0, 0]

    while open_q.size() + focal.size() > 0:
        _update_focal(open_q, focal, f_min, f_bound)
        curr = focal.pop()
        if curr is None:
            break
        curr.close()

        # 目标检查
        if curr.id == goal:
            goal_node = curr
            break

        get_neighbor_locs(env, neighbors, curr.id)

        for ni in range(4):
            next_loc = neighbors[ni]
            if next_loc == -1:
                continue

            cost = curr.g + 1
            tie_breaker = curr.tie_breaker

            # 单向道约束：traffic[next] != -1 表示 next 只允许从某方向进入
            if traffic[next_loc] != -1:
                candidates = [
                    next_loc + 1,
                    next_loc + env.cols,
                    next_loc - 1,
                    next_loc - env.cols,
                ]
                if curr.id == candidates[traffic[next_loc]]:
                    continue  # 跳过：当前节点是被禁止进入 next 的来源

            depth = curr.depth + 1

            # 计算移动方向
            diff = next_loc - curr.id
            d = get_d(diff, env)

            # 对向流代价：(flow[curr→d] + 1) * flow[next→(d+2)%4]
            # 对应论文中的 c_e = f(v1→v2) × f(v2→v1)（进入 next 时 curr 方向增 1）
            op_flow_inc = (flow[curr.id].d[d] + 1) * flow[next_loc].d[(d + 2) % 4]

            # 顶点流代价：进入 next 时的总流量（含本次）
            temp_vertex = 1 + sum(flow[next_loc].d)

            # 累积对向流
            new_op_flow = curr.op_flow
            new_all_vertex_flow = curr.all_vertex_flow

            if OBJECTIVE == OBJ.O_VC:
                new_op_flow += op_flow_inc

            # FOCAL 模式：vertex_flow 单独累积到 all_vertex_flow
            if OBJECTIVE in (OBJ.O_VC, OBJ.VC):
                new_all_vertex_flow += (temp_vertex - 1) // 2
            elif OBJECTIVE == OBJ.SUM_OVC:
                new_all_vertex_flow += (temp_vertex - 1) // 2 + op_flow_inc

            # 启发式
            if ht.empty():
                h_next = manhattan_distance(next_loc, goal, env)
            else:
                h_next = get_heuristic(ht, env, traffic, flow, next_loc)

            temp = SNode(next_loc, cost, h_next, new_op_flow, depth, new_all_vertex_flow)
            temp.tie_breaker = tie_breaker

            if not mem.has_node(next_loc):
                next_node = mem.generate_node(
                    next_loc, cost, h_next, new_op_flow, depth, new_all_vertex_flow
                )
                next_node.parent = curr
                next_node.tie_breaker = tie_breaker
                # 根据 f 决定放入 open 还是 focal
                if next_node.get_f() <= f_bound:
                    focal.push(next_node)
                else:
                    open_q.push(next_node)
            else:
                existing = mem.get_node(next_loc)
                if not existing.is_closed():
                    if existing.get_f() <= f_bound:
                        # 在 focal 中
                        if re_jam(temp, existing):
                            existing.g = cost
                            existing.parent = curr
                            existing.depth = depth
                            existing.tie_breaker = tie_breaker
                            existing.set_all_flow(new_op_flow, new_all_vertex_flow)
                            focal.decrease_key(existing)
                    else:
                        # 在 open 中
                        if re_f(temp, existing):
                            existing.g = cost
                            existing.parent = curr
                            existing.depth = depth
                            existing.tie_breaker = tie_breaker
                            existing.set_all_flow(new_op_flow, new_all_vertex_flow)
                            open_q.decrease_key(existing)
                # 已关闭节点：FOCAL 模式下不重展开（对应 C++ 注释掉的重展开代码）

    assert goal_node is not None, \
        f"a_star_of: no path found from {start} to {goal}"

    # 回溯轨迹
    traj.clear()
    traj_len = goal_node.depth
    traj.extend([0] * traj_len)
    curr = goal_node
    for idx in range(traj_len - 1, -1, -1):
        traj[idx] = curr.id
        curr = curr.parent

    # 返回 goal 节点的副本（含代价信息）
    result = SNode(
        goal_node.id,
        goal_node.g,
        goal_node.h,
        goal_node.op_flow,
        goal_node.depth,
        goal_node.all_vertex_flow,
    )
    return result


# ===========================================================================
# single_shortest_path（贪心最短路，用于 init_traj_st）
# ===========================================================================

def single_shortest_path(
    env: "SharedEnvironment",
    flow: List[Int4],
    ht: "HeuristicTable",
    traffic: List[int],
    traj: List[int],
    mem: MemoryPool,
    start: int,
    goal: int,
) -> SNode:
    """
    对应 C++ s_node singleShortestPath(...)
    贪心算法：每步选择 h 值最小的邻居，不考虑流量代价。
    用于 INIT_PP=OFF 时的初始轨迹生成（init_traj_st）。
    """
    traj.clear()
    traj.append(start)
    neighbors = [0, 0, 0, 0]

    while traj[-1] != goal:
        curr = traj[-1]
        get_neighbor_locs(env, neighbors, curr)
        min_h = MAX_TIMESTEP
        next_loc = -1
        for i in range(4):
            nb = neighbors[i]
            if nb == -1:
                continue
            assert not ht.empty(), "single_shortest_path: heuristic table is empty"
            h = get_heuristic(ht, env, traffic, flow, nb)
            if h < min_h:
                min_h = h
                next_loc = nb
        assert next_loc != -1, \
            f"single_shortest_path: stuck at {curr}, no neighbor leads to goal {goal}"
        traj.append(next_loc)

    result = SNode(goal, len(traj), 0, 0, len(traj))
    return result
