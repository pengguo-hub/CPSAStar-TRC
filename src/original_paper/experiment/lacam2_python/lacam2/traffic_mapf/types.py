"""
types.py
对应 C++ traffic_mapf/Types.h

定义所有共享数据结构和编译时常量（全部硬编码为论文 F2 配置）：
  GUIDANCE=ON, GUIDANCE_LNS=5000, INIT_PP=ON,
  OBJECTIVE=1 (OBJ::O_VC), FOCAL_SEARCH=2, LNS_GROUP_SIZE=10
"""

from __future__ import annotations
import sys
import re
from enum import IntEnum
from dataclasses import dataclass, field
from typing import List, Optional

# ===========================================================================
# 编译时常量（论文 F2 配置，不可修改）
# ===========================================================================

MAX_TIMESTEP: int = sys.maxsize // 2  # 对应 C++ INT_MAX/2

# 论文使用的配置
LNS_GROUP_SIZE: int = 10         # 每次 LNS 邻域大小
GUIDANCE_LNS: int = 5000         # LNS 最大迭代次数
FOCAL_SEARCH: int = 2            # Focal Search 宽松因子 w=2
INIT_PP: bool = True             # 使用 PP 风格初始化（aStarOF）


# ===========================================================================
# 枚举
# ===========================================================================

class OBJ(IntEnum):
    """对应 C++ enum OBJ"""
    NONE    = 0
    O_VC    = 1   # 论文使用：先最小化对向流，再最小化顶点流
    VC      = 2
    SUM_OVC = 3
    SUI_TC  = 4
    SUI_TG  = 5


class ADAPTIVE(IntEnum):
    """对应 C++ enum ADAPTIVE"""
    RANDOM     = 0
    CONGESTION = 1
    COUNT      = 2  # 方法总数


# 当前激活的优化目标（对应 C++ #define OBJECTIVE 1）
OBJECTIVE: int = OBJ.O_VC


# ===========================================================================
# 数据结构
# ===========================================================================

class Int4:
    """
    对应 C++ struct Int4 { int d[4]; }
    存储四个方向的流量：d[0]=右, d[1]=下, d[2]=左, d[3]=上
    """
    __slots__ = ("d",)

    def __init__(self):
        self.d: List[int] = [0, 0, 0, 0]

    def __repr__(self) -> str:
        return f"Int4(d={self.d})"


class HHNode:
    """
    对应 C++ struct HNode (TrafficMAPF 命名空间中，非 lacam2 的 HNode)
    用于 HeuristicTable 中的 BFS 节点
    """
    __slots__ = ("location", "direction", "value", "label", "other", "priority")

    def __init__(self, location: int, direction: int, value: int):
        self.location: int = location
        self.direction: int = direction
        self.value: int = value
        self.label: int = 0
        self.other: int = 0
        self.priority: int = 0

    def __repr__(self) -> str:
        return f"HHNode(loc={self.location}, val={self.value})"


class HeuristicTable:
    """
    对应 C++ struct HeuristicTable
    懒惰 BFS 距离表（从目标反向 BFS）
    htable[loc] = 从 loc 到目标的最短距离
    open = 待扩展的节点队列（deque 用作 BFS 队列）
    """
    __slots__ = ("htable", "open")

    def __init__(self):
        from collections import deque
        self.htable: List[int] = []      # 距离表，空表示未初始化
        self.open: "deque[HHNode]" = deque()

    def empty(self) -> bool:
        return len(self.htable) == 0

    def __repr__(self) -> str:
        return f"HeuristicTable(size={len(self.htable)})"


@dataclass
class D2P:
    """
    对应 C++ struct d2p
    dist-to-path 表中的一个条目
    """
    label: int = 0
    id: int = -1
    cost: int = MAX_TIMESTEP
    togo: int = MAX_TIMESTEP


class Dist2Path:
    """
    对应 C++ struct Dist2Path
    懒惰 BFS 距离-到-引导路径表
    dist2path[loc] = D2P(label, loc, dist_to_path, togo_along_path)
    """
    __slots__ = ("label", "dist2path", "open")

    def __init__(self):
        from collections import deque
        self.label: int = 0
        self.dist2path: List[D2P] = []   # 空表示未初始化
        self.open: "deque[D2P]" = deque()

    def empty(self) -> bool:
        return len(self.dist2path) == 0

    def __repr__(self) -> str:
        return f"Dist2Path(size={len(self.dist2path)}, label={self.label})"


# ===========================================================================
# SharedEnvironment（对应 C++ class SharedEnvironment，简化版）
# ===========================================================================

class AgentState:
    """对应 C++ struct State（简化版，只需要 location）"""
    __slots__ = ("location", "orientation", "timestep")

    def __init__(self, location: int = -1, orientation: int = -1, timestep: int = -1):
        self.location = location
        self.orientation = orientation
        self.timestep = timestep


class SharedEnvironment:
    """
    对应 C++ class SharedEnvironment（#ifndef ROBOT_RUNNERS 分支）
    存储地图信息（rows, cols, map, neighbors）和智能体状态
    """

    # 用于解析 .map 文件头的正则
    _r_height = re.compile(r'height\s(\d+)')
    _r_width  = re.compile(r'width\s(\d+)')
    _r_map    = re.compile(r'map')

    def __init__(self):
        self.num_of_agents: int = 0
        self.rows: int = 0
        self.cols: int = 0
        self.map: List[int] = []         # 0=通路, 1=障碍
        self.neighbors: List[List[int]] = []  # neighbors[loc] = 可达邻居 loc 列表
        self.curr_states: List[AgentState] = []
        self.max_h: int = 0

    def load_map(self, fname: str) -> None:
        """
        对应 C++ SharedEnvironment::load_map()
        加载 .map 文件（MovingAI 格式），构建 map 数组和 neighbors 邻居表
        """
        with open(fname, 'r') as f:
            lines = f.readlines()

        # 去掉行末 \r\n
        lines = [line.rstrip('\r\n') for line in lines]

        rows = 0
        cols = 0
        map_start = 0

        for idx, line in enumerate(lines):
            m = self._r_height.match(line)
            if m:
                rows = int(m.group(1))
                continue
            m = self._r_width.match(line)
            if m:
                cols = int(m.group(1))
                continue
            if self._r_map.match(line):
                map_start = idx + 1
                break

        self.rows = rows
        self.cols = cols
        self.map = [0] * (rows * cols)
        self.neighbors = [[] for _ in range(rows * cols)]

        # 读地图
        for y in range(rows):
            line = lines[map_start + y]
            for x in range(cols):
                s = line[x] if x < len(line) else '.'
                index = cols * y + x
                if s in ('T', '@'):
                    self.map[index] = 1  # 障碍

        # 构建邻居表（上下左右四方向，去除越界和障碍）
        for row in range(rows):
            for col in range(cols):
                loc = row * cols + col
                if self.map[loc] == 0:
                    if row > 0 and self.map[loc - cols] == 0:
                        self.neighbors[loc].append(loc - cols)
                    if row < rows - 1 and self.map[loc + cols] == 0:
                        self.neighbors[loc].append(loc + cols)
                    if col > 0 and self.map[loc - 1] == 0:
                        self.neighbors[loc].append(loc - 1)
                    if col < cols - 1 and self.map[loc + 1] == 0:
                        self.neighbors[loc].append(loc + 1)

    def __repr__(self) -> str:
        return (f"SharedEnvironment(rows={self.rows}, cols={self.cols}, "
                f"agents={self.num_of_agents})")
