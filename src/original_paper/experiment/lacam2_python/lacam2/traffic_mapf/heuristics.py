"""
heuristics.py
对应 C++ traffic_mapf/heuristics.hpp + heuristics.cpp

提供：
  init_heuristic()      : 初始化懒惰 BFS 距离表（以 goal 为起点）
  get_heuristic()       : 懒惰 BFS 查询 source 到 goal 的最短距离
  init_dist_2_path()    : 初始化 Dist2Path（从路径各点反向 BFS）
  get_dist_2_path()     : 懒惰查询 source 到引导路径的距离 + 沿路径剩余距离
  init_flow_heuristic() : 初始化流量感知启发式（从 goal 反向 Dijkstra）
  get_flow_heuristic()  : 懒惰查询 source 的流量感知节点
"""

from __future__ import annotations
from collections import deque
from typing import List, Optional, TYPE_CHECKING

from .types import (
    HeuristicTable, HHNode, Dist2Path, D2P,
    Int4, MAX_TIMESTEP,
)
from .utils import get_neighbor_locs, get_neighbor_locs_list, get_d
from .search_node import SNode, MemoryPool, re_of
from .heap import PQueueMinOF

if TYPE_CHECKING:
    from .types import SharedEnvironment
    from .traj_lns import TrajLNS, FlowHeuristic


# ===========================================================================
# init_heuristic / get_heuristic
# ===========================================================================

def init_heuristic(
    ht: HeuristicTable,
    env: "SharedEnvironment",
    goal_location: int,
) -> None:
    """
    对应 C++ void init_heuristic(HeuristicTable& ht, SharedEnvironment*, int)
    初始化从 goal_location 反向 BFS 的距离表：
      ht.htable[goal] = 0，其余 = MAX_TIMESTEP
      ht.open = deque([HHNode(goal, 0, 0)])
    """
    M = len(env.map)
    ht.htable = [MAX_TIMESTEP] * M
    ht.open = deque()
    root = HHNode(goal_location, 0, 0)
    ht.htable[goal_location] = 0
    ht.open.append(root)


def get_heuristic(
    ht: HeuristicTable,
    env: "SharedEnvironment",
    traffic: List[int],
    flow: List[Int4],
    source: int,
) -> int:
    """
    对应 C++ int get_heuristic(HeuristicTable&, SharedEnvironment*, ..., int source)
    懒惰 BFS：若 ht.htable[source] 已知则直接返回；
    否则继续从 ht.open 展开 BFS 直到覆盖 source 为止。

    注意：这是纯最短路（不考虑流量），用作 A* 的 admissible heuristic。
    """
    if ht.htable[source] < MAX_TIMESTEP:
        return ht.htable[source]

    neighbors = [0, 0, 0, 0]

    while ht.open:
        curr = ht.open.popleft()
        get_neighbor_locs(env, neighbors, curr.location)

        for next_loc in neighbors:
            if next_loc == -1:
                continue
            cost = curr.value + 1
            if cost >= ht.htable[next_loc]:
                continue
            ht.open.append(HHNode(next_loc, 0, cost))
            ht.htable[next_loc] = cost

        if source == curr.location:
            return curr.value

    return MAX_TIMESTEP


# ===========================================================================
# init_dist_2_path / get_dist_2_path
# ===========================================================================

def init_dist_2_path(
    dp: Dist2Path,
    env: "SharedEnvironment",
    path: List[int],
    traffic: List[int],
) -> None:
    """
    对应 C++ void init_dist_2_path(Dist2Path&, SharedEnvironment*, Traj&, ...)
    初始化引导路径距离表：
      从路径末尾（靠近 goal）向前遍历，togo[i] = i 到 goal 的路径步数
      path 上的每个点加入 dp.open（作为 BFS 起点），dist=0
      label++ 实现 O(1) 重置
    """
    M = len(env.map)
    if not dp.dist2path:
        dp.dist2path = [D2P() for _ in range(M)]

    dp.open.clear()
    dp.label += 1

    togo = 0
    # 从路径末尾往前，togo 表示"沿路径还需走多少步到达 goal"
    for i in range(len(path) - 1, -1, -1):
        p = path[i]
        assert (dp.dist2path[p].label != dp.label
                or dp.dist2path[p].cost == MAX_TIMESTEP), \
            f"init_dist_2_path: path has duplicate location {p}"
        entry = D2P(label=dp.label, id=p, cost=0, togo=togo)
        dp.open.append(entry)
        dp.dist2path[p] = entry
        togo += 1


def get_dist_2_path(
    dp: Dist2Path,
    env: "SharedEnvironment",
    traffic: List[int],
    source: int,
) -> int:
    """
    对应 C++ int get_dist_2_path(Dist2Path&, SharedEnvironment*, ..., int source)
    懒惰查询 source 到引导路径的启发式值：
      返回 cost + togo = (dist_to_path) + (steps_along_path_to_goal)
    这就是论文中的 h_i(v) = (d_p, d_g) 的组合值：d_p + d_g
    """
    entry = dp.dist2path[source]
    if entry.label == dp.label and entry.cost < MAX_TIMESTEP:
        return entry.cost + entry.togo

    neighbors = [0, 0, 0, 0]

    while dp.open:
        curr = dp.open.popleft()

        get_neighbor_locs(env, neighbors, curr.id)

        for next_loc in neighbors:
            if next_loc == -1:
                continue
            cost = curr.cost + 1

            existing = dp.dist2path[next_loc]
            if existing.label == dp.label and cost >= existing.cost:
                continue

            next_entry = D2P(label=dp.label, id=next_loc, cost=cost, togo=curr.togo)
            dp.open.append(next_entry)
            dp.dist2path[next_loc] = next_entry

        if source == curr.id:
            return curr.cost + curr.togo

    return MAX_TIMESTEP


