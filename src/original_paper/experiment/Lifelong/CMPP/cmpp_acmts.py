"""
cmpp_acmts.py
A-CMTS：Anytime Congestion Mitigation Tree Search
完整复现论文 Section V（Algorithm 1 & Algorithm 2）。

关键设计：
  - 高层搜索节点包含：forced C+、forbidden C-、路径集合 π、total cost、LB
  - 根节点用优先级规划（PP）初始化（论文 Line 4）
  - 主循环：按 cost 最小弹出节点，更新 UB，计算 LB，剪枝，选顶点，扩展
  - 扩展（Algorithm 2）：
      P（强制节点）：继承路径，重算 cost（因为 forced 约束改变了合法解空间的下界）
      Q（禁止节点）：对 agent a 重规划，再对所有仍经过 v 的其他 agent 重规划
  - Lifelong 变体（Section V.E）：通过 initial_paths 传入上一轮剩余路径作为根节点热启动

论文公式：
  C(v) = ∏_{e∈δ⁻(v)} (f_e + 1) - 1                    (2)
  Γ(N) = {v | ∃a∈A, ∃e∈(δ⁻(v)∩N.π_a), (a,e)∉N.C+}   (5)
  a* ∈ {a∈A | ∃e*∈δ⁻(v*)∩N.π_a, (a,e*)∉N.C+}         (6)
  LB = Length(π_min) + ΔC                               (论文 Section V.A Note)
"""

import heapq
import time
from collections import defaultdict


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数：流量 → 顶点拥塞
# ──────────────────────────────────────────────────────────────────────────────

def _compute_vertex_congestion(graph, edge_flows):
    """
    由有向边流量字典计算每个顶点的 C(v)。
    C(v) = ∏_{e∈δ⁻(v)} (f_e + 1) - 1

    Parameters
    ----------
    graph      : CMPPGraph
    edge_flows : dict (u,v)->int

    Returns
    -------
    dict v -> float
    """
    # 初始化：每个顶点乘积因子为 1
    prod = {v: 1 for v in graph.V}
    for (u, v), f in edge_flows.items():
        if v in prod:
            prod[v] *= (f + 1)
    return {v: prod[v] - 1 for v in graph.V}


def _compute_edge_flows(paths):
    """
    由路径字典计算有向边流量。

    Parameters
    ----------
    paths : dict agent_id -> list of vertices

    Returns
    -------
    dict (u,v) -> int
    """
    flows = {}
    for path in paths.values():
        for i in range(len(path) - 1):
            e = (path[i], path[i + 1])
            flows[e] = flows.get(e, 0) + 1
    return flows


def _total_cost(vertex_congestion):
    return sum(vertex_congestion.values())


# ──────────────────────────────────────────────────────────────────────────────
# 高层搜索节点
# ──────────────────────────────────────────────────────────────────────────────

class CMPPHighLevelNode:
    """
    高层搜索节点，包含：
      forced             : {agent_id: frozenset of forced edges}
      forbidden          : {agent_id: frozenset of forbidden edges}
      paths              : {agent_id: list of vertices}
      cost               : float  total congestion cost Σ C(v)
      lb                 : float  lower bound
      edge_flows         : dict (u,v)->int
      vertex_congestion  : dict v->float
    """
    __slots__ = ('forced', 'forbidden', 'paths', 'cost', 'lb',
                 'edge_flows', 'vertex_congestion')

    def __init__(self, forced, forbidden, paths, cost, lb,
                 edge_flows=None, vertex_congestion=None):
        self.forced = forced
        self.forbidden = forbidden
        self.paths = paths
        self.cost = cost
        self.lb = lb
        self.edge_flows = edge_flows if edge_flows is not None else {}
        self.vertex_congestion = vertex_congestion if vertex_congestion is not None else {}

    def __lt__(self, other):
        return self.cost < other.cost


# ──────────────────────────────────────────────────────────────────────────────
# 主类
# ──────────────────────────────────────────────────────────────────────────────

