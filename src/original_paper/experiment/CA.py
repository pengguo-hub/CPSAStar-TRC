"""
Cooperative A* (CA*) — 完整复现
论文: Silver, D. (2005). Cooperative Pathfinding. AIIDE-2005.
算法: Cooperative A* (CA*) — 时空 A* + Reservation Table
      解决 Vertex Conflict (点冲突) 和 Edge Conflict (边冲突)
"""

import heapq
import math
import numpy as np
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ============================================================
# GridMap  (与原代码完全一致，供 test_congestion_base.py import)
# ============================================================

class GridMap:
    def __init__(self, width=100, height=100, cellsize=1):
        self.width = width
        self.height = height
        self.cellsize = cellsize
        self.grid = np.zeros((height, width), dtype=int)
        self.static_obstacles: set = set()
        self.dynamic_obstacles: set = set()

    def add_static_obstacle(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = 1
            self.static_obstacles.add((x, y))

    def remove_static_obstacle(self, x, y):
        if (x, y) in self.static_obstacles:
            self.static_obstacles.remove((x, y))
            self.grid[y][x] = 0

    def add_dynamic_obstacle(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.dynamic_obstacles.add((x, y))

    def remove_dynamic_obstacle(self, x, y):
        self.dynamic_obstacles.discard(x, y)

    def region_coordinate(self, x, y, value):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = value
            self.static_obstacles.add((x, y))

    def get_grid_matrix(self):
        return self.grid.copy()


# ============================================================
# TicketManager  (Reservation Table)
# 保留原有属性名：node_reservations, edge_reservations, agv_reservations
# ============================================================

class TicketManager:
    """
    稀疏 3D Reservation Table。
    node_reservations[(x,y,t)]     = {agv_id: priority}
    edge_reservations[(x1,y1,x2,y2,t)] = {agv_id: priority}
    agv_reservations[agv_id]       = set of keys
    """

    def __init__(self):
        self.node_reservations: Dict[Tuple, Dict[str, float]] = defaultdict(dict)
        self.edge_reservations: Dict[Tuple, Dict[str, float]] = defaultdict(dict)
        self.agv_reservations:  Dict[str, set] = defaultdict(set)

    # ---------- query ----------

    def is_node_conflict(self, node, t, agv_id, priority) -> bool:
        key = ((node[0], node[1]), t)
        return any(p >= priority for aid, p in self.node_reservations[key].items()
                   if aid != agv_id)

    def is_edge_conflict(self, x1, y1, x2, y2, t, agv_id, priority) -> bool:
        # 对向边冲突：检查 (x2,y2)->(x1,y1) 是否已被预留
        rev_key = (x2, y2, x1, y1, t)
        return any(p >= priority for aid, p in self.edge_reservations[rev_key].items()
                   if aid != agv_id)

    # ---------- reserve ----------

    def reserve(self, agv_id: str, reservations: list, priority: float) -> bool:
        for item in reservations:
            if len(item) == 2:  # node: ((x,y), t)
                node, t = item
                x, y = node
                if self.is_node_conflict((x, y), t, agv_id, priority):
                    return False
            else:  # edge: ('edge', x1,y1,x2,y2,t)
                _, x1, y1, x2, y2, t = item
                if self.is_edge_conflict(x1, y1, x2, y2, t, agv_id, priority):
                    return False
        for item in reservations:
            if len(item) == 2:
                node, t = item
                x, y = node
                key = ((x, y), t)
                self.node_reservations[key][agv_id] = priority
                self.agv_reservations[agv_id].add(('node', key))
            else:
                _, x1, y1, x2, y2, t = item
                key = (x1, y1, x2, y2, t)
                self.edge_reservations[key][agv_id] = priority
                self.agv_reservations[agv_id].add(('edge', key))
        return True

    def release_all(self, agv_id: str):
        for kind, key in list(self.agv_reservations.get(agv_id, [])):
            if kind == 'node':
                self.node_reservations[key].pop(agv_id, None)
                if not self.node_reservations[key]:
                    del self.node_reservations[key]
            else:
                self.edge_reservations[key].pop(agv_id, None)
                if not self.edge_reservations[key]:
                    del self.edge_reservations[key]
        self.agv_reservations.pop(agv_id, None)

    def get_all_reservations(self):
        return {
            'node_reservations': {k: dict(v) for k, v in self.node_reservations.items()},
            'edge_reservations': {k: dict(v) for k, v in self.edge_reservations.items()},
        }

# ============================================================
# CA* 核心：时空 A* 单 agent 搜索
# ============================================================

_MOVES = [(0, 1), (1, 0), (0, -1), (-1, 0), (0, 0)]   # 四方向 + 等待


def _heuristic(node: Tuple[int, int], goal: Tuple[int, int]) -> float:
    """曼哈顿距离启发式（CA* 论文基本启发式）"""
    # return abs(node[0] - goal[0]) + abs(node[1] - goal[1])
    dx, dy = goal[0] - node[0], goal[1] - node[1]
    distance_cost = (dx ** 2 + dy ** 2) ** 0.5
    return distance_cost


def _spacetime_astar(
    grid: GridMap,
    ticket_manager: TicketManager,
    agv_id: str,
    start: Tuple[int, int],
    goal: Tuple[int, int],
    start_time: float,
    priority: float,
    move_time: float = 1.0,
    max_wait: int = 0,
    max_time: float = 500.0,
    enable_turn_penalty=True,
) -> Tuple[Optional[List], Optional[List]]:
    """
    CA* 时空搜索。返回 (path, times) 或 (None, None)。
    path:  [(x,y), ...]
    times: [t, ...]
    """
    t0 = round(start_time, 1)

    # heap: (f, pos, time, wait_count)
    h0 = _heuristic(start, goal)
    g0 = 0.0
    f0 = g0 + h0
    start_pos = (start[0], start[1])
    open_heap = [(f0, start_pos, t0, 0)]

    g_score: Dict[Tuple, float] = {(start[0], start[1], t0): g0}
    came_from: Dict[Tuple, Optional[Tuple]] = {(start[0], start[1], t0): None}

    def get_prev_dir(state):
        prev = came_from.get(state)
        if prev is None:
            return None
        return (state[0] - prev[0], state[1] - prev[1])

    while open_heap:
        f, current_pos, t, wc = heapq.heappop(open_heap)
        x, y = current_pos
        current_time = t
        cur_state = (x, y, current_time)
        g = g_score.get(cur_state, math.inf)

        if (x, y) == goal:
            path, times = _reconstruct(came_from, cur_state)
            reservations = _build_reservations(path, times)
            if ticket_manager.reserve(agv_id, reservations, priority):
                return path, times
            return None, None

        for dx, dy in _MOVES:
            nx, ny = x + dx, y + dy
            is_wait = (dx == 0 and dy == 0)

            if not (0 <= nx < grid.width and 0 <= ny < grid.height):
                continue
            if grid.grid[ny][nx] != 0:
                continue

            arrival_t = round(t + move_time, 1)

            if arrival_t > max_time:
                continue

            new_wc = wc + 1 if is_wait else 0
            if new_wc > max_wait:
                continue

            # --- 冲突检查 (论文核心) ---
            if ticket_manager.is_node_conflict((nx, ny), arrival_t, agv_id, priority):
                continue
            if not is_wait and ticket_manager.is_edge_conflict(
                    x, y, nx, ny, t, agv_id, priority):
                continue

            nb_state = (nx, ny, arrival_t)
            new_g = g + (2 if is_wait else move_time)
            if enable_turn_penalty and not is_wait:
                prev_dir = get_prev_dir((x, y, t))
                if prev_dir is not None:
                    new_dir = (dx, dy)
                    if new_dir != prev_dir:
                        new_g += 0.5

            if new_g < g_score.get(nb_state, math.inf) - 1e-9:
                g_score[nb_state] = new_g
                came_from[nb_state] = cur_state
                h = _heuristic((nx, ny), goal)
                f_val = new_g + h
                neighbor_pos = (nx, ny)
                heapq.heappush(open_heap, (f_val, neighbor_pos, arrival_t, new_wc))

    return None, None


def _reconstruct(came_from, final_state):
    path, times = [], []
    state = final_state
    while state is not None:
        x, y, t = state
        path.append((x, y))
        times.append(t)
        state = came_from.get(state)
    path.reverse()
    times.reverse()
    return path, times


def _build_reservations(path, times):
    items = []
    for i, ((x, y), t) in enumerate(zip(path, times)):
        items.append(((x, y), t))                                   # node 改成 2 元素
        if i > 0 and path[i] != path[i - 1]:
            px, py = path[i - 1]
            items.append(('edge', px, py, x, y, times[i - 1]))     # edge 不变
    return items


# ============================================================
# 优先级排序（与原代码完全一致）
# ============================================================

_PRIORITY_MAP = {'emergency': 3, 'high': 2, 'normal': 1}


def _sort_agvs(agv_tasks: dict) -> Dict[str, float]:
    now = datetime.now()
    all_timeleft = []
    for agv_id, task in agv_tasks.items():
        constraints = task.get('constraints') or {}
        timelimit = constraints.get('timelimit') or constraints.get('time_limit')
        timeleft = None
        if timelimit:
            try:
                dl = datetime.strptime(timelimit, '%H:%M').replace(
                    year=now.year, month=now.month, day=now.day)
                timeleft = (dl - now).total_seconds() / 60.0
            except Exception:
                pass
        task['_timeleft'] = timeleft
        if timeleft is not None:
            all_timeleft.append(timeleft)

    max_tl = max(all_timeleft) if all_timeleft else 1.0
    scores = {}
    for agv_id, task in agv_tasks.items():
        constraints = task.get('constraints') or {}
        plevel = _PRIORITY_MAP.get(constraints.get('priority', 'normal'), 1)
        pnorm = plevel / 3.0
        tl = task.get('_timeleft')
        if tl is None:
            tnorm = 0.0
        elif tl < 0:
            urgency_factor = 2
            tnorm = 1 + (-tl) / max_tl * urgency_factor
        else:
            tnorm = 1 - (tl / max_tl)   # 线性，与原代码一致
        scores[agv_id] = 0.5 * pnorm + 0.5 * tnorm

    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))



