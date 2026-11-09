"""
shared_env.py
=============
对应 C++ guided-pibt/inc/SharedEnv.h + ActionModel.h + States.h + Tasks.h

定义：
  Action        — 枚举：FW（前进）/ CR（顺时针转）/ CCR（逆时针转）/ W（等待）/ NA
  AgentState    — 单个 agent 的当前状态（location, orientation, timestep）
  Task          — 单个任务（task_id, location, t_assigned, t_finished）
  SharedEnv     — 全局共享环境（地图 + agent 状态 + 当前任务 + 路径队列）
                  对应 C++ class SharedEnvironment（guided-pibt 版本）

注意：guided-pibt 中 agent 移动模型是"朝向+转向"（orientation-based），
但本实现简化为无朝向的 4 连通网格移动（与你现有框架一致），
每步直接给出目标位置而非动作类型，保持与 GridMap 的兼容性。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Deque
from collections import deque
import numpy as np


# ===========================================================================
# Action（对应 C++ enum Action）
# ===========================================================================

class Action:
    FW  = 0   # 前进（移动到下一格）
    CR  = 1   # 顺时针转（不移动）
    CCR = 2   # 逆时针转（不移动）
    W   = 3   # 原地等待
    NA  = 4   # 无动作（未规划）


# ===========================================================================
# AgentState（对应 C++ struct State in States.h）
# ===========================================================================

@dataclass
class AgentState:
    """
    对应 C++ struct State { int location; int orientation; int timestep; }
    location    : 在 map 数组中的 1D 索引 = row * cols + col
    orientation : 朝向（0=东/右, 1=南/下, 2=西/左, 3=北/上），本实现不用但保留字段
    timestep    : 最后更新的时间步
    """
    location:    int = -1
    orientation: int = 0
    timestep:    int = 0

    def xy(self, cols: int):
        """返回 (col, row) 即 (x, y)"""
        return (self.location % cols, self.location // cols)


# ===========================================================================
# Task（对应 C++ struct Task in Tasks.h）
# ===========================================================================

@dataclass
class Task:
    """
    对应 C++ struct Task { int task_id; int location; int t_assigned; int t_finished; }
    在 lifelong MAPF 中，每个 task 是一个目标位置（agent 到达即完成）。
    你的框架是 pickup → dropoff 两段，拆成两个 Task 即可。
    """
    task_id:    int = -1
    location:   int = -1   # 目标位置（1D index）
    t_assigned: int = -1   # 分配时间步
    t_finished: int = -1   # 完成时间步（-1 = 未完成）

    @property
    def is_finished(self) -> bool:
        return self.t_finished >= 0


# ===========================================================================
# SharedEnv（对应 C++ class SharedEnvironment in SharedEnv.h，guided-pibt 版）
# ===========================================================================

class SharedEnv:
    """
    对应 C++ class SharedEnvironment（guided-pibt 版本）

    字段（与 C++ 原版对齐）：
      rows, cols          : 地图尺寸
      map                 : 地图数组（0=通路，1=障碍），一维，行优先
      neighbors           : neighbors[loc] = 可达邻居 loc 列表（4 连通，不含障碍）
      num_of_agents       : agent 数量（对应 C++ num_of_agents）
      curr_states         : List[AgentState]，长度 = num_of_agents
      goal_locations      : List[Deque[Tuple[int,int]]]
                            goal_locations[i] = deque of (location, t_assigned)
                            对应 C++ vector<deque<pair<int,int>>> goal_locations
      paths               : List[List[int]]，paths[i] = agent i 规划的路径（1D loc 序列）
      plan_start          : paths 的起始时间步（对应 C++ plan_start）
      task_finished       : 已完成任务总数（对应 C++ task_finished）
    """

    def __init__(self):
        self.rows: int = 0
        self.cols: int = 0
        self.map: List[int] = []
        self.neighbors: List[List[int]] = []
        self.num_of_agents: int = 0

        # agent 状态
        self.curr_states: List[AgentState] = []

        # 目标队列：goal_locations[i] = deque of (loc, t_assigned)
        # agent i 的当前目标是 goal_locations[i][0]
        self.goal_locations: List[Deque] = []

        # 路径（plan_start 时刻起的位置序列）
        self.paths: List[List[int]] = []
        self.plan_start: int = 0

        # 统计
        self.task_finished: int = 0
        self.curr_timestep: int = 0  # 对应 C++ env->curr_timestep

    # ------------------------------------------------------------------
    # 从 GridMap 初始化
    # ------------------------------------------------------------------

    def load_from_gridmap(self, grid) -> None:
        """
        从 BenchmarkLoader 返回的 GridMap 对象初始化地图。
        grid.grid[y][x] == 0 表示可通行，!= 0 表示障碍。
        """
        self.rows = grid.height
        self.cols = grid.width
        self.map = [0] * (self.rows * self.cols)
        self.neighbors = [[] for _ in range(self.rows * self.cols)]

        for y in range(self.rows):
            for x in range(self.cols):
                loc = y * self.cols + x
                if grid.grid[y][x] != 0:
                    self.map[loc] = 1  # 障碍

        # 构建邻居表（4 连通，不越界，不进障碍）
        for y in range(self.rows):
            for x in range(self.cols):
                loc = y * self.cols + x
                if self.map[loc] != 0:
                    continue
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < self.rows and 0 <= nx < self.cols:
                        nb_loc = ny * self.cols + nx
                        if self.map[nb_loc] == 0:
                            self.neighbors[loc].append(nb_loc)

    # ------------------------------------------------------------------
    # 初始化 agents
    # ------------------------------------------------------------------

    def init_agents(self, initial_positions: dict) -> None:
        """
        从 initial_positions: {agv_id: (x, y)} 初始化 agent 状态。
        agv_id 按 'agv_0', 'agv_1', ... 顺序对应 agent index 0, 1, ...
        """
        self.num_of_agents = len(initial_positions)
        self.curr_states = []
        self.goal_locations = [deque() for _ in range(self.num_of_agents)]
        self.paths = [[] for _ in range(self.num_of_agents)]

        # 按 agv_0, agv_1, ... 顺序排列
        for i in range(self.num_of_agents):
            agv_id = f"agv_{i}"
            x, y = initial_positions[agv_id]
            loc = y * self.cols + x
            self.curr_states.append(AgentState(location=loc, orientation=0, timestep=0))

    # ------------------------------------------------------------------
    # 坐标转换工具
    # ------------------------------------------------------------------

    def xy_to_loc(self, x: int, y: int) -> int:
        return y * self.cols + x

    def loc_to_xy(self, loc: int):
        return (loc % self.cols, loc // self.cols)

    def is_valid_loc(self, loc: int) -> bool:
        return 0 <= loc < len(self.map) and self.map[loc] == 0

    def build_reachable_set(self) -> None:
        from collections import deque as _deque
        visited: set = set()
        best: set = set()
        for start in range(len(self.map)):
            if self.map[start] != 0 or start in visited:
                continue
            component: set = set()
            q = _deque([start])
            component.add(start)
            visited.add(start)
            while q:
                cur = q.popleft()
                for nb in self.neighbors[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        component.add(nb)
                        q.append(nb)
            if len(component) > len(best):
                best = component
        self._reachable: set = best

    def is_reachable(self, loc: int) -> bool:
        if not hasattr(self, '_reachable'):
            self.build_reachable_set()
        return loc in self._reachable
