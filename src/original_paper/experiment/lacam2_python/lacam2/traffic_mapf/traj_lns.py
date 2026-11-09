"""
traj_lns.py
对应 C++ traffic_mapf/TrajLNS.h

定义：
  FlowHeuristic : 流量感知启发式（对应 C++ struct FlowHeuristic）
  TrajLNS       : 轨迹 LNS 主对象（对应 C++ class TrajLNS）
"""

from __future__ import annotations
from typing import List, Set, Optional, TYPE_CHECKING

from .types import (
    Int4, HeuristicTable, Dist2Path, SharedEnvironment,
    ADAPTIVE, LNS_GROUP_SIZE,
)
from .search_node import SNode, MemoryPool
from .heap import PQueueMinOF

if TYPE_CHECKING:
    pass


# ===========================================================================
# FlowHeuristic
# ===========================================================================

class FlowHeuristic:
    """
    对应 C++ struct FlowHeuristic

    用于流量感知的 Dijkstra 式反向搜索。
    以目标为起点，计算考虑流量代价的最短路径树。

    字段：
      h      : 指向对应的 HeuristicTable（纯距离启发式，从 start 反向 BFS）
      target : 智能体的目标 location
      origin : 智能体的起始 location
      open   : pqueue_min_of（按 (op_flow, f) 排序的 OPEN 队列）
      mem    : 内存池（按位置索引的搜索节点）
    """

    def __init__(self):
        self.h: Optional[HeuristicTable] = None
        self.target: int = -1
        self.origin: int = -1
        self.open: "PQueue" = PQueueMinOF()   # 对应 C++ pqueue_min_of open
        self.mem: MemoryPool = MemoryPool()

    def empty(self) -> bool:
        """对应 C++ FlowHeuristic::empty()"""
        return self.mem.generated() == 0

    def reset(self) -> None:
        """
        对应 C++ FlowHeuristic::reset()
        清空 open 队列，重置内存池（O(1)）
        """
        self.open.clear()
        self.mem.reset()

    def __repr__(self) -> str:
        return (f"FlowHeuristic(target={self.target}, "
                f"origin={self.origin}, generated={self.mem.generated()})")


# ===========================================================================
# TrajLNS
# ===========================================================================

class TrajLNS:
    """
    对应 C++ class TrajLNS

    主状态对象，维护：
      trajs[i]          : 智能体 i 的当前轨迹（位置序列）
      flow[loc]         : 每个位置的四方向流量（Int4）
      heuristics[loc]   : 以 loc 为目标的懒惰 BFS 距离表
      traj_dists[i]     : 智能体 i 的引导路径距离表（Dist2Path）
      goal_nodes[i]     : 智能体 i 最近一次搜索的 goal s_node（含代价信息）
      flow_heuristics[i]: 流量感知启发式（FLOW_GUIDANCE 分支，本实现使用 dist2path 分支）
      occupations[loc]  : 当前占用 loc 的智能体集合
      op_flow           : 全局对向流代价总和
      vertex_flow       : 全局顶点流代价总和
      soc               : 全局 sum-of-cost（所有轨迹长度之和）
      weights[ADAPTIVE] : LNS 自适应权重
      tabu_list[i]      : tabu 表（select_most_expensive 用）
    """

    def __init__(self, env: SharedEnvironment):
        self.env: SharedEnvironment = env
        N = env.num_of_agents
        M = len(env.map)

        # 时间控制（对应 C++ start_time + t_ms）
        import time
        self.start_time: float = time.perf_counter()
        self.t_ms: int = 0   # >0 时作为全局时间预算上限（毫秒）

        # 轨迹和任务
        self.trajs: List[List[int]] = [[] for _ in range(N)]
        self.tasks: List[int] = [-1] * N  # tasks[i] = 智能体 i 的目标 location

        # 流量
        self.flow: List[Int4] = [Int4() for _ in range(M)]

        # 启发式表（以 location 为 key）
        self.heuristics: List[HeuristicTable] = [HeuristicTable() for _ in range(M)]

        # 引导路径距离表（每个智能体一个）
        self.traj_dists: List[Dist2Path] = [Dist2Path() for _ in range(N)]

        # 搜索结果节点
        self.goal_nodes: List[SNode] = [SNode() for _ in range(N)]

        # 流量感知启发式（FLOW_GUIDANCE 用，本版本不使用但需要占位）
        self.flow_heuristics: List[FlowHeuristic] = [FlowHeuristic() for _ in range(N)]

        # LNS 相关
        self.occupations: List[Set[int]] = [set() for _ in range(M)]
        self.tabu_list: List[bool] = [False] * N
        self.num_in_tablu: int = 0

        # 全局代价
        self.op_flow: int = 0
        self.vertex_flow: int = 0
        self.soc: int = 0

        # 自适应 LNS 权重（每种方法一个，初始相等）
        self.weights: List[float] = [1.0] * int(ADAPTIVE.COUNT)

        self.decay_factor: float = 0.001
        self.reaction_factor: float = 0.1
        self.group_size: int = LNS_GROUP_SIZE

        # 进度计数
        self.traj_inited: int = 0
        self.dist2path_inited: int = 0
        self.tdh_build: int = 0

        # 内存池（所有搜索共享，每次搜索前 reset）
        self.mem: MemoryPool = MemoryPool()

    def init_mem(self) -> None:
        """
        对应 C++ TrajLNS::init_mem()
        初始化共享内存池（大小 = 地图节点数）
        """
        self.mem.init(len(self.env.map))

    def elapsed_ms(self) -> float:
        """返回从 start_time 起经过的毫秒数"""
        import time
        return (time.perf_counter() - self.start_time) * 1000.0

    def is_time_up(self) -> bool:
        """检查是否超出 t_ms 时间预算"""
        if self.t_ms == 0:
            return False
        return self.elapsed_ms() > self.t_ms

    def __repr__(self) -> str:
        return (f"TrajLNS(N={self.env.num_of_agents}, "
                f"op_flow={self.op_flow}, vertex_flow={self.vertex_flow}, "
                f"soc={self.soc})")
