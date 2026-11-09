import heapq
import copy
import time
from typing import Dict, List, Tuple, Optional


class CBSPlanner:
    """
    Conflict-Based Search (CBS)
    修复点:
    1. 增加 wait action
    2. 分段路径时间步连续
    3. AGV到达destination后消失
    4. max_iterations + max_time 双重限制
    5. 低层A*使用 CAT (冲突避免表) 进行 tie-breaking
    """

    def __init__(self, grid, agv_info, max_iters, time_limit):
        self.grid = grid
        self.agv_info = agv_info
        self.max_iters = max_iters
        self.time_limit = time_limit
        self.dist_cache = {}
        self.constraint_tree = []
        self.best_solution = None
        self.best_soc = float('inf')

    def _precompute_distances(self, goal):
        """BFS 计算地图上所有格子到 goal 的最短步数"""
        from collections import deque
        width, height = self.grid.width, self.grid.height
        dist = [[float('inf')] * width for _ in range(height)]
        q = deque()
        gx, gy = goal
        dist[gy][gx] = 0
        q.append((gx, gy))
        while q:
            x, y = q.popleft()
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height and self.grid.grid[ny][nx] == 0:
                    if dist[ny][nx] == float('inf'):
                        dist[ny][nx] = dist[y][x] + 1
                        q.append((nx, ny))
        return dist

    def _build_cat(self, paths, exclude_agv_id):
        """
        构建冲突避免表 (CAT - Conflict Avoidance Table)
        论文 Section 4.3: 存储所有其他 agent 的时空占用位置
        用于低层 A* 的 tie-breaking, 优先选择冲突数最少的路径

        返回: set of (x, y, t) — 其他 agent 占用的时空格子
        """
        cat = set()
        for agv_id, path in paths.items():
            if agv_id == exclude_agv_id:
                continue
            for t, pos in enumerate(path):
                cat.add((pos[0], pos[1], t))
        return cat

    def batch_plan(self, parsed_tasks, reset=True):
        """
        统一接口: 批量规划多个AGV
        参数:
            parsed_tasks: {agv_id: {'agv_position':..., 'source':..., 'destination':...}}
            max_iterations: 最大CBS高层迭代次数
            max_time: 最大规划时间(秒)
        返回: {agv_id: [(x1,y1), (x2,y2), ...], ...}
              只包含规划成功且无冲突的AGV
        """
        max_iterations = self.max_iters
        max_time = self.time_limit
        if reset:
            self.constraint_tree = []
            self.best_solution = None
            self.best_soc = float('inf')

        agv_tasks = {}
        goals_to_precompute = set()
        for agv_id, task in parsed_tasks.items():
            agv_tasks[agv_id] = {
                'start': tuple(task['agv_position']),
                'pickup': tuple(task['source']),
                'goal': tuple(task['destination']),
            }
            goals_to_precompute.add(tuple(task['source']))
            goals_to_precompute.add(tuple(task['destination']))

        for g in goals_to_precompute:
            if g not in self.dist_cache:
                self.dist_cache[g] = self._precompute_distances(g)

        paths = self._cbs_search(agv_tasks, max_iterations=max_iterations, max_time=max_time)
        return paths

    def _cbs_search(self, agv_tasks, max_iterations=10000, max_time=30.0):
        """CBS高层搜索"""
        start_time = time.time()

        root_node = CTNode(constraints={}, paths={}, soc=0)
        failed_agvs = []

        for agv_id, task in agv_tasks.items():
            root_node.constraints[agv_id] = []

            # 第1段: agv_position → source  (无 CAT, 根节点路径为空)
            path_seg1 = self._plan_single_agent(
                agv_id=agv_id,
                start=task['start'],
                goal=task['pickup'],
                constraints=root_node.constraints[agv_id],
                start_time=0,
                cat=self._build_cat(root_node.paths, agv_id)
            )
            if path_seg1 is None:
                # print(f"[CBS] 根节点: AGV {agv_id} 第1段路径失败 (start→pickup)")
                failed_agvs.append(agv_id)
                continue

            # 第2段: source → destination  (时间接续第1段)
            seg1_end_time = len(path_seg1) - 1
            path_seg2 = self._plan_single_agent(
                agv_id=agv_id,
                start=task['pickup'],
                goal=task['goal'],
                constraints=root_node.constraints[agv_id],
                start_time=seg1_end_time,
                cat=self._build_cat(root_node.paths, agv_id)
            )
            if path_seg2 is None:
                # print(f"[CBS] 根节点: AGV {agv_id} 第2段路径失败 (pickup→goal)")
                failed_agvs.append(agv_id)
                continue

            full_path = path_seg1 + path_seg2[1:]
            root_node.paths[agv_id] = full_path
            root_node.soc += len(full_path)

        if not root_node.paths:
            # print("[CBS] 所有AGV规划失败")
            return {}

        # if failed_agvs:
            # print(f"[CBS] 部分AGV初始规划失败: {failed_agvs}")

        conflict = self._detect_first_conflict(root_node.paths, agv_tasks)
        if conflict is None:
            # print("[CBS] 根节点无冲突, 直接返回")
            return root_node.paths

        heapq.heappush(self.constraint_tree, (root_node.soc, 0, root_node))
        node_id = 1
        iteration = 0

        while self.constraint_tree and iteration < max_iterations:
            elapsed = time.time() - start_time
            if elapsed >= max_time:
                # print(f"[CBS] 达到时间限制 {max_time}s (已用 {elapsed:.2f}s), 迭代 {iteration} 次")
                break

            iteration += 1
            _, _, current_node = heapq.heappop(self.constraint_tree)

            conflict = self._detect_first_conflict(current_node.paths, agv_tasks)
            if conflict is None:
                elapsed = time.time() - start_time
                # print(f"[CBS] 成功找到完整解, 迭代 {iteration} 次, 耗时 {elapsed:.2f}s, SOC: {current_node.soc}")
                return current_node.paths

            agv_i, agv_j = conflict['agents']

            for constrained_agv in [agv_i, agv_j]:
                if constrained_agv not in agv_tasks:
                    continue

                child_node = CTNode(
                    constraints=copy.deepcopy(current_node.constraints),
                    paths=copy.deepcopy(current_node.paths),
                    soc=0
                )

                new_constraint = self._create_constraint(conflict, constrained_agv)
                child_node.constraints[constrained_agv].append(new_constraint)

                task = agv_tasks[constrained_agv]

                # 构建 CAT: 使用 child_node 中其他 agent 的路径
                cat = self._build_cat(child_node.paths, constrained_agv)

                # 重规划第1段 (带 CAT)
                path_seg1 = self._plan_single_agent(
                    agv_id=constrained_agv,
                    start=task['start'],
                    goal=task['pickup'],
                    constraints=child_node.constraints[constrained_agv],
                    start_time=0,
                    cat=cat
                )
                if path_seg1 is None:
                    continue

                # 重规划第2段 (带 CAT, 时间接续)
                seg1_end_time = len(path_seg1) - 1
                path_seg2 = self._plan_single_agent(
                    agv_id=constrained_agv,
                    start=task['pickup'],
                    goal=task['goal'],
                    constraints=child_node.constraints[constrained_agv],
                    start_time=seg1_end_time,
                    cat=cat
                )
                if path_seg2 is None:
                    continue

                full_path = path_seg1 + path_seg2[1:]
                child_node.paths[constrained_agv] = full_path
                child_node.soc = sum(len(p) for p in child_node.paths.values())

                heapq.heappush(self.constraint_tree, (child_node.soc, node_id, child_node))
                node_id += 1

        # 达到限制, 提取无冲突子集
        elapsed = time.time() - start_time
        # print(f"[CBS] 达到限制 (迭代 {iteration} 次, 耗时 {elapsed:.2f}s), 提取无冲突子集")

        if self.constraint_tree:
            _, _, best_node = min(self.constraint_tree, key=lambda x: x[0])
            return self._extract_conflict_free_subset(best_node.paths, agv_tasks)
        else:
            return self._extract_conflict_free_subset(root_node.paths, agv_tasks)

    def _extract_conflict_free_subset(self, paths, agv_tasks):
        """从给定路径中提取最大的无冲突子集"""
        if not paths:
            return {}

        current_paths = copy.deepcopy(paths)
        removed_agvs = []

        for _ in range(len(agv_tasks) + 1):
            conflict = self._detect_first_conflict(current_paths, agv_tasks)
            if conflict is None:
                # print(f"[CBS] 无冲突子集: {len(current_paths)}/{len(paths)} 个AGV成功")
                # if removed_agvs:
                #     print(f"[CBS] 未能规划的AGV: {removed_agvs}")
                return current_paths

            agv_a, agv_b = conflict['agents']
            len_a = len(current_paths.get(agv_a, []))
            len_b = len(current_paths.get(agv_b, []))
            agv_to_remove = agv_a if len_a >= len_b else agv_b

            if agv_to_remove in current_paths:
                del current_paths[agv_to_remove]
                removed_agvs.append(agv_to_remove)

        return current_paths

    def _plan_single_agent(self, agv_id, start, goal, constraints, start_time=0, cat=None):
        """
        单智能体时空A*规划
        - 支持 wait action
        - 时间步连续 (由 start_time 控制)
        - 使用 CAT 进行 tie-breaking (论文 Section 4.3)
          f 值相同时, 优先选择与其他 agent 冲突次数 (num_conflicts) 更少的节点

        open_heap 元素: (f, num_conflicts, g, pos, abs_time)
          num_conflicts: 该状态路径上与 CAT 的冲突数, f 相同时作为第二排序键
        """
        if cat is None:
            cat = set()

        dist_map = self.dist_cache.get(goal)
        if dist_map is None:
            def heuristic(pos):
                return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])
        else:
            def heuristic(pos):
                h = dist_map[pos[1]][pos[0]]
                return h if h != float('inf') else abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])

        h0 = heuristic(start)
        # 计算起始点的 CAT 冲突数
        init_conflicts = 1 if (start[0], start[1], start_time) in cat else 0

        # heap: (f, num_conflicts, g, pos, abs_time)
        open_heap = []
        heapq.heappush(open_heap, (h0, init_conflicts, 0, start, start_time))

        # g_score: (x, y, abs_time) -> g
        g_score = {(start[0], start[1], start_time): 0}
        # conflicts_score: (x, y, abs_time) -> num_conflicts
        conflicts_score = {(start[0], start[1], start_time): init_conflicts}
        came_from = {}

        max_expanded = 10000
        expanded_count = 0
        max_abs_time = start_time + self.grid.width * self.grid.height * 2 + 50

        while open_heap and expanded_count < max_expanded:
            expanded_count += 1
            f, num_conflicts, g, current, cur_t = heapq.heappop(open_heap)

            if current == goal:
                return self._reconstruct_path(came_from, (current[0], current[1], cur_t))

            if cur_t >= max_abs_time:
                continue

            # 检查是否已被更优解覆盖
            cur_state = (current[0], current[1], cur_t)
            if g > g_score.get(cur_state, float('inf')):
                continue

            next_t = cur_t + 1

            # 移动方向 + wait action
            neighbors = [(current[0] + dx, current[1] + dy) for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]]
            neighbors.append(current)  # wait

            for npos in neighbors:
                nx, ny = npos

                if npos != current:
                    if not self._is_valid_neighbor(npos):
                        continue
                    if self._violates_edge_constraint(current, npos, cur_t, constraints):
                        continue

                if self._violates_node_constraint(npos, next_t, constraints):
                    continue

                state = (nx, ny, next_t)
                tentative_g = g + 1

                # CAT: 统计到达 npos 在 next_t 时是否与其他 agent 冲突
                # num_conflicts 累积整条路径上的冲突数 (用于 tie-breaking)
                new_conflicts = num_conflicts + (1 if (nx, ny, next_t) in cat else 0)

                old_g = g_score.get(state, float('inf'))
                old_conflicts = conflicts_score.get(state, float('inf'))

                # 更新条件: g 更小, 或 g 相同但冲突更少 (tie-breaking)
                if tentative_g < old_g or (tentative_g == old_g and new_conflicts < old_conflicts):
                    g_score[state] = tentative_g
                    conflicts_score[state] = new_conflicts
                    came_from[state] = (current[0], current[1], cur_t)

                    h_val = heuristic(npos)
                    f_val = tentative_g + h_val
                    heapq.heappush(open_heap, (f_val, new_conflicts, tentative_g, npos, next_t))

        return None

    def _detect_first_conflict(self, paths, agv_tasks):
        """
        检测第一个冲突 (顶点冲突 + 边冲突)
        AGV到达destination后消失, 不再占用格子
        """
        agv_ids = list(paths.keys())
        occupancy = {}
        edges = {}

        for agv_id in agv_ids:
            path = paths[agv_id]
            goal = agv_tasks[agv_id]['goal']

            for i, pos in enumerate(path):
                t = i
                # 到达destination的最后一步: AGV消失
                if pos == goal and i == len(path) - 1:
                    break

                key = (pos[0], pos[1], t)
                if key not in occupancy:
                    occupancy[key] = []
                occupancy[key].append(agv_id)

                if i < len(path) - 1:
                    next_pos = path[i + 1]
                    if next_pos != pos:  # 移动才记录边
                        edge_key = (pos, next_pos, t)
                        if edge_key not in edges:
                            edges[edge_key] = []
                        edges[edge_key].append(agv_id)

        # 顶点冲突
        for (x, y, t), agv_list in occupancy.items():
            if len(agv_list) > 1:
                return {
                    'type': 'node',
                    'agents': (agv_list[0], agv_list[1]),
                    'location': (x, y),
                    'time': t
                }

        # 边冲突 (对向穿越)
        for (pos1, pos2, t), agv_list in edges.items():
            reverse_key = (pos2, pos1, t)
            if reverse_key in edges:
                return {
                    'type': 'edge',
                    'agents': (agv_list[0], edges[reverse_key][0]),
                    'location': (pos1, pos2),
                    'time': t
                }

        return None

    def _violates_node_constraint(self, pos, time, constraints):
        for c in constraints:
            if c['type'] == 'node' and c['location'] == pos and c['time'] == time:
                return True
        return False

    def _violates_edge_constraint(self, from_pos, to_pos, time, constraints):
        for c in constraints:
            if c['type'] == 'edge' and c['location'] == (from_pos, to_pos) and c['time'] == time:
                return True
        return False

    def _create_constraint(self, conflict, agv_id):
        if conflict['type'] == 'node':
            return {'type': 'node', 'location': conflict['location'], 'time': conflict['time']}
        elif conflict['type'] == 'edge':
            agents = conflict['agents']
            location = conflict['location']
            edge = location if agv_id == agents[0] else (location[1], location[0])
            return {'type': 'edge', 'location': edge, 'time': conflict['time']}

    def _is_valid_neighbor(self, pos):
        x, y = pos
        return (0 <= x < self.grid.width and
                0 <= y < self.grid.height and
                self.grid.grid[y][x] == 0)

    def _reconstruct_path(self, came_from, final_state):
        path = []
        state = final_state
        while True:
            x, y, t = state
            path.append((x, y))
            if state not in came_from:
                break
            state = came_from[state]
        return path[::-1]


class CTNode:
    def __init__(self, constraints, paths, soc):
        self.constraints = constraints
        self.paths = paths
        self.soc = soc

    def __lt__(self, other):
        return self.soc < other.soc
