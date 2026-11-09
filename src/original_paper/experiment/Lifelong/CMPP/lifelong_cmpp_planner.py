"""
lifelong_cmpp_planner.py
完整复现论文 Section VI.C：CMPP 与 PIBT 在 Lifelong-MAPF 场景下的集成。

论文描述（Section VI.C Integration of CMPP with PIBT）：
  1. A-CMTS 在稀疏图 G 上为每个 agent 计算 CMPP 路径 πi=(πi[1],...,πi[Li])。
  2. 每步，agent i 的目标网格格子由路径决定：
       若 Li≥3，朝向 g(πi[2])（第二个稀疏顶点的代表格）；
       否则，直接朝向最终目标 gi。
  3. PIBT 执行一步无冲突移动。
  4. 移动后，用 f:V*→V 更新 agent 在稀疏图上的位置（取最近稀疏顶点）。
  5. 若 agent 到达当前稀疏路径的第一个顶点（πi[1]），
     将其从路径头部移除（remove visited vertex）。
  6. 剩余路径作为下一次 A-CMTS 的热启动初始解（Section V.E）。

任务分配逻辑：
  参考 path_planner_lifelong_new.py，在 idle AGV 和候选任务之间做
  "前 look_ahead 个任务 × 所有 idle AGV" 的贪心最优匹配
  （按 AGV 当前位置到任务 pickup 的 Manhattan 距离最小化）。
  每步执行完毕后检查完成/新分配，不是简单弹出队列首任务。
"""

import heapq
from collections import deque, defaultdict

from .cmpp_adapter import plan_with_cmpp
from .cmpp_graph import CMPPGraph
from .pibt_local_planner import PIBTLocalPlanner
import time


# ──────────────────────────────────────────────────────────────────────────────
# 主类
# ──────────────────────────────────────────────────────────────────────────────

