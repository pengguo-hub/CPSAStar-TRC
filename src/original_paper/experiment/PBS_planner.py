import heapq
import copy
from typing import Dict, List, Tuple, Optional, Set


class PBSPlanner:
    """
    Priority-Based Search (PBS) 实现 - 严格对应论文 Algorithm 2
    (Ma et al., AAAI 2019: "Searching with Consistent Prioritization for MAPF")

    关键设计决策:
    1. 高层: 深度优先搜索 (STACK, DFS) — 不是 best-first/heap
    2. 无约束列表: PBS 不在节点中存 constraints，完全靠优先级关系让低优先级 AGV 避让
    3. UpdatePlan: 拓扑排序后依次重规划受影响的所有 AGV
    4. 低层: 时空 A*，等待以"重复当前位置"表示在路径中
    5. 超时/迭代上限时: 返回部分成功子集，不视为全局失败
    """

    def __init__(self, grid, agv_info, max_iter=5000, time_limit=60.0):
        self.grid = grid
        self.agv_info = agv_info
        self.max_iter = max_iter          # 高层节点展开上限
        self.time_limit = time_limit      # 秒，高层搜索总时间上限

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def batch_plan(self, parsed_tasks, reset=True):
        """
        批量规划多个 AGV，每个任务路径为 agv_position → source → destination。
        返回: {agv_id: [(x,y), (x,y), ...], ...}
        超时或迭代上限时返回**已无冲突的最大子集**，不返回全零。
        """
        import time as _time
        self._start_time = _time.time()
        self._time_limit = self.time_limit

        # 解析任务
        agv_tasks = {}
        for agv_id, task in parsed_tasks.items():
            agv_tasks[agv_id] = {
                'start':  tuple(task['agv_position']),
                'pickup': tuple(task['source']),
                'goal':   tuple(task['destination']),
            }

        return self._pbs_search(agv_tasks)

    # ------------------------------------------------------------------
    # 高层 PBS 搜索 (Algorithm 2)
    # ------------------------------------------------------------------

    def _pbs_search(self, agv_tasks):
        import time as _time

        # ── 根节点初始化 ──────────────────────────────────────────────
        # priority_order[j] = set of i  表示 i ≺ j (i 比 j 优先级高)
        root = PTNode(priority_order={}, paths={})

        # 按任意顺序为每个 AGV 做初始规划 (UpdatePlan with empty ordering)
        all_agv_ids = list(agv_tasks.keys())
        failed_init = []
        for agv_id in all_agv_ids:
            ok = self._update_plan_single(root, agv_id, agv_tasks)
            if not ok:
                print(f"[PBS] 根节点: AGV {agv_id} 初始规划失败，跳过")
                failed_init.append(agv_id)
                # 不把它加进 paths，保持部分成功
                # 论文在空偏序下 always succeeds, 但实际地图可能出现孤立点
                continue

        if not root.paths:
            print("[PBS] 所有 AGV 初始规划失败")
            return {}

        # ── 检查是否已无冲突 ──────────────────────────────────────────
        conflicts = self._detect_conflicts(root.paths)
        if not conflicts:
            return root.paths

        # ── 深度优先 STACK (论文: insert in non-increasing order of cost) ─
        # 论文 Line 8: STACK ← {Root}
        # 论文 Line 23: insert new nodes into STACK in non-increasing order of cost
        #   → 代价小的排在栈顶 (先展开)
        stack = [root]          # 简单列表，append/pop (-1) 即 DFS
        iteration = 0
        best_partial = root     # 记录最优部分解，供超时时使用

        while stack and iteration < self.max_iter:
            # 时间检查
            if _time.time() - self._start_time > self._time_limit:
                # print(f"[PBS] 达到时间上限 {self._time_limit}s，返回部分解")
                break

            iteration += 1

            # 论文 Line 10: N ← top node in STACK (DFS)
            current = stack.pop()

            # 论文 Line 12-13
            conflicts = self._detect_conflicts(current.paths)
            if not conflicts:
                # print(f"[PBS] 找到无冲突解，迭代次数: {iteration}")
                return current.paths

            # 更新最优部分解（路径数最多/总代价最小）
            if len(current.paths) > len(best_partial.paths):
                best_partial = current
            elif (len(current.paths) == len(best_partial.paths) and
                  current.soc() < best_partial.soc()):
                best_partial = current

            # 论文 Line 14: C ← first collision
            conflict = conflicts[0]
            agv_i, agv_j = conflict['agents']

            # 论文 Line 15-23: 两个子节点，对应 (j≺i) 和 (i≺j)
            # 按代价从大到小推入栈 → 代价小的后推 → 先弹出 (DFS 倾向低代价)
            children = []
            for (hi, lo) in [(agv_j, agv_i), (agv_i, agv_j)]:
                # hi 优先级高于 lo，即 hi ≺ lo
                child = PTNode(
                    priority_order=copy.deepcopy(current.priority_order),
                    paths=copy.deepcopy(current.paths)
                )

                # 添加有序对: hi ≺ lo
                child.priority_order.setdefault(lo, set()).add(hi)

                # 传递闭包
                child.priority_order = self._transitive_closure(child.priority_order)

                # 检测环（两个 AGV 互为更高优先级）
                if self._has_cycle(child.priority_order):
                    continue

                # 论文 Line 20: success ← UpdatePlan(N', a_i)
                # UpdatePlan 对 lo 及所有低于 lo 的 AGV 做拓扑序重规划
                success = self._update_plan(child, lo, agv_tasks)
                if not success:
                    continue

                children.append(child)

            # 按代价从大到小推入栈（代价小的后推，先被 pop）
            children.sort(key=lambda n: n.soc(), reverse=True)
            for child in children:
                stack.append(child)

        # print(f"[PBS] 达到迭代上限 {iteration}，提取无冲突子集")
        return self._extract_conflict_free_subset(best_partial.paths)

    # ------------------------------------------------------------------
    # UpdatePlan (Algorithm 2, Lines 25-32)
    # ------------------------------------------------------------------

    def _update_plan_single(self, node, agv_id, agv_tasks):
        """
        为单个 agv_id 做低层规划（用于根节点初始化）。
        """
        if agv_id not in agv_tasks:
            return False
        task = agv_tasks[agv_id]

        # 分段规划: start→pickup, pickup→goal
        path = self._plan_two_segments(
            agv_id=agv_id,
            start=task['start'],
            pickup=task['pickup'],
            goal=task['goal'],
            priority_order=node.priority_order,
            existing_paths=node.paths
        )
        if path is None:
            return False
        node.paths[agv_id] = path
        return True

    def _update_plan(self, node, changed_agv, agv_tasks):
        """
        论文 UpdatePlan(N, a_i):
        1. 拓扑排序: {changed_agv} ∪ {j | changed_agv ≺ j}
        2. 对列表中每个 j，若 j == changed_agv 或 j 与某高优先级 AGV 冲突，则重规划 j
        返回 False 表示规划失败（子节点剪枝）。
        """
        # 找出所有优先级 ≤ changed_agv 的 AGV（changed_agv 本身 + 它的下游）
        replan_set = self._get_lower_or_equal(changed_agv, node.priority_order)

        # 拓扑排序 replan_set（按优先级从高到低）
        sorted_agvs = self._topological_sort(replan_set, node.priority_order)

        for agv_id in sorted_agvs:
            if agv_id not in agv_tasks:
                continue

            # 论文 Line 28: 若 j == i 或 j 与某高优先级 ak 冲突，则重规划
            if agv_id == changed_agv or self._collides_with_higher(agv_id, node):
                task = agv_tasks[agv_id]
                path = self._plan_two_segments(
                    agv_id=agv_id,
                    start=task['start'],
                    pickup=task['pickup'],
                    goal=task['goal'],
                    priority_order=node.priority_order,
                    existing_paths=node.paths
                )
                if path is None:
                    return False
                node.paths[agv_id] = path

        return True

    def _get_lower_or_equal(self, agv_id, priority_order):
        """
        返回 agv_id 本身 + 所有直接或间接低于 agv_id 的 AGV。
        priority_order[j] = set of i (i 比 j 优先级高)
        → 找出所有 j 满足 agv_id ∈ priority_order[j]（agv_id 是 j 的上游）
        """
        result = {agv_id}
        changed = True
        while changed:
            changed = False
            for j, higher_set in priority_order.items():
                if j not in result and result & higher_set:
                    result.add(j)
                    changed = True
        return result

    def _topological_sort(self, agv_set, priority_order):
        """
        对 agv_set 内的 AGV 按优先级做拓扑排序（高优先级靠前）。
        priority_order[j] = set of i 表示 i ≺ j
        """
        # Kahn's algorithm
        in_degree = {a: 0 for a in agv_set}
        # 对 agv_set 内的边建图
        for j in agv_set:
            for i in priority_order.get(j, set()):
                if i in agv_set:
                    in_degree[j] += 1  # j 依赖 i，i 先排

        queue = [a for a in agv_set if in_degree[a] == 0]
        sorted_list = []
        while queue:
            # 优先取优先级最高的（即没有更高优先级依赖的那些）
            node = queue.pop(0)
            sorted_list.append(node)
            # 找出所有 j 满足 node ∈ priority_order[j]
            for j in agv_set:
                if node in priority_order.get(j, set()):
                    in_degree[j] -= 1
                    if in_degree[j] == 0:
                        queue.append(j)

        # 如果有环（不应该，已检测），把剩余的加上
        for a in agv_set:
            if a not in sorted_list:
                sorted_list.append(a)
        return sorted_list

    def _collides_with_higher(self, agv_id, node):
        """
        检查 agv_id 的当前路径是否与任何更高优先级 AGV 有冲突。
        """
        if agv_id not in node.paths:
            return True
        higher_agvs = node.priority_order.get(agv_id, set())
        sub_paths = {agv_id: node.paths[agv_id]}
        for hi in higher_agvs:
            if hi in node.paths:
                sub_paths[hi] = node.paths[hi]
        if len(sub_paths) < 2:
            return False
        conflicts = self._detect_conflicts(sub_paths)
        return any(agv_id in c['agents'] for c in conflicts)

    # ------------------------------------------------------------------
    # 分段低层规划
    # ------------------------------------------------------------------

    def _plan_two_segments(self, agv_id, start, pickup, goal,
                           priority_order, existing_paths):
        """
        分段规划: start→pickup + pickup→goal。
        等待以路径中重复当前位置表示。
        """
        # 构建高优先级 AGV 的时空预约表
        higher_agvs = priority_order.get(agv_id, set())
        reservations = self._build_reservations(higher_agvs, existing_paths)

        # 第1段: start → pickup（时间从 0 开始）
        seg1 = self._spacetime_astar(agv_id, start, pickup, 0, reservations)
        if seg1 is None:
            return None

        # 第2段: pickup → goal（时间从第1段结束时刻开始）
        t_offset = len(seg1) - 1  # 第1段最后一步的时刻
        seg2 = self._spacetime_astar(agv_id, pickup, goal, t_offset, reservations)
        if seg2 is None:
            return None

        # 拼接（去掉第2段的重复起点）
        return seg1 + seg2[1:]

    def _spacetime_astar(self, agv_id, start, goal, t_start, reservations):
        """
        时空 A*: 每步移动一格或原地等待（等待 = 路径中重复当前格）。
        t_start: 起始时间步（整数）。
        返回路径列表 [(x,y), ...] 或 None。
        """
        # open_heap: (f, g, pos, t)
        # g = 步数（含等待步），每步代价 1
        open_heap = []
        h0 = self._heuristic(start, goal)
        heapq.heappush(open_heap, (h0, 0, start, t_start))

        # g_score[(x, y, t)] = 到达该时空状态的最小 g
        g_score = {(start[0], start[1], t_start): 0}
        came_from = {}

        max_expanded = 50000
        expanded = 0

        while open_heap and expanded < max_expanded:
            expanded += 1
            f, g, pos, t = heapq.heappop(open_heap)

            # 目标检测
            if pos == goal:
                return self._reconstruct_path(came_from, (pos[0], pos[1], t))

            # 扩展: 4 方向移动 + 原地等待（5 种动作）
            neighbors = []
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = pos[0] + dx, pos[1] + dy
                if self._is_valid(nx, ny):
                    neighbors.append((nx, ny))
            # 等待
            neighbors.append(pos)

            nt = t + 1
            for npos in neighbors:
                # 节点冲突: 在时刻 nt 占用 npos
                if self._node_conflict(npos, nt, reservations):
                    continue
                # 边冲突: 与某高优先级 AGV 相向行驶
                # 即: 高优先级 AGV 在时刻 t 从 npos 走到 pos
                if self._edge_conflict(pos, npos, t, reservations):
                    continue

                new_g = g + 1
                state = (npos[0], npos[1], nt)
                if state in g_score and new_g >= g_score[state]:
                    continue

                g_score[state] = new_g
                came_from[state] = (pos[0], pos[1], t)
                h = self._heuristic(npos, goal)
                heapq.heappush(open_heap, (new_g + h, new_g, npos, nt))

        return None

    # ------------------------------------------------------------------
    # 时空预约表
    # ------------------------------------------------------------------

    def _build_reservations(self, higher_agvs, existing_paths):
        """
        为高优先级 AGV 构建时空预约表。
        reservations['nodes'][(x, y, t)] = True  → t 时刻 (x,y) 被占用
        reservations['edges'][(pos, npos, t)] = True → t 时刻从 pos 走到 npos

        注意: 每条路径最后一格在目标点永久停留，时间步从最后一步开始无限延伸。
        实现简化: 预约到合理的最大时间步。
        """
        reservations = {'nodes': {}, 'edges': {}}

        for agv_id in higher_agvs:
            if agv_id not in existing_paths:
                continue
            path = existing_paths[agv_id]
            for t, pos in enumerate(path):
                reservations['nodes'][(pos[0], pos[1], t)] = True
                if t < len(path) - 1:
                    npos = path[t + 1]
                    reservations['edges'][(pos, npos, t)] = True

            # 目标点永久占用（预约到足够远的时间步）
            # last_pos = path[-1]
            # last_t = len(path) - 1
            # for extra in range(1, 200):
            #     reservations['nodes'][(last_pos[0], last_pos[1], last_t + extra)] = True

        return reservations

    def _node_conflict(self, pos, t, reservations):
        """检测节点冲突"""
        return (pos[0], pos[1], t) in reservations['nodes']

    def _edge_conflict(self, from_pos, to_pos, t, reservations):
        """
        检测相向边冲突。
        当前 AGV 在时刻 t → t+1 从 from_pos 移动到 to_pos，
        若高优先级 AGV 在同一时刻 t → t+1 从 to_pos 移动到 from_pos，则冲突。
        即检查 edges[(to_pos, from_pos, t)] 是否存在。
        """
        return (to_pos, from_pos, t) in reservations['edges']

    # ------------------------------------------------------------------
    # 全局冲突检测 (用于高层)
    # ------------------------------------------------------------------

    def _detect_conflicts(self, paths):
        """
        检测所有路径之间的冲突（节点冲突 + 相向边冲突）。
        等待步: path[t] == path[t+1]，等待时不产生边，只占用节点。
        返回冲突列表，PBS 只用第一个冲突。
        """
        if len(paths) < 2:
            return []

        agv_ids = list(paths.keys())
        max_t = max(len(p) for p in paths.values())

        # 构建时空占用
        node_occ = {}   # (x, y, t) → [agv_id]
        edge_occ = {}   # (pos, npos, t) → [agv_id]

        for agv_id in agv_ids:
            path = paths[agv_id]
            for t, pos in enumerate(path):
                key = (pos[0], pos[1], t)
                node_occ.setdefault(key, []).append(agv_id)

                # 目标点之后视为停留
                if t < len(path) - 1:
                    npos = path[t + 1]
                    # 仅当实际移动时记录边（等待不记录边，避免误判相向冲突）
                    if npos != pos:
                        edge_occ.setdefault((pos, npos, t), []).append(agv_id)

            # # 路径结束后在目标点停留
            # last_pos = path[-1]
            # last_t = len(path) - 1
            # for extra_t in range(last_t + 1, max_t):
            #     key = (last_pos[0], last_pos[1], extra_t)
            #     node_occ.setdefault(key, []).append(agv_id)

        # 节点冲突检测
        for (x, y, t), agv_list in node_occ.items():
            if len(agv_list) > 1:
                return [{'type': 'node',
                         'agents': (agv_list[0], agv_list[1]),
                         'location': (x, y), 'time': t}]

        # 相向边冲突检测
        for (pos, npos, t), agv_list in edge_occ.items():
            reverse_key = (npos, pos, t)
            if reverse_key in edge_occ:
                reverse_list = edge_occ[reverse_key]
                return [{'type': 'edge',
                         'agents': (agv_list[0], reverse_list[0]),
                         'location': (pos, npos), 'time': t}]

        return []

    # ------------------------------------------------------------------
    # 超时后提取无冲突最大子集
    # ------------------------------------------------------------------

    def _extract_conflict_free_subset(self, paths):
        """
        从给定路径中逐步移除冲突 AGV，直到无冲突。
        策略: 每次移除冲突中代价（路径长度）较大的那个，保留更多完成的任务。
        """
        current = copy.deepcopy(paths)
        removed = []
        max_iter = len(paths) + 1

        for _ in range(max_iter):
            conflicts = self._detect_conflicts(current)
            if not conflicts:
                break
            c = conflicts[0]
            a0, a1 = c['agents']
            # 移除路径更长的（启发式：路径越长，等待越多，冲突贡献更大）
            len0 = len(current.get(a0, []))
            len1 = len(current.get(a1, []))
            to_remove = a0 if len0 >= len1 else a1
            if to_remove in current:
                del current[to_remove]
                removed.append(to_remove)
                # print(f"[PBS] 超时子集: 移除 AGV {to_remove}")

        # print(f"[PBS] 最终返回 {len(current)}/{len(paths)} 个 AGV 的路径")
        # if removed:
        #     print(f"[PBS] 被移除的 AGV: {removed}")
        return current

    # ------------------------------------------------------------------
    # 图工具
    # ------------------------------------------------------------------

    def _transitive_closure(self, priority_order):
        """计算优先级偏序的传递闭包"""
        closure = copy.deepcopy(priority_order)
        changed = True
        while changed:
            changed = False
            for j, higher_set in list(closure.items()):
                for i in list(higher_set):
                    if i in closure:
                        before = len(higher_set)
                        higher_set.update(closure[i])
                        if len(higher_set) > before:
                            changed = True
        return closure

    def _has_cycle(self, priority_order):
        """检测优先级图中是否有环（i ≺ j 且 j ≺ i）"""
        # 快速检查: 若 priority_order[j] 含 j 自身，则有环
        for j, higher_set in priority_order.items():
            if j in higher_set:
                return True
        return False

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _heuristic(self, pos, goal):
        return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])

    def _is_valid(self, x, y):
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


# ======================================================================

class PTNode:
    """优先级树节点"""
    __slots__ = ('priority_order', 'paths')

    def __init__(self, priority_order, paths):
        self.priority_order = priority_order   # {agv_id: set(higher_priority_agvs)}
        self.paths = paths                     # {agv_id: [(x,y), ...]}

    def soc(self):
        """Sum of Costs (路径长度之和)"""
        return sum(len(p) for p in self.paths.values())
