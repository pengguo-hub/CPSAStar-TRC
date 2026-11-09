"""
planner.py
对应 C++ 的 planner.hpp / planner.cpp + lacam2.hpp / lacam2.cpp

包含：
  Objective  : 优化目标枚举
  Agent      : 智能体（当前/下一步位置）
  LNode      : 低层搜索节点（约束列表）
  HNode      : 高层搜索节点（配置节点，C-node）
  Planner    : LaCAM2 主求解器
  solve()    : 对外接口（对应 C++ solve()）

算法结构（严格对应 C++ 逻辑）：
  外层：高层 DFS 搜索配置空间（OPEN 栈 + EXPLORED 哈希表）
  内层：低层展开（expand_lowlevel_tree）+ PIBT 规划（get_new_config / funcPIBT）
  后处理：rewrite（Dijkstra 风格代价更新）+ 回溯提取路径
"""

from __future__ import annotations

import time
import random
from collections import deque
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

from .graph import Vertex, Config, is_same_config, config_hash
from .dist_table import DistTable
from .instance import Instance, Solution


# ======================================================================
# 优化目标
# ======================================================================

class Objective(IntEnum):
    OBJ_NONE        = 0
    OBJ_MAKESPAN    = 1
    OBJ_SUM_OF_LOSS = 2
    OBJ_SUM_OF_COST = 3


# ======================================================================
# Deadline：时间限制管理（对应 C++ struct Deadline + utils.hpp）
# ======================================================================

class Deadline:
    """对应 C++ struct Deadline"""

    def __init__(self, time_limit_ms: float):
        self.t_s = time.perf_counter()
        self.time_limit_ms = time_limit_ms

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.t_s) * 1000.0

    def is_expired(self) -> bool:
        return self.elapsed_ms() > self.time_limit_ms


# ======================================================================
# Agent
# ======================================================================

class Agent:
    """对应 C++ struct Agent"""
    __slots__ = ("id", "v_now", "v_next")

    def __init__(self, aid: int):
        self.id: int = aid
        self.v_now:  Optional[Vertex] = None
        self.v_next: Optional[Vertex] = None


# ======================================================================
# LNode（低层搜索节点）
# ======================================================================

class LNode:
    """
    对应 C++ struct LNode
    记录已确定下一步位置的智能体约束集合：
      who[k]   = 第 k 条约束对应的智能体 id
      where[k] = 该智能体下一步要去的顶点
      depth    = 已约束的智能体数
    """
    __slots__ = ("who", "where", "depth")

    def __init__(
        self,
        parent: Optional["LNode"] = None,
        agent_id: int = 0,
        v: Optional[Vertex] = None,
    ):
        if parent is None:
            self.who:   List[int]    = []
            self.where: List[Vertex] = []
            self.depth: int          = 0
        else:
            self.who   = parent.who   + [agent_id]
            self.where = parent.where + [v]
            self.depth = parent.depth + 1


# ======================================================================
# HNode（高层搜索节点，C-node）
# ======================================================================

_HNODE_CNT = 0  # 全局计数器，对应 C++ HNode::HNODE_CNT


class HNode:
    """
    对应 C++ struct HNode
    表示一个多智能体配置（所有智能体的位置），以及从该配置出发的低层搜索状态。
    """

    def __init__(
        self,
        C: Config,
        D: DistTable,
        parent: Optional["HNode"],
        g: int,
        h: int,
    ):
        global _HNODE_CNT
        _HNODE_CNT += 1

        self.C: Config = C                  # 当前配置（长度 N 的顶点列表）
        self.parent: Optional[HNode] = parent
        self.neighbor: set = set()          # 邻居高层节点集合

        self.g: int = g    # 从起点到此节点的代价
        self.h: int = h    # 启发式值
        self.f: int = g + h

        N = len(C)
        self.priorities: List[float] = [0.0] * N
        self.order:      List[int]   = list(range(N))

        # 低层搜索树（队列，BFS 展开约束）
        self.search_tree: deque = deque()
        self.search_tree.append(LNode())  # 根节点（空约束）

        # 更新邻居
        if parent is not None:
            parent.neighbor.add(self)

        # 设置优先级（对应 C++ HNode 构造函数中的 priorities 初始化）
        if parent is None:
            # 初始节点：优先级 = BFS 距离 / N（距离目标越远优先级越高）
            for i in range(N):
                self.priorities[i] = D.get_v(i, C[i]) / N
        else:
            # 动态优先级（PIBT 风格）
            for i in range(N):
                if D.get_v(i, C[i]) != 0:
                    self.priorities[i] = parent.priorities[i] + 1
                else:
                    # 已到达目标：只保留小数部分
                    self.priorities[i] = parent.priorities[i] - int(parent.priorities[i])

        # 按优先级降序排列智能体顺序
        self.order.sort(key=lambda i: self.priorities[i], reverse=True)


