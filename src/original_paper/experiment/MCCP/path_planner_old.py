import heapq
from typing import List, Tuple, Optional, Dict
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

class CongestionAwareAStar:
    def __init__(self, grid, predictor,
                 move_cost: float = 1.0,
                 congestion_weight: float = 5.0,
                 prediction_window: int = 1):
        self.grid = grid
        self.predictor = predictor
        self.move_cost = move_cost
        self.congestion_weight = congestion_weight
        self.prediction_window = prediction_window

    def _congestion_cost(self, x: int, y: int, t: int) -> float:
        total = 0.0
        for k in range(self.prediction_window):
            total += self.predictor.get_density_at(t + k, x, y)
        avg = total / self.prediction_window
        return self.congestion_weight * avg

    def plan(self, agv_id, start: Tuple[int, int], goal: Tuple[int, int],
             start_time: int = 0, time_limit: int = 300,
             occupied: Dict[Tuple[int, int, int], str] = None) -> Optional[List[Tuple[int, int]]]:
        # print(start)
        # print(goal)
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
                    if occupied[(t, nx, ny)] == occupied[(nt, x, y)] and agv_id != occupied[(t, nx, ny)]:
                        continue

                move = self.move_cost
                congestion = self._congestion_cost(nx, ny, nt)
                # print(congestion)
                tentative_g = g_score[(x,y,t)] + move + congestion
                # tentative_g = g_score[(x, y, t)] + move
                #
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    h = manhattan_distance((nx, ny), goal)
                    f = tentative_g + h
                    heapq.heappush(open_set, (f, neighbor, path + [(nx, ny)]))

        return None