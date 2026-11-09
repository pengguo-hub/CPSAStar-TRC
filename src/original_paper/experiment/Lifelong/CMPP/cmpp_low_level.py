"""
cmpp_low_level.py
低层规划器：给定 agent 及其约束，返回最小化增量拥塞的路径。

论文 Section V.C 说明：
  低层搜索最小化 Σ ΔC(v)，其中 ΔC(v) 是 agent a 加入后顶点 v 拥塞度的增量。

  推导：
    C_others(v) = ∏_{e ∈ δ⁻(v)} (f_e + 1) - 1   （其他 agent 的贡献）
    agent a 通过边 (u,v) 进入 v 时，该边流量从 f_{(u,v)} 变为 f_{(u,v)}+1，
    其余进入 v 的边流量不变。
    新 C(v) = (C_others(v) + 1) × (f_{(u,v)} + 2) / (f_{(u,v)} + 1) - 1
    ΔC(v)   = 新C(v) - C_others(v)
            = (C_others(v) + 1) × [(f_{(u,v)} + 2) / (f_{(u,v)} + 1) - 1]
            = (C_others(v) + 1) / (f_{(u,v)} + 1)

  注意：other_congestion[v] 须是去掉 agent a 自身贡献后的 C_others(v)，
  other_flows[(u,v)] 须是去掉 agent a 自身贡献后的流量。
  调用方在 _expand 中已经将 agent a 的旧路径从 other_flows 减去，因此直接使用即可。

  强制边处理（论文 Section V.C Note）：
    对强制边集合 C+_a，先按当前起点的欧氏距离排序，然后依次用 Dijkstra 从
    上一段终点规划到当前强制边起点，再强制走该边，最后规划到 goal。
    拼接所有段得到最终路径。
    路径须满足 simple path 约束（无重复顶点）。
"""

import heapq


class CMPPLowLevelPlanner:
    """低层规划器：最小化增量拥塞的 Dijkstra，支持强制/禁止边"""

    def __init__(self, graph, delta=1.0):
        self.graph = graph
        self.delta = delta  # 保留接口，当前实现中未使用

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def plan(self, agent, other_flows, other_congestion,
             forced_edges, forbidden_edges):
        """
        Parameters
        ----------
        agent          : 具有 .start, .goal 属性的对象
        other_flows    : dict (u,v)->int   其他 agent 在该有向边上的流量
        other_congestion: dict v->float    其他 agent 在该顶点的 C_others(v)
        forced_edges   : list of (u,v)     必须按顺序经过的有向边
        forbidden_edges: set  of (u,v)     禁止使用的有向边

        Returns
        -------
        list of vertices (path)，或 None（不可达）
        """
        # 1. 对强制边按「当前起点 → 边起点」的欧氏距离排序（论文 Section V.C）
        if forced_edges:
            start_pos = agent.start
            forced_edges = sorted(
                forced_edges,
                key=lambda e: self.graph.distance(start_pos, e[0])
            )

        # 2. 分段规划
        segments = []
        current_start = agent.start
        visited = set()  # 用于 simple-path 检查（近似：按访问顺序去重）

        for fu, fv in forced_edges:
            # 规划到强制边起点
            seg = self._dijkstra(
                current_start, fu,
                other_flows, other_congestion,
                forbidden_edges, visited
            )
            if seg is None:
                return None
            # 去掉末尾（避免与强制边起点重复），将已访问节点加入 visited
            for v in seg[:-1]:
                visited.add(v)
            segments.append(seg[:-1])

            # 强制边本身
            if fv in visited:
                # simple path 冲突，规划失败
                return None
            segments.append([fu, fv])
            visited.add(fu)
            visited.add(fv)
            current_start = fv

        # 最后一段：current_start → goal
        last_seg = self._dijkstra(
            current_start, agent.goal,
            other_flows, other_congestion,
            forbidden_edges, visited
        )
        if last_seg is None:
            return None
        segments.append(last_seg)

        # 3. 拼接所有段
        full_path = []
        for seg in segments:
            if not seg:
                continue
            if full_path and seg[0] == full_path[-1]:
                full_path.extend(seg[1:])
            else:
                full_path.extend(seg)

        return full_path if full_path else None

    # ------------------------------------------------------------------
    # Dijkstra：最小化增量拥塞 ΔC(v)
    # ------------------------------------------------------------------
    def _dijkstra(self, start, goal,
                  other_flows, other_congestion,
                  forbidden_edges, visited_set):
        """
        返回从 start 到 goal 的最小 Σ ΔC(v) 路径（顶点序列），
        或 None（不可达）。

        ΔC(v) = (C_others(v) + 1) / (f_{(u,v)} + 1)

        visited_set：已被之前分段使用的顶点（simple-path 约束），
                     goal 顶点本身不做限制（允许到达 goal 即使 goal 已在 visited）。
        """
        INF = float('inf')

        # 初始化
        dist = {}
        prev = {}
        dist[start] = 0.0
        pq = [(0.0, id(start), start)]  # (cost, tiebreak, vertex)

        while pq:
            d, _, u = heapq.heappop(pq)
            if d > dist.get(u, INF) + 1e-12:
                continue
            if u == goal:
                break

            for v in self.graph.adj[u]:
                e = (u, v)
                # 禁止边
                if e in forbidden_edges:
                    continue
                # simple-path：除 goal 外，不重复经过 visited_set 中的顶点
                if v in visited_set and v != goal:
                    continue

                # ΔC(v) = (C_others(v) + 1) / (f_{(u,v)} + 1)
                C_others_v = other_congestion.get(v, 0.0)
                f_uv = other_flows.get(e, 0)
                delta_c = (C_others_v + 1.0) / (f_uv + 1.0)

                nd = d + delta_c
                if nd < dist.get(v, INF) - 1e-12:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, id(v), v))

        if goal not in dist:
            return None

        # 重建路径
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()

        # 验证路径起点
        if path[0] != start:
            return None

        return path
