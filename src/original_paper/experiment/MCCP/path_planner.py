import heapq
from typing import List, Tuple, Optional, Dict
import sys
import os
pass  # Package imports replace process-wide import-path mutation.  # 添加项目根目录到搜索路径
from .utils import manhattan_distance
import numpy as np
class GridMap:
    def __init__(self, width=100, height=100,cell_size=1):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.grid = np.zeros((height, width), dtype=int) #0表示空地，1表示障碍物
        self.static_obstacles = set()  # 静态障碍物坐标集合
        self.dynamic_obstacles = set()  # 动态障碍物集合
        self.agv_positions = {}  # AGV当前位置字典，格式：{agv_id: (x,y)}

    def add_static_obstacle(self, x, y):
        """添加静态障碍物"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = 1
            self.static_obstacles.add((x, y))

    def remove_static_obstacle(self, x, y):
        """移除静态障碍物"""
        if (x, y) in self.static_obstacles:
            self.static_obstacles.remove((x, y))
            self.grid[y][x] = 0

    def add_dynamic_obstacle(self, x, y):
        """添加动态障碍物"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.dynamic_obstacles.add((x, y))

    def remove_dynamic_obstacle(self, x, y):
        """移除动态障碍物"""
        self.dynamic_obstacles.discard((x, y))

    def region_coordinate(self,x,y,value):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = value
            self.static_obstacles.add((x,y))

    def get_grid_matrix(self):
        """返回网格矩阵的深拷贝（NumPy数组）"""
        return self.grid.copy()  # 深拷贝NumPy数组

import numpy as np
from typing import Dict, List, Tuple, Union

class CongestionFieldManager:
    def __init__(self, predictor, sigma: float = 0.7, grid_size: Tuple[int, int] = (100, 100)):
        """
        :param predictor: 预测器对象，必须实现 get_density_at(t, x, y) 返回预测密度
        :param sigma: 预测密度的权重 (固定值，0~1)
        :param grid_size: (width, height)
        """
        self.predictor = predictor
        self.sigma = sigma
        self.width, self.height = grid_size
        self._obs_cache = None   # 存储当前时刻的观测密度场

    def update_observation(self, robot_paths: Dict[Union[str, int], List[Tuple[int, int]]], t: int):
        """
        根据所有机器人的路径数据，计算 t 时刻的观测密度场并缓存。
        """
        obs_field = self._compute_observation_density(robot_paths, t)
        self._obs_cache = obs_field

    def _compute_observation_density(self, robot_paths: Dict[Union[str, int], List[Tuple[int, int]]], t: int) -> np.ndarray:
        """计算观测密度场（归一化）"""
        obs_field = np.zeros((self.height, self.width), dtype=np.float32)
        robot_count = 0
        for path in robot_paths.values():
            if t < len(path):
                x, y = path[t]
                if 0 <= x < self.width and 0 <= y < self.height:
                    obs_field[y, x] += 1
                    robot_count += 1
        if robot_count > 0:
            obs_field /= robot_count
        return obs_field

    def get_density(self, t: int, x: int, y: int) -> float:
        """返回融合后的密度值：sigma * 预测 + (1-sigma) * 观测"""
        # print("******************")
        pred = self.predictor.get_density_at(t, x, y)
        # print(f"pred:{pred}")
        if self._obs_cache is not None:
            # print("++++++++++++++++++++++")
            h, w = self._obs_cache.shape
            y_min = max(0, y - 1)
            y_max = min(h, y + 2)  # 注意 Python 切片是左闭右开，所以 +2 才能包含 y+1
            x_min = max(0, x - 1)
            x_max = min(w, x + 2)
            obs = np.sum(self._obs_cache[y_min:y_max, x_min:x_max])
        else:
            obs = 0.0
        # print(f"obs:{obs}")
        return self.sigma * pred + (1 - self.sigma) * obs

class CongestionAwareAStar:
    def __init__(self, grid, congestion_manager,  # 改为 congestion_manager
                 move_cost: float = 1.0,
                 congestion_weight: float = 5.0,
                 prediction_window: int = 1):
        self.grid = grid
        self.congestion_manager = congestion_manager
        self.move_cost = move_cost
        self.congestion_weight = congestion_weight
        self.prediction_window = prediction_window

    def _congestion_cost(self, x: int, y: int, t: int) -> float:
        total = 0.0
        for k in range(self.prediction_window):
            total += self.congestion_manager.get_density(t + k, x, y)
        avg = total / self.prediction_window
        return self.congestion_weight * avg

    def plan(self, agv_id, start: Tuple[int, int], goal: Tuple[int, int],
             start_time: int = 0, time_limit: int = 300,
             occupied: Dict[Tuple[int, int, int], str] = None,robot_paths=None) -> Optional[List[Tuple[int, int]]]:
        # print(start)
        # print(goal)
        if robot_paths is not None:
            self.congestion_manager.update_observation(robot_paths, start_time)
        occupied = occupied or {}
        open_set = []
        start_node = (start[0], start[1], start_time)
        g_score = {start_node: 0}
        h0 = manhattan_distance(start, goal)
        f_score = {start_node: g_score[start_node] + h0}
        heapq.heappush(open_set, (f_score[start_node], start_node, [start]))
        visited = set()

        while open_set:
            _, current, path = heapq.heappop(open_set)
            x, y, t = current

            if (x, y) == goal:
                return path

            if (x, y, t) in visited:
                continue
            visited.add((x, y, t))

            if t >= time_limit:
                continue

            for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                nx, ny = x + dx, y + dy
                # print(nx, ny)

                if not (0 <= nx < self.grid.width and 0 <= ny < self.grid.height):
                    continue
                if (nx, ny) in self.grid.static_obstacles:
                    # print(nx, ny)
                    continue
                nt = t + 1
                neighbor = (nx, ny, nt)

                if (nt, nx, ny) in occupied:
                    continue
                if (t, nx, ny) in occupied and (nt, x, y) in occupied:
                    if agv_id!=occupied[(t, nx, ny)] and occupied[(t, nx, ny)] == occupied[(nt, x, y)]:
                        continue

                move = self.move_cost
                congestion = self._congestion_cost(nx, ny, nt)
                # print(congestion)
                tentative_g = g_score[(x,y,t)] + move + congestion
                # tentative_g = g_score[(x, y, t)] + move

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    h = manhattan_distance((nx, ny), goal)
                    f = tentative_g + h
                    heapq.heappush(open_set, (f, neighbor, path + [(nx, ny)]))

        return None