"""
flow.py
对应 C++ traffic_mapf/flow.hpp + flow.cpp

提供：
  get_op_flow()      : 计算两个位置之间的对向流代价
  get_vertex_flow()  : 计算位置的顶点流代价
  add_traj()         : 将轨迹加入流量统计
  remove_traj()      : 从流量统计中移除轨迹
  init_traj()        : 用 aStarOF 初始化所有智能体轨迹（INIT_PP=ON）
  init_traj_st()     : 用 singleShortestPath 初始化（INIT_PP=OFF）
  init_dist_table()  : 为每个轨迹初始化 Dist2Path 距离表
  destroy_improve()  : LNS 主循环（PathRefinement）
"""

from __future__ import annotations
import random as _random
from typing import List, Set, TYPE_CHECKING

from .types import OBJ, OBJECTIVE, MAX_TIMESTEP, ADAPTIVE
from .utils import get_d
from .search_node import SNode
from .search import a_star_of, single_shortest_path
from .heuristics import init_dist_2_path, get_heuristic, init_heuristic

if TYPE_CHECKING:
    from .traj_lns import TrajLNS

# 全局随机生成器（对应 C++ std::mt19937 g(0)）
_rng = _random.Random(0)


# ===========================================================================
# 流量代价辅助函数
# ===========================================================================

def get_op_flow(lns: "TrajLNS", prev_loc: int, loc: int, d: int) -> int:
    """
    对应 C++ int get_op_flow(TrajLNS& lns, int prev_loc, int loc, int d)
    对向流代价 = flow[prev_loc→d] * flow[loc→(d+2)%4]
    """
    return lns.flow[prev_loc].d[d] * lns.flow[loc].d[(d + 2) % 4]


def get_vertex_flow(lns: "TrajLNS", loc: int) -> int:
    """
    对应 C++ int get_vertex_flow(TrajLNS& lns, int loc)
    顶点流代价 = (total_incoming_flow - 1) / 2，其中 total = Σ flow[loc].d[k]
    """
    total = sum(lns.flow[loc].d)
    return (total - 1) // 2


def get_all_op_flow(lns: "TrajLNS") -> int:
    """
    对应 C++ int get_all_op_flow(TrajLNS& lns)
    计算全局对向流总和（仅用于断言检查）
    """
    op_flow = 0
    for row in range(lns.env.rows):
        for col in range(lns.env.cols):
            loc = row * lns.env.cols + col
            right_loc = loc + 1
            bottom_loc = loc + lns.env.cols

            if col != lns.env.cols - 1:
                op_flow += lns.flow[loc].d[0] * lns.flow[right_loc].d[2]
            if row != lns.env.rows - 1:
                op_flow += lns.flow[loc].d[1] * lns.flow[bottom_loc].d[3]
    return op_flow


# ===========================================================================
# add_traj / remove_traj
# ===========================================================================

def remove_traj(lns: "TrajLNS", agent: int) -> None:
    """
    对应 C++ void remove_traj(TrajLNS& lns, int agent)
    从流量统计中移除 agent 的轨迹，并更新 op_flow / vertex_flow / soc
    """
    traj = lns.trajs[agent]
    if not traj:
        return

    lns.occupations[traj[0]].discard(agent)
    lns.soc -= len(traj) - 1

    if len(traj) <= 1:
        return

    for j in range(1, len(traj)):
        loc = traj[j]
        prev_loc = traj[j - 1]
        diff = loc - prev_loc
        d = get_d(diff, lns.env)

        lns.occupations[loc].discard(agent)

        old_op_flow = get_op_flow(lns, prev_loc, loc, d)
        old_vertex_flow = get_vertex_flow(lns, prev_loc)

        # 更新流量
        lns.flow[prev_loc].d[d] -= 1

        new_op_flow = get_op_flow(lns, prev_loc, loc, d)
        new_vertex_flow = get_vertex_flow(lns, prev_loc)

        lns.op_flow += new_op_flow - old_op_flow
        lns.vertex_flow += new_vertex_flow - old_vertex_flow

        assert lns.flow[prev_loc].d[d] >= 0, \
            f"remove_traj: negative flow at loc={prev_loc}, d={d}"
        assert lns.op_flow >= 0, f"remove_traj: negative op_flow"
        assert lns.vertex_flow >= 0, f"remove_traj: negative vertex_flow"