# ======================================================================
# Planner
# ======================================================================

class Planner:
    """
    对应 C++ struct Planner
    实现完整的 LaCAM2 求解逻辑：高层 DFS + 低层 PIBT
    """

    def __init__(
        self,
        ins: Instance,
        deadline: Optional[Deadline],
        rng: Optional[random.Random],
        verbose: int = 0,
        objective: Objective = Objective.OBJ_NONE,
        restart_rate: float = 0.001,
        guid_t_ms: float = 0.0,
        disappear_on_goal: bool = False,
    ):
        self.ins       = ins
        self.deadline  = deadline
        self.rng       = rng
        self.verbose   = verbose
        self.objective = objective
        self.RESTART_RATE = restart_rate

        self.N      = ins.N
        self.V_size = ins.G.size()
        self.D      = DistTable(ins)
        self.loop_cnt = 0
        self.disappear_on_goal = disappear_on_goal

        # GUIDANCE=ON：初始化流量引导系统
        if guid_t_ms > 0:
            self._solver_info(1, "setting up guidance...")
            self.D.setup_guidance(ins, guid_t_ms)
            self._solver_info(1, "guidance setup done")

        # PIBT 用的缓存
        # C_next[i] 存智能体 i 的候选下一步（最多 5 个：4 邻居 + 原地）
        self.C_next:         List[List[Optional[Vertex]]] = [[None] * 5 for _ in range(self.N)]
        self.tie_breakers:   List[float]                  = [0.0] * self.V_size
        self.A:              List[Optional[Agent]]        = [None] * self.N
        self.occupied_now:   List[Optional[Agent]]        = [None] * self.V_size
        self.occupied_next:  List[Optional[Agent]]        = [None] * self.V_size

    # ------------------------------------------------------------------
    # 主求解入口
    # ------------------------------------------------------------------

    def solve(self) -> Tuple[Solution, str]:
        """
        对应 C++ Planner::solve()
        返回 (solution, additional_info)
        solution 为空列表表示失败
        """
        self._solver_info(1, "start search")

        # 初始化智能体
        for i in range(self.N):
            self.A[i] = Agent(i)

        # 初始化搜索
        OPEN: List[HNode] = []  # 模拟 std::stack（用列表末尾作为栈顶）
        # key = 配置的哈希值 -> HNode（注意：可能碰撞，用 (hash, tuple(ids)) 作 key）
        EXPLORED: Dict[Tuple, HNode] = {}

        H_init = HNode(list(self.ins.starts), self.D, None, 0,
                       self._get_h_value(list(self.ins.starts)))
        OPEN.append(H_init)
        EXPLORED[self._config_key(H_init.C)] = H_init

        solution: Solution = []
        C_new: Config = [None] * self.N
        H_goal: Optional[HNode] = None

        # ---- 主 DFS 循环 ----
        while OPEN and not self._is_expired():
            self.loop_cnt += 1

            H = OPEN[-1]  # 栈顶（不 pop）

            # 低层搜索树耗尽
            if not H.search_tree:
                OPEN.pop()
                continue

            # 剪枝：当前节点 f 值已不优于已知解
            if H_goal is not None and H.f >= H_goal.f:
                OPEN.pop()
                continue

            # 检查目标条件
            if H_goal is None and is_same_config(H.C, self.ins.goals):
                H_goal = H
                self._solver_info(1, f"found solution, cost: {H.g}")
                if self.objective == Objective.OBJ_NONE:
                    break
                continue

            # 低层展开 + PIBT
            L = H.search_tree.popleft()
            self._expand_lowlevel_tree(H, L)

            res = self._get_new_config(H, L)
            if not res:
                continue

            # 构造新配置
            for a in self.A:
                C_new[a.id] = a.v_next

            key = self._config_key(C_new)
            if key in EXPLORED:
                # 找到已探索节点，执行 rewrite
                H_existing = EXPLORED[key]
                self._rewrite(H, H_existing, H_goal, OPEN)
                # 随机重启或插入已有节点
                if self.rng is not None and self.rng.random() >= self.RESTART_RATE:
                    H_insert = H_existing
                else:
                    H_insert = H_init
                if H_goal is None or H_insert.f < H_goal.f:
                    OPEN.append(H_insert)
            else:
                # 新节点
                edge_cost = self._get_edge_cost_configs(H, H.C, C_new)
                H_new = HNode(
                    list(C_new), self.D, H,
                    H.g + edge_cost,
                    self._get_h_value(C_new),
                )
                EXPLORED[self._config_key(H_new.C)] = H_new
                if H_goal is None or H_new.f < H_goal.f:
                    OPEN.append(H_new)

        # ---- 回溯提取路径 ----
        if H_goal is not None:
            node = H_goal
            while node is not None:
                solution.append(list(node.C))
                node = node.parent
            solution.reverse()
        elif EXPLORED:
            per_agent_partial: List[Optional[List]] = [None] * self.N
            for node in EXPLORED.values():
                for i in range(self.N):
                    if (node.C[i] is self.ins.goals[i]
                            and (node.parent is None
                                 or node.parent.C[i] is not self.ins.goals[i])):
                        # AGV i 刚到达 goal 的节点，只取第一个找到的
                        if per_agent_partial[i] is None:
                            trace = []
                            cur = node
                            while cur is not None:
                                trace.append(cur.C[i])
                                cur = cur.parent
                            trace.reverse()
                            per_agent_partial[i] = trace

            if any(p is not None for p in per_agent_partial):
                max_steps = max(len(p) for p in per_agent_partial if p is not None)
                for t in range(max_steps):
                    config = []
                    for i in range(self.N):
                        p = per_agent_partial[i]
                        if p is not None:
                            config.append(p[min(t, len(p) - 1)])
                        else:
                            config.append(self.ins.starts[i])
                    solution.append(config)

        # 打印结果
        if H_goal is not None and not OPEN:
            self._solver_info(1, f"solved optimally, objective: {self.objective.name}")
        elif H_goal is not None:
            self._solver_info(1, f"solved sub-optimally, objective: {self.objective.name}")
        elif not OPEN:
            self._solver_info(1, "no solution")
        else:
            self._solver_info(1, "timeout")

        optimal = (H_goal is not None and not OPEN)
        additional_info = (
            f"optimal={int(optimal)}\n"
            f"objective={int(self.objective)}\n"
            f"loop_cnt={self.loop_cnt}\n"
            f"num_node_gen={len(EXPLORED)}\n"
        )

        return solution, additional_info

    # ------------------------------------------------------------------
    # rewrite（Dijkstra 风格代价传播）
    # ------------------------------------------------------------------

    def _rewrite(
        self,
        H_from: HNode,
        H_to: HNode,
        H_goal: Optional[HNode],
        OPEN: List[HNode],
    ) -> None:
        """对应 C++ Planner::rewrite()"""
        H_from.neighbor.add(H_to)

        Q: deque = deque([H_from])
        while Q:
            n_from = Q.popleft()
            for n_to in n_from.neighbor:
                g_val = n_from.g + self._get_edge_cost_nodes(n_from, n_to)
                if g_val < n_to.g:
                    if n_to is H_goal:
                        self._solver_info(1, f"cost update: {n_to.g} -> {g_val}")
                    n_to.g = g_val
                    n_to.f = n_to.g + n_to.h
                    n_to.parent = n_from
                    Q.append(n_to)
                    if H_goal is not None and n_to.f < H_goal.f:
                        OPEN.append(n_to)

    # ------------------------------------------------------------------
    # 代价函数
    # ------------------------------------------------------------------

    def _get_edge_cost_configs(
        self, H_from: Optional[HNode], C1: Config, C2: Config
    ) -> int:
        """对应 C++ Planner::get_edge_cost(HNode*, Config, Config)"""
        if self.objective == Objective.OBJ_SUM_OF_LOSS:
            cost = 0
            for i in range(self.N):
                if C1[i] is not self.ins.goals[i] or C2[i] is not self.ins.goals[i]:
                    cost += 1
            return cost

        elif self.objective == Objective.OBJ_SUM_OF_COST:
            cost = 0
            for i in range(self.N):
                if C1[i] is not self.ins.goals[i] or C2[i] is not self.ins.goals[i]:
                    cost += 1
                # 惩罚：智能体曾到达目标但又离开（等价 SoC）
                ex_cost = 0
                if (H_from is not None
                        and C1[i] is self.ins.goals[i]
                        and C2[i] is not self.ins.goals[i]):
                    curr = H_from
                    while (curr.parent is not None
                           and curr.parent.C[i] is self.ins.goals[i]):
                        ex_cost += 1
                        curr = curr.parent
                cost += ex_cost
            return cost

        # 默认：makespan（每步代价 = 1）
        return 1

    def _get_edge_cost_nodes(self, H_from: HNode, H_to: HNode) -> int:
        """对应 C++ Planner::get_edge_cost(HNode*, HNode*)"""
        return self._get_edge_cost_configs(H_from, H_from.C, H_to.C)

    def _get_h_value(self, C: Config) -> int:
        """对应 C++ Planner::get_h_value()"""
        cost = 0
        if self.objective == Objective.OBJ_MAKESPAN:
            for i in range(self.N):
                cost = max(cost, self.D.get_v(i, C[i]))
        elif self.objective in (Objective.OBJ_SUM_OF_LOSS, Objective.OBJ_SUM_OF_COST):
            for i in range(self.N):
                cost += self.D.get_v(i, C[i])
        return cost

    # ------------------------------------------------------------------
    # 低层树展开
    # ------------------------------------------------------------------

    def _expand_lowlevel_tree(self, H: HNode, L: LNode) -> None:
        """
        对应 C++ Planner::expand_lowlevel_tree()
        为 H->order[L.depth] 号智能体的所有候选下一步创建新约束节点
        """
        if L.depth >= self.N:
            return
        i = H.order[L.depth]
        # disappear_on_goal=True 时：已消失的 AGV 只有原地一个候选，不展开邻居
        if self.disappear_on_goal and H.C[i] is self.ins.goals[i]:
            H.search_tree.append(LNode(L, i, H.C[i]))
            return
        candidates = list(H.C[i].neighbor) + [H.C[i]]  # 邻居 + 原地等待
        if self.rng is not None:
            self.rng.shuffle(candidates)
        for v in candidates:
            H.search_tree.append(LNode(L, i, v))

    # ------------------------------------------------------------------
    # 获取新配置（调用 PIBT）
    # ------------------------------------------------------------------

    def _get_new_config(self, H: HNode, L: LNode) -> bool:
        """
        对应 C++ Planner::get_new_config()
        先应用 L 中的约束，再对未确定智能体执行 PIBT
        """
        # 清空并重建 occupied 缓存
        for a in self.A:
            if a.v_now is not None and self.occupied_now[a.v_now.id] is a:
                self.occupied_now[a.v_now.id] = None
            if a.v_next is not None:
                self.occupied_next[a.v_next.id] = None
                a.v_next = None
            a.v_now = H.C[a.id]
            if not (self.disappear_on_goal and a.v_now is self.ins.goals[a.id]):
                self.occupied_now[a.v_now.id] = a

        # 应用约束
        for k in range(L.depth):
            i = L.who[k]
            loc = L.where[k].id

            # 顶点冲突检查
            if self.occupied_next[loc] is not None:
                return False
            # 交换冲突检查
            l_pre = H.C[i].id
            if (self.occupied_next[l_pre] is not None
                    and self.occupied_now[loc] is not None
                    and self.occupied_next[l_pre].id == self.occupied_now[loc].id):
                return False

            self.A[i].v_next = L.where[k]
            self.occupied_next[loc] = self.A[i]

        # PIBT 规划
        for k in H.order:
            a = self.A[k]
            if self.disappear_on_goal and a.v_now is self.ins.goals[a.id]:
                if a.v_next is None:
                    a.v_next = a.v_now
                continue
            if a.v_next is None and not self._funcPIBT(a):
                return False
        return True

    # ------------------------------------------------------------------
    # PIBT（优先级继承回退算法）
    # ------------------------------------------------------------------

    def _funcPIBT(self, ai: Agent) -> bool:
        """
        对应 C++ Planner::funcPIBT()
        为智能体 ai 选择下一步位置（优先级继承 + 交换检测）
        """
        i = ai.id
        neighbors = ai.v_now.neighbor
        K = len(neighbors)

        # 填充候选位置
        for k, u in enumerate(neighbors):
            self.C_next[i][k] = u
            if self.rng is not None:
                self.tie_breakers[u.id] = self.rng.random()
        self.C_next[i][K] = ai.v_now  # 原地等待

        # 按引导距离升序排列（距目标越近越优先）
        # 无 GUIDANCE 时使用 D.get_v；有 GUIDANCE 时使用 D.get_g（在此统一）
        cands = self.C_next[i][:K + 1]
        cands.sort(key=lambda v: self.D.get_g(i, v) + self.tie_breakers[v.id])
        self.C_next[i][:K + 1] = cands

        # 检测并执行交换
        swap_agent = self._swap_possible_and_required(ai)
        if swap_agent is not None:
            # 反转候选顺序以允许交换（push 方向翻转）
            self.C_next[i][:K + 1] = list(reversed(self.C_next[i][:K + 1]))

        # 主循环：尝试每个候选位置
        for k in range(K + 1):
            u = self.C_next[i][k]

            # 避免顶点冲突
            if self.occupied_next[u.id] is not None:
                continue

            ak = self.occupied_now[u.id]

            # 避免交换冲突
            if ak is not None and ak.v_next is ai.v_now:
                continue

            # 预订下一步位置
            self.occupied_next[u.id] = ai
            ai.v_next = u

            # 优先级继承：若 u 被占用且未规划，递归调用
            if ak is not None and ak is not ai and ak.v_next is None:
                if not self._funcPIBT(ak):
                    continue

            # 成功：若需要交换则拉动交换智能体
            if (k == 0
                    and swap_agent is not None
                    and swap_agent.v_next is None
                    and self.occupied_next[ai.v_now.id] is None):
                swap_agent.v_next = ai.v_now
                self.occupied_next[ai.v_now.id] = swap_agent

            return True

        # 所有候选均失败：原地等待
        self.occupied_next[ai.v_now.id] = ai
        ai.v_next = ai.v_now
        return False

    # ------------------------------------------------------------------
    # 交换检测
    # ------------------------------------------------------------------

    def _swap_possible_and_required(self, ai: Agent) -> Optional[Agent]:
        """对应 C++ Planner::swap_possible_and_required()"""
        i = ai.id
        # 首选位置就是原地：不需要交换
        if self.C_next[i][0] is ai.v_now:
            return None

        # 情况 a/b：直接交换
        aj = self.occupied_now[self.C_next[i][0].id]
        if (aj is not None
                and aj.v_next is None
                and self._is_swap_required(ai.id, aj.id, ai.v_now, aj.v_now)
                and self._is_swap_possible(aj.v_now, ai.v_now)):
            return aj

        # 情况 c：清空操作
        for u in ai.v_now.neighbor:
            ak = self.occupied_now[u.id]
            if ak is None or self.C_next[i][0] is ak.v_now:
                continue
            if (self._is_swap_required(ak.id, ai.id, ai.v_now, self.C_next[i][0])
                    and self._is_swap_possible(self.C_next[i][0], ai.v_now)):
                return ak

        return None

    def _is_swap_required(
        self,
        pusher: int,
        puller: int,
        v_pusher_origin: Vertex,
        v_puller_origin: Vertex,
    ) -> bool:
        """对应 C++ Planner::is_swap_required()"""
        v_pusher = v_pusher_origin
        v_puller = v_puller_origin
        tmp: Optional[Vertex] = None

        while self.D.get_g(pusher, v_puller) < self.D.get_g(pusher, v_pusher):
            n = len(v_puller.neighbor)
            for u in v_puller.neighbor:
                a = self.occupied_now[u.id]
                if (u is v_pusher
                        or (len(u.neighbor) == 1
                            and a is not None
                            and self.ins.goals[a.id] is u)):
                    n -= 1
                else:
                    tmp = u
            if n >= 2:
                return False
            if n <= 0:
                break
            v_pusher = v_puller
            v_puller = tmp

        return (
            self.D.get_g(puller, v_pusher) < self.D.get_g(puller, v_puller)
            and (
                self.D.get_g(pusher, v_pusher) == 0
                or self.D.get_g(pusher, v_puller) < self.D.get_g(pusher, v_pusher)
            )
        )

    def _is_swap_possible(
        self,
        v_pusher_origin: Vertex,
        v_puller_origin: Vertex,
    ) -> bool:
        """对应 C++ Planner::is_swap_possible()"""
        v_pusher = v_pusher_origin
        v_puller = v_puller_origin
        tmp: Optional[Vertex] = None

        while v_puller is not v_pusher_origin:
            n = len(v_puller.neighbor)
            for u in v_puller.neighbor:
                a = self.occupied_now[u.id]
                if (u is v_pusher
                        or (len(u.neighbor) == 1
                            and a is not None
                            and self.ins.goals[a.id] is u)):
                    n -= 1
                else:
                    tmp = u
            if n >= 2:
                return True
            if n <= 0:
                return False
            v_pusher = v_puller
            v_puller = tmp

        return False

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _config_key(self, C: Config) -> Tuple:
        """用元组作为 dict key，保证无碰撞（比纯哈希更安全）"""
        if not self.disappear_on_goal:
            return tuple(v.id for v in C)
        return tuple(
            -(i + 1) if C[i] is self.ins.goals[i] else C[i].id
            for i in range(self.N)
        )

    def _is_expired(self) -> bool:
        if self.deadline is None:
            return False
        return self.deadline.is_expired()

    def _solver_info(self, level: int, *msgs) -> None:
        if self.verbose < level:
            return
        elapsed = self.deadline.elapsed_ms() if self.deadline else 0
        print(f"elapsed:{elapsed:6.0f}ms  loop_cnt:{self.loop_cnt:8d}  "
              f"node_cnt:{_HNODE_CNT:8d}\t" + " ".join(str(m) for m in msgs))


# ======================================================================
# 对外接口
# ======================================================================

def solve(
    ins: Instance,
    verbose: int = 0,
    deadline: Optional[Deadline] = None,
    rng: Optional[random.Random] = None,
    objective: Objective = Objective.OBJ_NONE,
    restart_rate: float = 0.001,
    guid_t_ms: float = 0.0,
    disappear_on_goal: bool = False,
) -> Tuple[Solution, str]:
    """
    对应 C++ solve() 函数
    返回 (solution, additional_info_str)

    guid_t_ms > 0：启用 GUIDANCE（论文 F2 配置），使用流量引导启发式
    guid_t_ms = 0：纯 LaCAM2 基线（无引导）
    """
    planner = Planner(ins, deadline, rng, verbose, objective, restart_rate, guid_t_ms, disappear_on_goal)
    return planner.solve()