# ============================================================
# IntegratedAGVPlanner  (对外主类，接口与原 Astarbase 完全兼容)
# ============================================================

class _DefaultWaypointGen:
    """默认 mock，外部可覆盖（test_new.py 和 test_congestion_base.py 都会注入）"""
    def llm_generate_waypoints(self, parsed_tasks):
        return parsed_tasks


class IntegratedAGVPlanner:
    """
    CA* (Cooperative A*) 规划器。
    完整复现 Silver 2005 论文。
    """

    def __init__(
        self,
        grid: GridMap,
        agv_info: dict = None,
        move_time: float = 1.0,
        max_wait: int = 0,
        max_time: float = 500.0,
    ):
        self.grid = grid
        self.agv_info = agv_info or {}
        self.move_time = move_time
        self.max_wait = max_wait
        self.max_time = max_time

        # 对外属性（保持原有命名）
        self.ticket_manager = TicketManager()
        self.agv_tasks: Dict[str, dict] = {}
        self.waypointgenerator = _DefaultWaypointGen()

    # --------------------------------------------------
    #  主入口
    # --------------------------------------------------

    def batch_plan(self, parsed_tasks: dict, reset: bool = True) -> Dict[str, list]:
        """
        一次性规划所有任务。

        参数:
            parsed_tasks: {agv_id: {task_id, agv_position, source, destination,
                                    waypoints, constraints}}
            reset: True = 清空 reservation table 重新规划
                   False = 在已有预留基础上继续规划（新任务追加）

        返回:
            {agv_id: [(x,y), ...]}  仅含成功规划的 AGV
        """
        if reset:
            self.ticket_manager = TicketManager()
            self.agv_tasks = {}

        # 若外部注入了 MockWaypointGen，用它"翻译"parsed_tasks
        # (test_new.py / test_congestion_base.py 会注入，直接返回 waypointsmap)
        waypointsmap = self.waypointgenerator.llm_generate_waypoints(parsed_tasks)
        if waypointsmap is None:
            waypointsmap = parsed_tasks

        # Step 1: 整理 agv_tasks
        for agv_id, info in waypointsmap.items():
            agv_pos = tuple(info.get('agv_position') or info.get('agv_pos') or (0, 0))
            source  = tuple(info.get('source')      or agv_pos)
            dest    = tuple(info.get('destination') or info.get('dest') or source)
            constraints = info.get('constraints') or {}
            self.agv_tasks[agv_id] = {
                'waypoints':    (agv_pos, source, dest),
                'agv_position': agv_pos,
                'source':       source,
                'destination':  dest,
                'constraints':  constraints,
                'path':         [],
                'times':        [],
                'status':       'pending',
            }

        # Step 2: 优先级排序
        sorted_agvs = _sort_agvs(self.agv_tasks)

        # Step 3: 按优先级逐一做 CA* 规划
        paths: Dict[str, list] = {}
        for agv_id in sorted_agvs:
            task = self.agv_tasks[agv_id]
            priority = sorted_agvs[agv_id]
            waypoints = task['waypoints']  # (agv_pos, source, destination)

            speed = 1.0
            if agv_id in self.agv_info:
                speed = self.agv_info[agv_id].get('speed', 1.0)
            mt = round(1.0 / speed, 4) if speed > 0 else self.move_time

            full_path, full_times = self._plan_full(
                agv_id, waypoints, priority, mt)

            if full_path is not None:
                task['path']   = full_path
                task['times']  = full_times
                task['status'] = 'planned'
                paths[agv_id]  = full_path

        return paths

    # --------------------------------------------------
    #  内部：分段规划后拼接
    # --------------------------------------------------

    def _plan_full(self, agv_id, waypoints, priority, move_time):
        full_path: List[Tuple] = []
        full_times: List[float] = []
        current_time = 0

        for i in range(len(waypoints) - 1):
            seg_start = tuple(waypoints[i])
            seg_end   = tuple(waypoints[i + 1])

            if seg_start == seg_end:
                if not full_path:
                    full_path.append(seg_start)
                    full_times.append(current_time)
                continue

            path, times = _spacetime_astar(
                grid=self.grid,
                ticket_manager=self.ticket_manager,
                agv_id=agv_id,
                start=seg_start,
                goal=seg_end,
                start_time=current_time,
                priority=priority,
                move_time=move_time,
                max_wait=self.max_wait,
                max_time=self.max_time,
                enable_turn_penalty=True
            )

            if path is None:
                self.ticket_manager.release_all(agv_id)
                return None, None

            if not full_path:
                full_path.extend(path)
                full_times.extend(times)
            else:
                full_path.extend(path[1:])
                full_times.extend(times[1:])

            current_time = times[-1]

        if not full_path:
            full_path  = [tuple(waypoints[0])]
            full_times = [0.0]

        return full_path, full_times