class LifelongPlanner:
    """
    CMPP + A-CMTS + PIBT 终身规划器。

    Parameters
    ----------
    grid           : GridMap
    agv_info       : {agv_id: {'speed': float}}
    init_pos       : {agv_id: (x, y)}
    task_queue     : deque of ((pickup_x, pickup_y), (dropoff_x, dropoff_y))
    graph_step     : int  稀疏图采样步长（论文使用 2~4）
    omega          : float  A-CMTS 次优因子（论文推荐 1.3）
    time_limit     : float  每步 A-CMTS 时间上限（论文使用 1.0s）
    """

    def __init__(self, grid, agv_info, init_pos, task_queue,
                 graph_step=2, omega=1.3, time_limit=1.0):
        self.grid = grid
        self.agv_info = agv_info
        self.init_pos = dict(init_pos)
        self.task_queue = deque(task_queue)

        # A-CMTS 参数（论文推荐值）
        self.omega = omega
        self.time_limit = time_limit
        self.graph_step = graph_step

        # ── 构建稀疏图（全程不变）────────────────────────────────────────
        obstacles = self._extract_obstacles(grid)
        self.sparse_graph = CMPPGraph.from_grid(
            grid.width, grid.height, obstacles, step=graph_step
        )

        # ── PIBT 局部规划器 ───────────────────────────────────────────────
        self.pibt = PIBTLocalPlanner(grid.width, grid.height, obstacles)

        # ── 运行时状态（run_lifelong 调用前初始化）───────────────────────
        self.agv_positions = {}           # {agv_id: (x, y)} 当前网格坐标
        self.agv_tasks = {}               # {agv_id: task_dict}
        self.completed_tasks = []
        self.failed_tasks = []
        self.total_steps = 0

        # ── CMPP 稀疏路径状态 ─────────────────────────────────────────────
        # {agv_id: [sparse_vertex, ...]}  当前剩余稀疏路径（含当前位置映射的顶点）
        self.sparse_paths = {}
        # {agv_id: [sparse_vertex, ...]}  上一步计算的剩余路径（热启动用）
        self.prev_sparse_paths = {}
        self.total_assigned_tasks = 0
        self.total_assignment_time = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # 公共接口
    # ──────────────────────────────────────────────────────────────────────────

    def run_lifelong(self, max_cycles=500):
        """
        主循环：每个 cycle 对应论文中的一个仿真时间步（one grid step）。

        Returns
        -------
        (completed_tasks, failed_tasks)
        """
        # ── 重置状态 ──────────────────────────────────────────────────────
        self.agv_positions = dict(self.init_pos)
        self.agv_tasks = {}
        self.completed_tasks = []
        self.failed_tasks = []
        self.total_steps = 0
        self.sparse_paths = {}
        self.prev_sparse_paths = {}
        total_assignment_time = 0.0

        # 初始任务分配
        t_start = time.perf_counter()
        self._assign_new_tasks()
        total_assignment_time += time.perf_counter()-t_start

        for step in range(max_cycles):
            self.total_steps = step + 1

            if step % 10 == 0:
                finished   = len(self.completed_tasks)
                assigned   = finished + len(self.agv_tasks)
                throughput = finished / (step + 1) if step >= 0 else 0.0
                print(
                    f"[t={step:5d}] finished={finished} "
                    f"throughput={throughput:.4f} "
                    f"assigned={assigned}",
                    flush=True
                )

            # ── 1. CMPP 全局重规划（每步）────────────────────────────────
            self._replan_all_cmpp()

            # ── 2. PIBT 执行一步网格移动 ──────────────────────────────────
            self._pibt_step()

            # ── 3. 检查到达情况，更新稀疏路径，分配新任务 ──────────────────
            self._check_arrivals_and_reassign()

            t_start = time.perf_counter()
            self._assign_new_tasks()
            total_assignment_time += time.perf_counter() - t_start

            # ── 终止条件：无活跃任务且队列为空 ──────────────────────────
            if not self.agv_tasks and not self.task_queue:
                break

        # 超时的任务记为失败
        for agv_id, task in list(self.agv_tasks.items()):
            self.failed_tasks.append((agv_id, task))
            self._clean_agv(agv_id)

        self.total_assignment_time = total_assignment_time

        return self.completed_tasks, self.total_assigned_tasks

    def get_throughput(self):
        if self.total_steps == 0:
            return 0.0
        return len(self.completed_tasks) / self.total_steps

    # ──────────────────────────────────────────────────────────────────────────
    # 任务分配
    # ──────────────────────────────────────────────────────────────────────────

    def _assign_new_tasks(self):
        """
        在 idle AGV 和候选任务队列之间做贪心最优匹配。
        每次从「前 look_ahead 个任务 × 所有 idle AGV」的代价矩阵中
        反复选出代价最小的 (AGV, task) 对，直到 AGV 或任务耗尽。
        代价 = Manhattan(AGV.pos, task.pickup)。

        参考 path_planner_lifelong_new.py _assign_new_tasks。
        """
        busy_agvs = set(self.agv_tasks.keys())
        idle_agvs = [aid for aid in self.agv_info if aid not in busy_agvs]
        if not idle_agvs or not self.task_queue:
            return

        look_ahead = min(len(idle_agvs) * 3, len(self.task_queue))
        candidates = list(enumerate(self.task_queue))[:look_ahead]
        # candidates: [(原始下标, (pickup, dropoff)), ...]

        index_to_task = {i: t for i, t in candidates}
        remaining_agvs = list(idle_agvs)
        remaining_indices = [i for i, _ in candidates]
        matched = []   # [(agv_id, task_index)]

        while remaining_agvs and remaining_indices:
            best_agv, best_idx, best_cost = None, None, float('inf')
            for agv_id in remaining_agvs:
                pos = self.agv_positions[agv_id]
                for idx in remaining_indices:
                    pickup, _ = index_to_task[idx]
                    cost = abs(pos[0] - pickup[0]) + abs(pos[1] - pickup[1])
                    if cost < best_cost:
                        best_cost, best_agv, best_idx = cost, agv_id, idx
            if best_agv is None:
                break
            matched.append((best_agv, best_idx))
            remaining_agvs.remove(best_agv)
            remaining_indices.remove(best_idx)

        # 从 task_queue 中移除已匹配任务
        matched_indices = {idx for _, idx in matched}
        self.task_queue = deque(
            task for i, task in enumerate(self.task_queue)
            if i not in matched_indices
        )

        # 创建任务记录
        for agv_id, idx in matched:
            pickup, dropoff = index_to_task[idx]
            current_pos = self.agv_positions[agv_id]
            self._create_task(agv_id, current_pos, pickup, dropoff)
            self.total_assigned_tasks += 1

    def _create_task(self, agv_id, current_pos, pickup, dropoff):
        """
        初始化 AGV 任务。
        waypoints 一次性规划：cur → pickup → dropoff（三段），
        这样 CMPP 能看到完整路径，稀疏路径长度足够（Li≥3），引导有效。
        到达判断统一用稀疏顶点的代表格（vertex_to_grid），不用原始坐标。
        """
        cur_sparse  = self.sparse_graph.grid_to_vertex.get(current_pos, current_pos)
        pick_sparse = self.sparse_graph.grid_to_vertex.get(pickup, pickup)
        drop_sparse = self.sparse_graph.grid_to_vertex.get(dropoff, dropoff)

        # 三段 waypoints（去掉相邻重复）
        wps = [cur_sparse]
        if pick_sparse != cur_sparse:
            wps.append(pick_sparse)
        if drop_sparse != wps[-1]:
            wps.append(drop_sparse)

        # 到达判断用稀疏顶点的代表格（g映射）
        pick_goal_grid = self.sparse_graph.vertex_to_grid.get(pick_sparse, pick_sparse)
        drop_goal_grid = self.sparse_graph.vertex_to_grid.get(drop_sparse, drop_sparse)

        self.agv_tasks[agv_id] = {
            'pickup':          pickup,           # 原始坐标（记录用）
            'dropoff':         dropoff,          # 原始坐标（记录用）
            'pick_sparse':     pick_sparse,
            'drop_sparse':     drop_sparse,
            'pick_goal_grid':  pick_goal_grid,   # 到达判断用
            'drop_goal_grid':  drop_goal_grid,   # 到达判断用
            'phase':           'to_pickup',      # 'to_pickup' | 'to_dropoff'
            'waypoints_sparse': wps,
            'goal_sparse':     drop_sparse,      # 最终目标稀疏顶点
            'goal_grid':       drop_goal_grid,   # 最终目标网格格子
            'picked_up':       False,
        }
        self.sparse_paths.pop(agv_id, None)
        self.prev_sparse_paths.pop(agv_id, None)

    def _start_dropoff_phase(self, agv_id):
        """
        AGV 到达 pickup 稀疏代表格后，更新阶段标记。
        不重置稀疏路径——当前路径已包含 pickup→dropoff 段，继续用即可。
        只需截断路径头部（已到达 pick_sparse），让剩余路径从 pick_sparse 开始。
        """
        task = self.agv_tasks[agv_id]
        task['phase']     = 'to_dropoff'
        task['picked_up'] = True
        # goal 更新为 dropoff
        task['goal_sparse'] = task['drop_sparse']
        task['goal_grid']   = task['drop_goal_grid']
        # waypoints 截断到 dropoff 段
        drop_sparse = task['drop_sparse']
        cur_pos     = self.agv_positions[agv_id]
        cur_sparse  = self.sparse_graph.grid_to_vertex.get(cur_pos, cur_pos)
        task['waypoints_sparse'] = [cur_sparse, drop_sparse]
        # 稀疏路径：截断到 pick_sparse 之后的部分
        sp = self.sparse_paths.get(agv_id, [])
        pick_sparse = task['pick_sparse']
        if pick_sparse in sp:
            idx = sp.index(pick_sparse)
            sp = sp[idx:]           # 从 pick_sparse 开始的剩余路径
        self.sparse_paths[agv_id]      = sp
        self.prev_sparse_paths[agv_id] = sp

    # ──────────────────────────────────────────────────────────────────────────
    # CMPP 全局重规划（每步调用）
    # ──────────────────────────────────────────────────────────────────────────

    def _replan_all_cmpp(self):
        """
        对所有活跃 AGV 调用 A-CMTS 进行 CMPP 规划（每步）。
        使用上一步的剩余稀疏路径作为热启动初始解（论文 Section V.E）。
        """
        parsed_tasks = {}
        initial_paths_by_seg = {}

        for agv_id, task in self.agv_tasks.items():
            waypoints = task['waypoints_sparse']
            if len(waypoints) < 2:
                continue

            # 更新 waypoints 的起点为当前稀疏位置
            cur_pos = self.agv_positions[agv_id]
            cur_sparse = self.sparse_graph.grid_to_vertex.get(cur_pos, cur_pos)
            # waypoints[0] 应始终反映当前稀疏位置
            waypoints[0] = cur_sparse

            # 如果起终点相同，AGV 已经在目标处，跳过规划
            if waypoints[0] == waypoints[-1]:
                continue

            parsed_tasks[agv_id] = {'waypoints': list(waypoints)}

            # 热启动：上一步的剩余稀疏路径拆成分段
            if agv_id in self.prev_sparse_paths:
                prev = self.prev_sparse_paths[agv_id]
                if prev and prev[0] == cur_sparse:
                    # 将完整剩余路径拆分为 waypoints 间的分段
                    segs = self._split_path_by_waypoints(prev, waypoints)
                    for seg_idx, seg_path in enumerate(segs):
                        if seg_path and len(seg_path) >= 2:
                            seg_id = f"{agv_id}_seg{seg_idx}"
                            initial_paths_by_seg[seg_id] = seg_path

        if not parsed_tasks:
            return

        # 调用 CMPP 规划器（返回稀疏路径）
        new_paths = plan_with_cmpp(
            parsed_tasks=parsed_tasks,
            grid=self.grid,
            max_time_per_plan=self.time_limit,
            omega=self.omega,
            initial_paths=initial_paths_by_seg,
            graph=self.sparse_graph,
            return_sparse=True,
        )

        # 更新稀疏路径
        for agv_id in parsed_tasks:
            sparse_path = new_paths.get(agv_id)
            if sparse_path and len(sparse_path) >= 1:
                self.sparse_paths[agv_id] = sparse_path
            else:
                # 规划失败：BFS fallback
                task = self.agv_tasks[agv_id]
                cur_pos = self.agv_positions[agv_id]
                cur_sparse = self.sparse_graph.grid_to_vertex.get(cur_pos, cur_pos)
                goal_sparse = task['waypoints_sparse'][-1]
                fallback = self._bfs_sparse(cur_sparse, goal_sparse)
                if fallback:
                    self.sparse_paths[agv_id] = fallback
                # 若 BFS 也失败，维持旧路径（若有）

    # ──────────────────────────────────────────────────────────────────────────
    # PIBT 一步执行（论文 Section VI.C）
    # ──────────────────────────────────────────────────────────────────────────

    def _pibt_step(self):
        """
        论文描述：
          若 Li≥3，agent 朝向 g(πi[2])（稀疏路径第二个顶点的代表网格格子）；
          否则（Li<3），直接朝向最终目标 gi。
        PIBT 执行一步无冲突移动。
        移动后，用 f:V*→V 更新 agent 的稀疏位置（取最近稀疏顶点），
        并移除已到达的稀疏路径头部顶点。
        """
        goals_grid = {}   # {agv_id: (x, y)}  本步 PIBT 目标格子

        for agv_id, task in self.agv_tasks.items():
            sparse_path = self.sparse_paths.get(agv_id, [])
            Li = len(sparse_path)

            if Li >= 3:
                # πi[2]（0-indexed: sparse_path[1]）
                next_sparse_v = sparse_path[1]
                waypoint_grid = self.sparse_graph.vertex_to_grid.get(
                    next_sparse_v, next_sparse_v
                )
            else:
                # 直接朝向最终目标网格格子
                waypoint_grid = task['goal_grid']

            goals_grid[agv_id] = waypoint_grid

        if not goals_grid:
            return

        # 当前网格位置（只包含有 goals 的 AGV）
        positions = {aid: self.agv_positions[aid] for aid in goals_grid}

        # PIBT 一步
        next_positions = self.pibt.step(positions, goals_grid)

        # ── 更新网格位置，并处理稀疏路径头部移除 ────────────────────────
        for agv_id, new_pos in next_positions.items():
            self.agv_positions[agv_id] = new_pos

            sparse_path = self.sparse_paths.get(agv_id)
            if not sparse_path:
                continue

            # 当前网格位置 → 当前稀疏顶点（用 f:V*→V）
            cur_sparse = self.sparse_graph.grid_to_vertex.get(new_pos, new_pos)

            # 论文："remove visited vertex from each agent's CMPP path"
            # 移除已越过的所有头部顶点：
            # 只要路径头部顶点已经被「越过」（当前稀疏位置比头部更靠后），就移除。
            # 判断：当前稀疏位置等于路径中更后面的某个顶点 → 把前面的全部移除
            # 简单做法：找 cur_sparse 在路径中最后一次出现的位置，截断到那里
            if cur_sparse in sparse_path:
                idx = len(sparse_path) - 1 - sparse_path[::-1].index(cur_sparse)
                # 保留从 cur_sparse 开始的剩余路径
                sparse_path = sparse_path[idx:]
            # 若 cur_sparse 不在路径里（走偏了），保持路径不变，下次重规划会修正

            # 路径只剩终点自身时不再截断
            if len(sparse_path) == 0:
                task = self.agv_tasks.get(agv_id)
                if task:
                    sparse_path = [task['goal_sparse']]

            self.sparse_paths[agv_id] = sparse_path
            # 保存剩余路径作为下一步热启动
            self.prev_sparse_paths[agv_id] = sparse_path

    # ──────────────────────────────────────────────────────────────────────────
    # 到达检查和新任务分配
    # ──────────────────────────────────────────────────────────────────────────

    def _check_arrivals_and_reassign(self):
        """
        检查哪些 AGV 到达了当前阶段目标，更新任务状态或完成任务，
        然后为空闲 AGV 分配新任务。

        到达判断：用稀疏顶点的代表格（vertex_to_grid / pick_goal_grid），
        而不是原始 pickup/dropoff 坐标。
        原因：PIBT 引导目标是稀疏顶点代表格，AGV 最终停在代表格上。
        """
        arrived_pickup = []
        arrived_dropoff = []

        for agv_id, task in list(self.agv_tasks.items()):
            cur_pos    = self.agv_positions[agv_id]
            cur_sparse = self.sparse_graph.grid_to_vertex.get(cur_pos, cur_pos)
            phase      = task['phase']
            # 到达判断：用稀疏顶点层面判断（不要求网格精确匹配）
            if phase == 'to_pickup' and cur_sparse == task['pick_sparse']:
                arrived_pickup.append(agv_id)
            elif phase == 'to_dropoff' and cur_sparse == task['drop_sparse']:
                arrived_dropoff.append(agv_id)

        # 到达 pickup → 进入第二阶段
        for agv_id in arrived_pickup:
            if agv_id in self.agv_tasks:
                self._start_dropoff_phase(agv_id)

        # 到达 dropoff → 任务完成，AGV 变为 idle
        for agv_id in arrived_dropoff:
            if agv_id in self.agv_tasks:
                task = self.agv_tasks[agv_id]
                self.completed_tasks.append((agv_id, task))
                self._clean_agv(agv_id)

    # ──────────────────────────────────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────────────────────────────────

    def _clean_agv(self, agv_id):
        """清除 AGV 的所有任务和路径状态。"""
        self.agv_tasks.pop(agv_id, None)
        self.sparse_paths.pop(agv_id, None)
        self.prev_sparse_paths.pop(agv_id, None)

    def _split_path_by_waypoints(self, full_path, waypoints):
        """
        将完整剩余稀疏路径按 waypoints 拆分为分段。

        Parameters
        ----------
        full_path  : list of sparse vertices（当前位置开始的剩余路径）
        waypoints  : list of sparse vertices（[cur, ..., goal]）

        Returns
        -------
        list of sub-paths（每段对应 waypoints[i]→waypoints[i+1]）
        """
        segments = []
        current_idx = 0
        for i in range(len(waypoints) - 1):
            sv = waypoints[i]
            gv = waypoints[i + 1]
            try:
                s_pos = full_path.index(sv, current_idx)
            except ValueError:
                segments.append([])
                continue
            try:
                g_pos = full_path.index(gv, s_pos)
            except ValueError:
                segments.append([])
                continue
            segments.append(full_path[s_pos:g_pos + 1])
            current_idx = g_pos
        return segments

    def _bfs_sparse(self, start, goal):
        """在稀疏图上 BFS 求最短路径（顶点序列）。"""
        if start == goal:
            return [start]
        q = deque([start])
        prev = {start: None}
        while q:
            u = q.popleft()
            if u == goal:
                break
            for v in self.sparse_graph.adj.get(u, []):
                if v not in prev:
                    prev[v] = u
                    q.append(v)
        if goal not in prev:
            return None
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path

    @staticmethod
    def _extract_obstacles(grid):
        obstacles = set()
        for y in range(grid.height):
            for x in range(grid.width):
                if grid.grid[y][x] == 1:
                    obstacles.add((x, y))
        return obstacles