def add_traj(lns: "TrajLNS", agent: int) -> None:
    """
    对应 C++ void add_traj(TrajLNS& lns, int agent)
    将 agent 的轨迹加入流量统计，更新 op_flow / vertex_flow / soc / occupations
    """
    traj = lns.trajs[agent]
    if not traj:
        return

    lns.occupations[traj[0]].add(agent)
    lns.soc += len(traj) - 1

    if len(traj) <= 1:
        return

    for j in range(1, len(traj)):
        loc = traj[j]
        prev_loc = traj[j - 1]
        diff = loc - prev_loc
        d = get_d(diff, lns.env)

        lns.occupations[loc].add(agent)

        old_op_flow = get_op_flow(lns, prev_loc, loc, d)
        old_vertex_flow = get_vertex_flow(lns, prev_loc)

        # 更新流量
        lns.flow[prev_loc].d[d] += 1

        new_op_flow = get_op_flow(lns, prev_loc, loc, d)
        new_vertex_flow = get_vertex_flow(lns, prev_loc)

        lns.op_flow += new_op_flow - old_op_flow
        lns.vertex_flow += new_vertex_flow - old_vertex_flow

        assert lns.op_flow >= 0, f"add_traj: negative op_flow"
        assert lns.vertex_flow >= 0, f"add_traj: negative vertex_flow"


# ===========================================================================
# init_traj（INIT_PP=ON，使用 aStarOF 逐智能体规划）
# ===========================================================================

def init_traj(
    lns: "TrajLNS",
    traffic: List[int],
    amount: int,
    remove_and_plan: bool = False,
) -> None:
    """
    对应 C++ void init_traj(TrajLNS& lns, vector<int>& traffic, int amount, bool remove_and_plan)
    使用 aStarOF 为每个智能体（或前 amount 个）顺序规划轨迹。
    流量在每条轨迹加入后立即更新（Algorithm 2 FindPaths 的逻辑）。

    INIT_PP=ON：remove_and_plan=False（首次规划）
    再规划时：remove_and_plan=True
    """
    count = 0
    for i in range(lns.env.num_of_agents):
        if lns.is_time_up():
            break
        if count >= amount:
            break
        if remove_and_plan and lns.trajs[i]:
            remove_traj(lns, i)
        if not lns.trajs[i] or remove_and_plan:
            start = lns.env.curr_states[i].location
            goal = lns.tasks[i]
            goal_ht = lns.heuristics[goal]
            traj_new: List[int] = []
            lns.goal_nodes[i] = a_star_of(
                lns.env, lns.flow, goal_ht, traffic,
                traj_new, lns.mem, start, goal
            )
            lns.trajs[i] = traj_new
            add_traj(lns, i)
            count += 1
            lns.traj_inited += 1

    # print(f"---init-agents:{count}")


def init_traj_st(
    lns: "TrajLNS",
    traffic: List[int],
) -> None:
    """
    对应 C++ void init_traj_st(TrajLNS& lns, vector<int>& traffic)
    使用 singleShortestPath（贪心）为所有空轨迹初始化，
    然后批量 add_traj（先规划全部，再统一加入流量）。
    用于 INIT_PP=OFF 分支。
    """
    for i in range(lns.env.num_of_agents):
        if not lns.trajs[i]:
            start = lns.env.curr_states[i].location
            goal = lns.tasks[i]
            goal_ht = lns.heuristics[goal]
            traj_new: List[int] = []
            lns.goal_nodes[i] = single_shortest_path(
                lns.env, lns.flow, goal_ht, traffic,
                traj_new, lns.mem, start, goal
            )
            lns.trajs[i] = traj_new
            lns.traj_inited += 1

    for i in range(lns.env.num_of_agents):
        if lns.trajs[i]:
            add_traj(lns, i)


# ===========================================================================
# init_dist_table（为每条轨迹初始化 Dist2Path）
# ===========================================================================

def init_dist_table(
    lns: "TrajLNS",
    traffic: List[int],
    amount: int,
) -> None:
    """
    对应 C++ void init_dist_table(TrajLNS& lns, ..., int amount)
    为尚未初始化 dist2path 的智能体（且轨迹非最短路）建立 Dist2Path 表。
    跳过轨迹已经是最短路（len == h(start)）的智能体。
    """
    count = 0
    for i in range(lns.env.num_of_agents):
        if count >= amount:
            break
        traj = lns.trajs[i]
        if not traj:
            continue
        # 如果轨迹已经是最短路，跳过（引导路径等于最短路，引导意义不大）
        goal_ht = lns.heuristics[traj[-1]]
        h_start = get_heuristic(goal_ht, lns.env, traffic, lns.flow, traj[0])
        if len(traj) == h_start:
            continue
        if not lns.traj_dists[i].empty():
            continue
        init_dist_2_path(lns.traj_dists[i], lns.env, traj, traffic)
        count += 1
        lns.dist2path_inited += 1