# ============================================================
# 简单自测
# ============================================================

if __name__ == '__main__':
    grid = GridMap(width=10, height=10)
    # 中间竖向障碍
    for yy in range(0, 4):
        grid.add_static_obstacle(4, yy)

    agvinfo = {
        'agv1': {'speed': 1.0},
        'agv2': {'speed': 1.0},
        'agv3': {'speed': 1.0},
    }

    planner = IntegratedAGVPlanner(grid=grid, agvinfo=agvinfo)

    parsed_tasks = {
        'agv1': {'task_id': 'T1', 'agv_position': (0,0), 'source': (2,0),
                 'destination': (8,0), 'constraints': {'priority': 'high'}},
        'agv2': {'task_id': 'T2', 'agv_position': (8,0), 'source': (6,0),
                 'destination': (0,0), 'constraints': {'priority': 'normal'}},
        'agv3': {'task_id': 'T3', 'agv_position': (0,5), 'source': (3,5),
                 'destination': (8,5), 'constraints': {'priority': 'emergency'}},
    }

    result = planner.batch_plan(parsed_tasks)
    print(f"成功规划: {len(result)}/{len(parsed_tasks)}")
    for aid, path in result.items():
        print(f"  {aid}: len={len(path)}, {path[0]}->{path[-1]}")

    # 验证零冲突
    max_t = max(len(p) for p in result.values())
    vc = 0
    for t in range(max_t):
        seen = {}
        for aid, path in result.items():
            if t < len(path):
                pos = path[t]
                if pos in seen:
                    vc += 1
                seen[pos] = aid
    ec = 0
    agv_list = list(result.items())
    for i in range(len(agv_list)):
        for j in range(i+1, len(agv_list)):
            ai, pi = agv_list[i]; aj, pj = agv_list[j]
            for t in range(min(len(pi), len(pj)) - 1):
                if pi[t] == pj[t+1] and pj[t] == pi[t+1]:
                    ec += 1
    print(f"Vertex conflicts: {vc}  Edge conflicts: {ec}")
    print("✓ 自测通过" if vc == 0 and ec == 0 else "✗ 有冲突！")

    # 验证 ticket_manager / agv_tasks 属性可访问（供 test_congestion_base.py）
    print(f"ticket_manager 节点预留数: {len(planner.ticket_manager.node_reservations)}")
    print(f"agv_tasks times 示例: {planner.agv_tasks['agv1']['times'][:3]}")
    print(f"conflict_updater.delta: {planner.conflict_updater.delta}")
