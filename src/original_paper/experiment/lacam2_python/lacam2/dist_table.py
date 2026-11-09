"""
dist_table.py
对应 C++ dist_table.hpp / dist_table.cpp（GUIDANCE=ON 完整版本）

DistTable：
  - 基础：懒惰 BFS 距离表（Lazy Reverse BFS / Reverse Resumable A*）
  - 扩展：setup_guidance() 初始化 TrajLNS + 流量引导路径
    - INIT_PP=ON：使用 aStarOF 顺序规划（Algorithm 2 FindPaths）
    - GUIDANCE_LNS=5000：LNS PathRefinement 迭代优化
    - init_dist_table：为每条轨迹建立 Dist2Path 距离表
  - get_g() / get_gd()：有 GUIDANCE 时使用 get_dist_2_path 引导启发式
    而非纯 BFS 距离（对应论文 h_i(v) = d_p + d_g）
"""

from __future__ import annotations
import random as _std_random
import time
from collections import deque
from typing import List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .instance import Instance
    from .graph import Vertex

# 编译时控制（论文 F2 配置）
GUIDANCE: bool = True


class DistTable:
    """
    对应 C++ struct DistTable
    基础距离表 + GUIDANCE=ON 时的流量引导启发式
    """

    def __init__(self, ins: "Instance"):
        self.V_size: int = ins.G.size()
        # table[i][v_id] = 智能体 i 目标到 v_id 的最短距离
        self.table: List[List[int]] = [
            [self.V_size] * self.V_size for _ in range(ins.N)
        ]
        # 每个智能体的 BFS 队列（懒惰求值）
        self.OPEN: List[deque] = [deque() for _ in range(ins.N)]

        # GUIDANCE 相关成员（对应 C++ DistTable 中的 env, lns, traffic）
        self.guidance_ready: bool = False
        self._lns: Optional[object] = None     # TrajLNS 实例
        self._traffic: List[int] = []

        self._setup(ins)

    def _setup(self, ins: "Instance") -> None:
        """
        对应 C++ DistTable::setup()
        初始化：每个智能体目标加入 OPEN，距离设为 0
        """
        for i in range(ins.N):
            goal = ins.goals[i]
            self.OPEN[i].append(goal)
            self.table[i][goal.id] = 0

    # ------------------------------------------------------------------
    # setup_guidance
    # ------------------------------------------------------------------

    def setup_guidance(self, ins: "Instance", t_ms: float) -> None:
        """
        对应 C++ DistTable::setup_guidance(const Instance* ins, int t_ms)

        初始化完整的流量引导系统：
          1. 创建 SharedEnvironment（加载地图，设置智能体状态）
          2. 创建 TrajLNS，初始化内存池
          3. 初始化每个智能体目标的 HeuristicTable
          4. INIT_PP=ON：用 aStarOF 顺序规划（init_traj）
          5. GUIDANCE_LNS>0：LNS PathRefinement（destroy_improve）
          6. 为每条轨迹建立 Dist2Path 距离表（init_dist_table）

        t_ms：导引路径预算时间（毫秒）= GUID_T * 1000
        """
        import math
        from .traffic_mapf.types import SharedEnvironment, AgentState, MAX_TIMESTEP
        from .traffic_mapf.heuristics import init_heuristic
        from .traffic_mapf.traj_lns import TrajLNS
        from .traffic_mapf.flow import (
            init_traj, init_traj_st, init_dist_table, destroy_improve
        )

        # 对应 C++ std::srand(0)
        _std_random.seed(0)

        self.guidance_ready = True
        start_time = time.perf_counter()

        # 创建 SharedEnvironment
        env = SharedEnvironment()
        env.load_map(ins.G.filename)
        env.num_of_agents = ins.N

        # 创建 TrajLNS
        lns = TrajLNS(env)
        lns.init_mem()
        lns.start_time = start_time

        # 对应 C++ lns.t_ms = GUID_T*1000 - 1*(GUID_T/0.005)
        # 即：给定总预算 t_ms 毫秒，稍微保守一点
        GUID_T = t_ms / 1000.0  # 转回秒
        lns.t_ms = int(GUID_T * 1000 - 1 * (GUID_T / 0.005))
        if lns.t_ms <= 0:
            lns.t_ms = int(t_ms)

        # traffic 数组（-1 表示无约束）
        traffic = [-1] * len(env.map)
        self._traffic = traffic

        # 设置智能体状态
        env.curr_states = [AgentState() for _ in range(ins.N)]
        for i in range(ins.N):
            lns.tasks[i] = ins.goals[i].index
            env.curr_states[i].location = ins.starts[i].index
            # 初始化目标位置的 HeuristicTable
            init_heuristic(lns.heuristics[ins.goals[i].index], env, ins.goals[i].index)

        # ---- INIT_PP=ON：用 aStarOF 顺序规划 ----
        init_traj(lns, traffic, MAX_TIMESTEP)

        elapsed_init_us = int((time.perf_counter() - start_time) * 1e6)
        # print(f"---init-t,{elapsed_init_us}")

        updated: Set[int] = set()

        # ---- GUIDANCE_LNS=5000：LNS 优化 ----
        from .traffic_mapf.types import GUIDANCE_LNS
        # print(f"---op-flow,{lns.op_flow}")
        # print(f"---vertex-flow,{lns.vertex_flow}")
        destroy_improve(lns, traffic, updated, GUIDANCE_LNS, GUIDANCE_LNS)

        elapsed_lns_us = int((time.perf_counter() - start_time) * 1e6)
        # print(f"---lns-t,{elapsed_lns_us}")
        # print(f"---op-flow,{lns.op_flow}")
        # print(f"---vertex-flow,{lns.vertex_flow}")

        # ---- 建立 Dist2Path 距离表（引导启发式） ----
        init_dist_table(lns, traffic, MAX_TIMESTEP)

        elapsed_setup_us = int((time.perf_counter() - start_time) * 1e6)
        # print(f"---setup-t,{elapsed_setup_us}")

        self._lns = lns

    # ------------------------------------------------------------------
    # 基础懒惰 BFS 查询
    # ------------------------------------------------------------------

    def get(self, i: int, v_id: int) -> int:
        """
        查询智能体 i 目标到 v_id 的最短距离（懒惰 BFS）
        对应 C++ DistTable::get(uint i, uint v_id)
        """
        if self.table[i][v_id] < self.V_size:
            return self.table[i][v_id]

        while self.OPEN[i]:
            n = self.OPEN[i].popleft()
            d_n = self.table[i][n.id]
            for m in n.neighbor:
                d_m = self.table[i][m.id]
                if d_n + 1 < d_m:
                    self.table[i][m.id] = d_n + 1
                    self.OPEN[i].append(m)
            if n.id == v_id:
                return d_n

        return self.V_size

    def get_v(self, i: int, v: "Vertex") -> int:
        """
        对应 C++ DistTable::get(uint i, Vertex* v)
        有 GUIDANCE 时：使用 HeuristicTable（纯 BFS 距离）
        无 GUIDANCE 时：使用 DistTable BFS
        """
        if self.guidance_ready and self._lns is not None:
            lns = self._lns
            from .traffic_mapf.heuristics import get_heuristic
            return get_heuristic(
                lns.heuristics[lns.tasks[i]], lns.env,
                self._traffic, lns.flow, v.index
            )
        return self.get(i, v.id)

    # ------------------------------------------------------------------
    # 引导启发式查询（论文核心：h_i(v) = d_p + d_g）
    # ------------------------------------------------------------------

    def get_g(self, i: int, v: "Vertex") -> int:
        """
        对应 C++ DistTable::get_g(uint i, Vertex* v)

        GUIDANCE=ON, FLOW_GUIDANCE=OFF（论文使用 dist2path 分支）：
          若 traj_dists[i] 已初始化：返回 get_dist_2_path（d_p + d_g）
          否则回退到纯 BFS 距离

        这是 PIBT 中用于排序候选下一步的关键启发式。
        """
        if self.guidance_ready and self._lns is not None:
            lns = self._lns
            from .traffic_mapf.heuristics import get_heuristic, get_dist_2_path
            if lns.traj_dists[i].empty():
                # 回退：纯 BFS 距离
                return get_heuristic(
                    lns.heuristics[lns.tasks[i]], lns.env,
                    self._traffic, lns.flow, v.index
                )
            return get_dist_2_path(
                lns.traj_dists[i], lns.env, self._traffic, v.index
            )
        return self.get(i, v.id)

    def get_gd(self, i: int, v: "Vertex") -> int:
        """
        对应 C++ DistTable::get_gd(uint i, Vertex* v)

        GUIDANCE=ON, FLOW_GUIDANCE=OFF（论文使用 dist2path 分支）：
          与 get_g 相同（dist2path 返回 cost + togo，即 d_p + d_g）

        注意：C++ 代码中 get_gd 和 get_g 在 FLOW_GUIDANCE=OFF 分支
              返回值相同（都是 get_dist_2_path）。
              FLOW_GUIDANCE=ON 时 get_gd 返回 s->depth（路径深度），
              但本实现只支持 FLOW_GUIDANCE=OFF。
        """
        return self.get_g(i, v)