# ===========================================================================
# update_traj（重新规划单个智能体）
# ===========================================================================

def update_traj(
    lns: "TrajLNS",
    i: int,
    traffic: List[int],
) -> None:
    """
    对应 C++ void update_traj(TrajLNS& lns, int i, vector<int>& traffic)
    用 aStarOF 重新规划智能体 i 的轨迹，并加入流量统计。
    注意：调用前需先 remove_traj(lns, i)
    """
    start = lns.env.curr_states[i].location
    goal = lns.tasks[i]
    goal_ht = lns.heuristics[goal]
    traj_new: List[int] = []
    lns.goal_nodes[i] = a_star_of(
        lns.env, lns.flow, goal_ht, traffic,
        traj_new, lns.mem, start, goal
    )
    lns.trajs[i] = traj_new
    add_traj(lns, i)


# ===========================================================================
# LNS 终止条件
# ===========================================================================

def _terminate(
    lns: "TrajLNS",
    max_ite: int,
    time_limit: float,
    ite: int,
    start_time_perf: float,
    stop: bool,
) -> bool:
    """
    对应 C++ bool terminate(TrajLNS&, int max_ite, double time_limit, int ite, ...)
    time_limit 单位：秒
    """
    if ite >= max_ite:
        return True
    import time
    elapsed_s = time.perf_counter() - start_time_perf
    if elapsed_s >= time_limit:
        return True
    if stop:
        return True
    return False


# ===========================================================================
# LNS 邻域选择方法
# ===========================================================================

def _random_select(lns: "TrajLNS", agents: List[int]) -> None:
    """
    对应 C++ void random_select(TrajLNS& lns, vector<int>& agents)
    随机选取 group_size 个不重复的智能体索引
    """
    N = lns.env.num_of_agents
    if lns.group_size >= N:
        for i in range(N):
            agents[i] = i
        return
    i = 0
    while i < lns.group_size:
        idx = _rng.randint(0, N - 1)
        if idx not in agents[:i]:
            agents[i] = idx
            i += 1


def _select_most_expensive(lns: "TrajLNS", agents: List[int]) -> None:
    """
    对应 C++ void select_most_expensive(TrajLNS& lns, vector<int>& agents)
    选择：
      1. 对向流代价最高的智能体（seed agent）
      2. 在 seed 路径中最拥挤位置上的邻居智能体
      3. 随机填满 group_size

    使用 tabu_list 避免重复选择同一智能体（tabu 超过半数时重置）
    """
    N = lns.env.num_of_agents
    if lns.num_in_tablu >= N // 2:
        lns.tabu_list = [False] * N
        lns.num_in_tablu = 0

    most_op_flow_i = -1
    most_cost_i = -1
    most_op_flow_val = 0
    most_cost_val = 0

    for i in range(N):
        if lns.tabu_list[i]:
            continue
        if lns.goal_nodes[i].get_op_flow() > most_op_flow_val:
            most_op_flow_val = lns.goal_nodes[i].get_op_flow()
            most_op_flow_i = i
        if lns.goal_nodes[i].get_g() > most_cost_val:
            most_cost_val = lns.goal_nodes[i].get_g()
            most_cost_i = i

    agent = most_op_flow_i if most_op_flow_i != -1 else most_cost_i

    congest_agents: List[int] = []

    if agent != -1:
        agents[0] = agent
        lns.tabu_list[agent] = True
        lns.num_in_tablu += 1

        path = lns.trajs[agent]
        most_congested_loc = -1
        most_congested_occ = 0
        for loc in path:
            if len(lns.occupations[loc]) > most_congested_occ:
                most_congested_occ = len(lns.occupations[loc])
                most_congested_loc = loc

        if most_congested_loc != -1:
            congest_agents = list(lns.occupations[most_congested_loc])

    idx_i = 1
    idx_j = 0
    while idx_i < lns.group_size:
        if idx_j < len(congest_agents):
            ca = congest_agents[idx_j]
            if lns.tabu_list[ca] or ca == agents[0]:
                idx_j += 1
                continue
            agents[idx_i] = ca
            lns.tabu_list[ca] = True
            lns.num_in_tablu += 1
            idx_i += 1
            idx_j += 1
            continue
        else:
            break

    while idx_i < lns.group_size:
        idx = _rng.randint(0, N - 1)
        if idx not in agents[:idx_i]:
            agents[idx_i] = idx
            lns.tabu_list[idx] = True
            lns.num_in_tablu += 1
            idx_i += 1


