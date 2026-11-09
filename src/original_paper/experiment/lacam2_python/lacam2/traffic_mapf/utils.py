"""
utils.py
对应 C++ traffic_mapf/utils.hpp + utils.cpp

提供：
  get_d()            : 由位置差值计算移动方向编号
  get_neighbor_locs(): 获取某位置的四方向邻居（填入固定长度数组）
  manhattan_distance(): 曼哈顿距离
"""

from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import SharedEnvironment


def get_d(diff: int, env: "SharedEnvironment") -> int:
    """
    对应 C++ int get_d(int diff, const SharedEnvironment* env)
    由 (next - curr) 的差值计算方向编号：
      d=0: 右  (diff == +1)
      d=1: 下  (diff == +cols)
      d=2: 左  (diff == -1)
      d=3: 上  (diff == -cols)
    对立方向 = (d + 2) % 4
    """
    if diff == 1:
        return 0
    elif diff == -1:
        return 2
    elif diff == env.cols:
        return 1
    else:
        return 3


def get_neighbor_locs(env: "SharedEnvironment",
                      neighbors: List[int],
                      location: int) -> None:
    """
    对应 C++ void getNeighborLocs(SharedEnvironment*, int[], int)
    将 location 的邻居填入 neighbors（长度 4，不足补 -1）
    直接使用 env.neighbors 预先算好的邻居表
    """
    nb = env.neighbors[location]
    size = len(nb)
    for i in range(4):
        if i < size:
            neighbors[i] = nb[i]
        else:
            neighbors[i] = -1


def get_neighbor_locs_list(env: "SharedEnvironment",
                           location: int) -> List[int]:
    """
    对应 C++ void getNeighborLocs(SharedEnvironment*, vector<int>&, int)
    返回邻居列表（长度不定）
    """
    return list(env.neighbors[location])


def manhattan_distance(loc: int, loc2: int, env: "SharedEnvironment") -> int:
    """
    对应 C++ int manhattanDistance(int loc, int loc2, SharedEnvironment*)
    """
    loc_x, loc_y   = divmod(loc,  env.cols)
    loc2_x, loc2_y = divmod(loc2, env.cols)
    return abs(loc_x - loc2_x) + abs(loc_y - loc2_y)