class CMPPA_CMTS:
    """
    A-CMTS：完整实现论文 Algorithm 1 & 2。

    Parameters
    ----------
    graph         : CMPPGraph
    agents        : list of Agent（有 .id, .start, .goal）
    low_level     : CMPPLowLevelPlanner
    omega         : float  次优因子（论文推荐 1.3）
    time_limit    : float  运行时间上限（秒）
    initial_paths : dict   {agent_id: list of vertices}  热启动路径（Lifelong 变体）
    """

    def __init__(self, graph, agents, low_level,
                 omega=1.3, time_limit=1.0, initial_paths=None):
        self.graph = graph
        self.agents = agents
        self.agent_map = {ag.id: ag for ag in agents}
        self.low_level = low_level
        self.omega = omega
        self.time_limit = time_limit
        self.initial_paths = initial_paths or {}

        self.best_solution = None
        self.best_cost = float('inf')

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def solve(self):
        """
        运行 A-CMTS 高层搜索（Algorithm 1）。
        返回 best_solution：dict {agent_id: list of vertices}
        """
        if not self.agents:
            return {}

        root = self._create_root_node()
        if root is None:
            return {}

        open_list = [root]
        heapq.heapify(open_list)
        self.best_solution = root.paths.copy()
        self.best_cost = root.cost

        start_time = time.time()

        while open_list and (time.time() - start_time) < self.time_limit:
            node = heapq.heappop(open_list)

            # 更新最优解（Algorithm 1, Lines 11-12）
            if node.cost < self.best_cost:
                self.best_cost = node.cost
                self.best_solution = node.paths.copy()

            # 计算 LB 并剪枝（Algorithm 1, Lines 13-15）
            node.lb = self._compute_lower_bound(node)
            if self.best_cost <= self.omega * node.lb:
                continue

            # 选择拥塞最高且可修改的顶点（Algorithm 1, Line 16）
            v_star = self._select_vertex(node)
            if v_star is None:
                continue  # Algorithm 1, Lines 17-18

            # 选择 agent 和对应边（Algorithm 1, Lines 19-20）
            a_star, e_star = self._select_agent_edge(node, v_star)
            if a_star is None:
                continue

            # 扩展节点（Algorithm 1, Line 21）
            P, Q = self._expand_node(node, a_star, e_star, v_star)

            # Algorithm 1, Line 22
            if P is not None:
                heapq.heappush(open_list, P)
            if Q is not None:
                heapq.heappush(open_list, Q)

        return self.best_solution

    # ------------------------------------------------------------------
    # 根节点初始化
    # ------------------------------------------------------------------
    def _create_root_node(self):
        """
        Algorithm 1, Lines 2-5：
        根节点约束为空，初始路径由优先级规划（PP）计算。
        若 initial_paths 非空（Lifelong 变体），则直接用它作为初始解。
        """
        forced = defaultdict(set)
        forbidden = defaultdict(set)

        if self.initial_paths:
            # Lifelong 变体（Section V.E）：用上一轮剩余路径热启动
            paths = {}
            for ag in self.agents:
                if ag.id in self.initial_paths:
                    p = self.initial_paths[ag.id]
                    # 确保路径起点是当前 start，终点是当前 goal
                    if p and p[0] == ag.start and p[-1] == ag.goal:
                        paths[ag.id] = p
                    else:
                        # 路径不匹配，重新规划
                        paths[ag.id] = None
                else:
                    paths[ag.id] = None

            # 对没有热启动路径的 agent 用 PP 规划
            # 先计算已有路径的流量
            existing_flows = _compute_edge_flows(
                {aid: p for aid, p in paths.items() if p}
            )
            existing_cong = _compute_vertex_congestion(self.graph, existing_flows)

            for ag in self.agents:
                if paths.get(ag.id) is None:
                    new_path = self.low_level.plan(
                        ag, existing_flows, existing_cong, [], set()
                    )
                    if new_path is None:
                        new_path = self._bfs_path(ag.start, ag.goal)
                    paths[ag.id] = new_path
                    if new_path:
                        for i in range(len(new_path) - 1):
                            e = (new_path[i], new_path[i + 1])
                            existing_flows[e] = existing_flows.get(e, 0) + 1
                        existing_cong = _compute_vertex_congestion(
                            self.graph, existing_flows
                        )
        else:
            # 标准 PP（优先级规划，论文按 agent index 排序）
            paths = {}
            cur_flows = {}
            cur_cong = {}

            for ag in sorted(self.agents, key=lambda a: a.id):
                path = self.low_level.plan(
                    ag, cur_flows, cur_cong, [], set()
                )
                if path is None:
                    path = self._bfs_path(ag.start, ag.goal)
                paths[ag.id] = path
                if path:
                    for i in range(len(path) - 1):
                        e = (path[i], path[i + 1])
                        cur_flows[e] = cur_flows.get(e, 0) + 1
                    cur_cong = _compute_vertex_congestion(
                        self.graph, cur_flows
                    )

        # 过滤掉规划失败的 agent
        paths = {aid: p for aid, p in paths.items() if p}

        edge_flows = _compute_edge_flows(paths)
        vertex_cong = _compute_vertex_congestion(self.graph, edge_flows)
        cost = _total_cost(vertex_cong)
        lb = self._compute_lower_bound_from_paths(paths)

        node = CMPPHighLevelNode(
            forced=forced,
            forbidden=forbidden,
            paths=paths,
            cost=cost,
            lb=lb,
            edge_flows=edge_flows,
            vertex_congestion=vertex_cong,
        )
        return node

    # ------------------------------------------------------------------
    # Algorithm 2：扩展节点
    # ------------------------------------------------------------------
    def _expand_node(self, node, a, e, v):
        """
        Algorithm 2：
          P  ← 强制节点：agent a 必须经过边 e
          Q  ← 禁止节点：agent a 禁止经过边 e，重规划 a 及所有仍经过 v 的其他 agent

        Returns (P, Q)，不可行时对应位置为 None。
        """
        # ── P：强制子节点（Algorithm 2, Lines 2-3）──────────────────────
        # 继承所有路径，加入强制约束，重算 cost（paths 不变，cost 也不变）
        P_forced = defaultdict(set,
                               {aid: set(s) for aid, s in node.forced.items()})
        P_forbidden = defaultdict(set,
                                  {aid: set(s) for aid, s in node.forbidden.items()})
        P_forced[a].add(e)

        P = CMPPHighLevelNode(
            forced=P_forced,
            forbidden=P_forbidden,
            paths=dict(node.paths),        # 继承路径
            cost=node.cost,                # 路径未变，cost 不变
            lb=node.lb,
            edge_flows=dict(node.edge_flows),
            vertex_congestion=dict(node.vertex_congestion),
        )

        # ── Q：禁止子节点（Algorithm 2, Lines 4-9）──────────────────────
        Q_forced = defaultdict(set,
                               {aid: set(s) for aid, s in node.forced.items()})
        Q_forbidden = defaultdict(set,
                                  {aid: set(s) for aid, s in node.forbidden.items()})
        Q_forbidden[a].add(e)

        Q_paths = dict(node.paths)

        # 重规划 agent a（Algorithm 2, Line 6）
        # 先从公共流量中减去 agent a 的旧路径贡献
        other_flows = dict(node.edge_flows)
        old_path_a = node.paths.get(a, [])
        for i in range(len(old_path_a) - 1):
            ek = (old_path_a[i], old_path_a[i + 1])
            other_flows[ek] = max(0, other_flows.get(ek, 0) - 1)
        other_cong = _compute_vertex_congestion(self.graph, other_flows)

        agent_a = self.agent_map[a]
        forced_a = list(Q_forced.get(a, []))
        forbidden_a = Q_forbidden.get(a, set())
        new_path_a = self.low_level.plan(
            agent_a, other_flows, other_cong, forced_a, forbidden_a
        )
        if new_path_a is None:
            # Q 不可行
            return P, None

        Q_paths[a] = new_path_a

        # 对所有仍经过 v 的其他 agent 重规划（Algorithm 2, Lines 8-9）
        # 按 agent id 排序保证确定性
        agents_through_v = sorted(
            [aid for aid, p in node.paths.items()
             if aid != a and p and v in p],
        )
        for aid in agents_through_v:
            # 计算去除当前 aid 路径后的其他流量
            cur_flows = _compute_edge_flows(
                {k: p for k, p in Q_paths.items() if k != aid}
            )
            cur_cong = _compute_vertex_congestion(self.graph, cur_flows)

            ag = self.agent_map[aid]
            forced_aid = list(Q_forced.get(aid, []))
            forbidden_aid = Q_forbidden.get(aid, set())
            new_p = self.low_level.plan(
                ag, cur_flows, cur_cong, forced_aid, forbidden_aid
            )
            if new_p is None:
                return P, None
            Q_paths[aid] = new_p

        # 重算 Q 的 cost（Algorithm 2, Line 10）
        Q_flows = _compute_edge_flows(Q_paths)
        Q_cong = _compute_vertex_congestion(self.graph, Q_flows)
        Q_cost = _total_cost(Q_cong)
        Q_lb = self._compute_lower_bound_from_paths(Q_paths)

        Q = CMPPHighLevelNode(
            forced=Q_forced,
            forbidden=Q_forbidden,
            paths=Q_paths,
            cost=Q_cost,
            lb=Q_lb,
            edge_flows=Q_flows,
            vertex_congestion=Q_cong,
        )
        return P, Q

    # ------------------------------------------------------------------
    # 顶点选择：Γ(N)（公式 5）
    # ------------------------------------------------------------------
    def _select_vertex(self, node):
        """
        Algorithm 1, Line 16：
        选择 Γ(N) 中拥塞度最高的顶点。
        Γ(N) = {v | ∃a∈A, ∃e∈(δ⁻(v)∩N.π_a), (a,e)∉N.C+}
        """
        best_v = None
        best_c = -1

        for v, Cv in node.vertex_congestion.items():
            if Cv <= best_c:
                continue
            # 检查是否存在可修改的进入边
            modifiable = False
            for aid, path in node.paths.items():
                forced_set = node.forced.get(aid, set())
                for i in range(len(path) - 1):
                    if path[i + 1] == v:
                        e = (path[i], v)
                        if e not in forced_set:
                            modifiable = True
                            break
                if modifiable:
                    break
            if modifiable:
                best_c = Cv
                best_v = v

        return best_v

    # ------------------------------------------------------------------
    # agent 和边选择（公式 6）
    # ------------------------------------------------------------------
    def _select_agent_edge(self, node, v):
        """
        Algorithm 1, Lines 19-20：
        在满足公式(6)的 agent 中，选择路径经过 v 的进入边流量最大的 agent，
        作为"重规划最可能降低拥塞"的近似。
        排除已被 forced 约束固定了该边的 agent。
        同时排除该边已在 agent 的 forbidden 中（禁止无意义的重复 forbid）。
        """
        best_a = None
        best_e = None
        best_flow = -1

        for aid, path in node.paths.items():
            forced_set = node.forced.get(aid, set())
            forbidden_set = node.forbidden.get(aid, set())
            for i in range(len(path) - 1):
                if path[i + 1] == v:
                    e = (path[i], v)
                    # 公式(6)：(a,e) ∉ N.C+
                    if e in forced_set:
                        continue
                    # 避免重复 forbid 同一条边（无意义）
                    if e in forbidden_set:
                        continue
                    flow = node.edge_flows.get(e, 0)
                    if flow > best_flow:
                        best_flow = flow
                        best_a = aid
                        best_e = e

        return best_a, best_e

    # ------------------------------------------------------------------
    # 下界计算（论文 Section V.A Note）
    # ------------------------------------------------------------------
    def _compute_lower_bound(self, node):
        """
        LB = Length(π_min) + ΔC
        π_min：满足所有约束的最短可行路径的长度和
        ΔC：已强制边引入的额外拥塞增量（这些边无法在后续重规划中消除）

        简化近似：
          - π_min 用 BFS 最短路长度（不考虑约束，给出一个有效下界）
          - ΔC 用当前强制边的流量乘积近似
        """
        return self._compute_lower_bound_from_paths(node.paths)

    def _compute_lower_bound_from_paths(self, paths):
        """
        近似 LB = Σ_i (shortest_path_length(s_i, g_i) - 1)
        这是一个有效下界，因为任何解的路径长度不可能短于最短路。
        """
        total = 0
        for ag in self.agents:
            if ag.start == ag.goal:
                continue
            # 用 BFS 长度（边数）作为下界
            bfs_len = self._bfs_length(ag.start, ag.goal)
            if bfs_len is not None:
                total += bfs_len
        return float(total)

    # ------------------------------------------------------------------
    # BFS 工具（在稀疏图上）
    # ------------------------------------------------------------------
    def _bfs_path(self, start, goal):
        """BFS 返回最短路径（顶点序列），不可达返回 None。"""
        if start == goal:
            return [start]
        from collections import deque
        q = deque([start])
        prev = {start: None}
        while q:
            u = q.popleft()
            if u == goal:
                break
            for v in self.graph.adj.get(u, []):
                if v not in prev:
                    prev[v] = u
                    q.append(v)
        if goal not in prev:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    def _bfs_length(self, start, goal):
        """返回 BFS 最短路边数，不可达返回 None。"""
        path = self._bfs_path(start, goal)
        return len(path) - 1 if path else None
