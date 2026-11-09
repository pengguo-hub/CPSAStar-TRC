"""
traffic_mapf package
对应 C++ guided-pibt/traffic_mapf/ 下的所有文件
提供流量引导的路径规划（Traffic Flow Guided MAPF）

对应论文：
  "Traffic Flow Optimisation for Lifelong Multi-Agent Path Finding"
  (AAAI-24)

编译选项（全部硬编码为论文 F2 配置）：
  GUIDANCE=ON
  GUIDANCE_LNS=5000
  INIT_PP=ON
  OBJECTIVE=1  (OBJ::O_VC)
  FOCAL_SEARCH=2
  LNS_GROUP_SIZE=10
"""

from .types import (
    OBJ, ADAPTIVE,
    Int4, HeuristicTable, HHNode,
    Dist2Path, D2P,
    SharedEnvironment,
    MAX_TIMESTEP,
    LNS_GROUP_SIZE,
    GUIDANCE_LNS,
    FOCAL_SEARCH,
    OBJECTIVE,
    INIT_PP,
)
from .utils import get_d, get_neighbor_locs, manhattan_distance
from .search_node import SNode, MemoryPool
from .heap import PQueueMinOF, PQueueMinJam, PQueueMinF
from .heuristics import (
    init_heuristic, get_heuristic,
    init_dist_2_path, get_dist_2_path,
    init_flow_heuristic, get_flow_heuristic,
)
from .traj_lns import TrajLNS, FlowHeuristic
from .search import a_star_of, single_shortest_path
from .flow import (
    get_op_flow, get_vertex_flow,
    add_traj, remove_traj,
    init_traj, init_traj_st,
    init_dist_table,
    destroy_improve,
)

__all__ = [
    "OBJ", "ADAPTIVE", "Int4", "HeuristicTable", "HHNode",
    "Dist2Path", "D2P", "SharedEnvironment",
    "AgentState",
    "MAX_TIMESTEP", "LNS_GROUP_SIZE", "GUIDANCE_LNS",
    "FOCAL_SEARCH", "OBJECTIVE", "INIT_PP",
    "get_d", "get_neighbor_locs", "manhattan_distance",
    "SNode", "MemoryPool",
    "PQueueMinOF", "PQueueMinJam", "PQueueMinF",
    "init_heuristic", "get_heuristic",
    "init_dist_2_path", "get_dist_2_path",
    "init_flow_heuristic", "get_flow_heuristic",
    "TrajLNS", "FlowHeuristic",
    "a_star_of", "single_shortest_path",
    "get_op_flow", "get_vertex_flow",
    "add_traj", "remove_traj",
    "init_traj", "init_traj_st",
    "init_dist_table",
    "destroy_improve",
]