def _select_method(lns: "TrajLNS") -> int:
    """
    对应 C++ int select_method(TrajLNS& lns)
    按权重随机选择 LNS 方法（RANDOM 或 CONGESTION）
    """
    total = sum(lns.weights)
    r = _rng.random()
    threshold = lns.weights[0]
    method = 0
    while threshold < r * total:
        method += 1
        threshold += lns.weights[method]
    return method


# ===========================================================================
# destroy_improve（LNS 主循环）
# ===========================================================================

def destroy_improve(
    lns: "TrajLNS",
    traffic: List[int],
    updated: Set[int],
    max_ite: int,
    time_limit: float,
) -> None:
    """
    对应 C++ void destory_improve(TrajLNS& lns, ..., int max_ite, double time_limit)

    LNS PathRefinement 主循环（论文 Algorithm 2 PathRefinement 部分）：
      1. 自适应选择方法（RANDOM 或 CONGESTION）
      2. 选择 group_size 个智能体作为"邻域"
      3. 移除它们的轨迹
      4. 用 aStarOF 重新规划
      5. 若新方案更优则保留，否则回滚
      6. 更新自适应权重

    终止条件：迭代次数 >= max_ite，或 时间 >= time_limit 秒，或全局时间预算 lns.t_ms 到期

    OBJECTIVE=O_VC 的接受准则（对应 C++ 代码）：
      若 op_flow 增大，或（op_flow 不变但 vertex_flow+soc 增大），则回滚
    """
    import time as _time

    ite = 0
    start_time = _time.perf_counter()
    neighbors = [-1] * lns.group_size

    while not _terminate(lns, max_ite, time_limit, ite, start_time, False):
        # 检查全局时间预算
        if lns.is_time_up():
            break

        # 重置邻域数组
        for k in range(lns.group_size):
            neighbors[k] = -1

        # 选择方法（自适应）
        method = _select_method(lns)

        if method == int(ADAPTIVE.RANDOM):
            _random_select(lns, neighbors)
        elif method == int(ADAPTIVE.CONGESTION):
            _select_most_expensive(lns, neighbors)
        else:
            raise ValueError(f"Unknown LNS method: {method}")

        # 随机打乱邻域顺序（对应 C++ std::shuffle）
        valid = [n for n in neighbors if n != -1]
        _rng.shuffle(valid)
        for k in range(len(valid)):
            neighbors[k] = valid[k]

        # 保存当前状态
        old_op_flow = lns.op_flow
        old_vertex_flow = lns.vertex_flow
        old_soc = lns.soc

        traj_copy = []
        goal_nodes_copy = []
        for k in range(lns.group_size):
            agent = neighbors[k]
            if agent == -1:
                break
            traj_copy.append(list(lns.trajs[agent]))
            goal_nodes_copy.append(lns.goal_nodes[agent])
            remove_traj(lns, agent)

        # 重新规划
        for k in range(lns.group_size):
            agent = neighbors[k]
            if agent == -1:
                break
            update_traj(lns, agent, traffic)

        # 接受/回滚判断（O_VC 准则）
        if OBJECTIVE == int(OBJ.O_VC):
            reject = (
                lns.op_flow > old_op_flow
                or (lns.op_flow == old_op_flow
                    and lns.vertex_flow + lns.soc > old_vertex_flow + old_soc)
            )
        elif OBJECTIVE == int(OBJ.VC):
            reject = lns.vertex_flow + lns.soc > old_vertex_flow + old_soc
        elif OBJECTIVE == int(OBJ.SUM_OVC):
            reject = (lns.op_flow + lns.vertex_flow + lns.soc
                      > old_op_flow + old_vertex_flow + old_soc)
        else:
            reject = False

        if reject:
            # 回滚
            for k in range(lns.group_size):
                agent = neighbors[k]
                if agent == -1:
                    break
                remove_traj(lns, agent)
                lns.trajs[agent] = traj_copy[k]
                lns.goal_nodes[agent] = goal_nodes_copy[k]
                add_traj(lns, agent)

            lns.weights[method] = (1 - lns.decay_factor) * lns.weights[method]
            adopt_new = False
        else:
            # 接受新方案
            for k in range(lns.group_size):
                agent = neighbors[k]
                if agent == -1:
                    break
                updated.add(agent)

            improvement = max(old_op_flow - lns.op_flow, 0)
            if lns.vertex_flow + lns.soc < old_vertex_flow + old_soc:
                improvement += (old_vertex_flow + old_soc
                                - lns.vertex_flow - lns.soc)

            lns.weights[method] = (
                lns.reaction_factor * improvement / lns.group_size
                + (1 - lns.reaction_factor) * lns.weights[method]
            )
            adopt_new = True

        ite += 1