# ===========================================================================
# init_flow_heuristic / get_flow_heuristic
# ===========================================================================

def get_flow_heuristic(
    ht: "FlowHeuristic",
    env: "SharedEnvironment",
    traffic: List[int],
    flow: List[Int4],
    source: int,
) -> Optional[SNode]:
    """
    对应 C++ s_node* get_flow_heuristic(FlowHeuristic&, ..., int source)

    从 ht.open（以 goal 为根的反向 Dijkstra）继续展开，直到关闭 source。
    使用 re_of 比较器（先比 op_flow，再比 f）。
    代价 = g + (vertex_flow-1)/2（顶点拥堵惩罚）
    注意：这里是从 goal 往外搜（反向），所以"当前→下一"的方向是
          从 next 到 curr（即 reverse_d = get_d(curr.id - next, env)），
          对应 C++ 中的 reverse_d = get_d(diff, env) where diff = curr->id - next
    """
    if ht.mem.has_node(source) and ht.mem.is_closed(source):
        return ht.mem.get_node(source)

    neighbors = [0, 0, 0, 0]

    while ht.open.size() > 0:
        curr = ht.open.pop()
        curr.close()

        get_neighbor_locs(env, neighbors, curr.id)

        for next_loc in neighbors:
            if next_loc == -1:
                continue

            cost = curr.g + 1
            diff = curr.id - next_loc  # 反向：从 next 到 curr 的方向
            # reverse_d = 从 next_loc 移动到 curr.id 的方向
            reverse_d = get_d(diff, env)

            # op_flow = 0（反向搜索不直接计算对向流）
            op_flow = 0

            # vertex_flow = 流经 curr.id 的总入流（所有四方向流量和）
            vertex_flow = sum(flow[curr.id].d)
            cost += (vertex_flow - 1) // 2

            h = get_heuristic(ht.h, env, traffic, flow, next_loc)
            depth = curr.depth + 1

            temp = SNode(next_loc, cost, h, op_flow, depth)

            if not ht.mem.has_node(next_loc):
                next_node = ht.mem.generate_node(next_loc, cost, h, op_flow, depth)
                next_node.parent = curr
                ht.open.push(next_node)
            else:
                existing = ht.mem.get_node(next_loc)
                if not existing.is_closed():
                    if re_of(temp, existing):
                        existing.g = cost
                        existing.parent = curr
                        existing.depth = depth
                        existing.op_flow = op_flow
                        ht.open.decrease_key(existing)
                else:
                    # 已关闭节点不应被重新展开（admissible 启发式保证）
                    if re_of(temp, existing):
                        # 这是错误情况（C++ 中 assert(false)），在 Python 中只警告
                        pass

        if source == curr.id:
            return curr

    return None


def init_flow_heuristic(
    lns: "TrajLNS",
    traffic: List[int],
    i: int,
) -> None:
    """
    对应 C++ void init_flow_heuristic(TrajLNS& lns, ..., int i)
    为智能体 i 初始化流量感知启发式。
    以 goal 为搜索起点，start_loc 为目标（反向搜索）。
    最后调用 get_flow_heuristic 将结果展开到 start_loc。
    """
    start_loc = lns.env.curr_states[i].location
    goal_location = lns.tasks[i]
    ht = lns.flow_heuristics[i]

    # ht.h 指向从 start_loc 出发的纯距离启发式表
    ht.h = lns.heuristics[start_loc]
    if ht.h.empty():
        init_heuristic(ht.h, lns.env, start_loc)

    ht.reset()
    if not ht.mem.is_ready():
        ht.mem.init(len(lns.env.map))

    ht.target = goal_location
    ht.origin = start_loc

    h_root = get_heuristic(ht.h, lns.env, traffic, lns.flow, start_loc)
    root = ht.mem.generate_node(goal_location, 0, h_root, 0, 0)
    ht.open.push(root)

    get_flow_heuristic(ht, lns.env, traffic, lns.flow, start_loc)


def init_flow_heuristic_with_goal(
    lns: "TrajLNS",
    traffic: List[int],
    ht: "FlowHeuristic",
    i: int,
    goal_loc: int,
) -> None:
    """
    对应 C++ void init_flow_heuristic(TrajLNS&, ..., FlowHeuristic&, int i, int goal_loc)
    带显式 goal_loc 参数的重载版本
    """
    start_loc = lns.env.curr_states[i].location
    goal_location = goal_loc

    ht.h = lns.heuristics[start_loc]
    if ht.h.empty():
        init_heuristic(ht.h, lns.env, start_loc)

    ht.reset()
    if not ht.mem.is_ready():
        ht.mem.init(len(lns.env.map))

    ht.target = goal_location
    ht.origin = start_loc

    h_root = get_heuristic(ht.h, lns.env, traffic, lns.flow, start_loc)
    root = ht.mem.generate_node(goal_location, 0, h_root, 0, 0)
    ht.open.push(root)

    get_flow_heuristic(ht, lns.env, traffic, lns.flow, start_loc)
