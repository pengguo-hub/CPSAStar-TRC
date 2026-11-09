"""
RHCR (Rolling-Horizon Collision Resolution) - Python修正版
论文: "Lifelong Multi-Agent Path Finding in Large-Scale Warehouses"
Jiaoyang Li et al., AAAI 2021

修复要点：
1. 使用 bounded-horizon Multi-Label A*（稳定可运行），不再使用有 bug 的 SIPP 草稿。
2. 正确实现 Windowed CA* with random restarts：失败则整轮重启，绝不返回残缺解。
3. low-level 在 horizon 内只需给出“前 w 步无冲突且朝目标前进”的前缀路径，
   不要求在 w 步内完成 pickup->dropoff，这才符合 RHCR/WHCA* 语义。
4. 保留 RHCR 框架：rolling horizon, keep-busy, potential P(w), greedy assignment。
"""

import heapq
import math
import random
import time
from collections import deque
from typing import List, Tuple, Optional


class AgentState:
    def __init__(self, agent_id: str, start_pos: Tuple[int, int]):
        self.agent_id = agent_id
        self.pos = start_pos
        self.goal_seq: List[Tuple[int, int]] = []
        self.current_pickup: Optional[Tuple[int, int]] = None
        self.current_dropoff: Optional[Tuple[int, int]] = None
        self.phase = 'idle'


class TaskRecord:
    def __init__(self, agent_id, pickup, dropoff, assign_time):
        self.agent_id = agent_id
        self.pickup = pickup
        self.dropoff = dropoff
        self.assign_time = assign_time
        self.complete_time = None



def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])



def _compute_hvalue_with_label(pos, goal_seq, label):
    if label >= len(goal_seq):
        return 0
    d = _manhattan(pos, goal_seq[label])
    for j in range(label + 1, len(goal_seq)):
        d += _manhattan(goal_seq[j - 1], goal_seq[j])
    return d



def _compute_hvalue(pos, goal_seq):
    return _compute_hvalue_with_label(pos, goal_seq, 0)



def _advance_label(pos, goal_seq, label):
    while label < len(goal_seq) and pos == goal_seq[label]:
        label += 1
    return label



def multi_label_astar_bounded(grid, start, goal_seq, constraints, horizon, start_time=0, max_extra_factor=4):
    if horizon <= 0:
        return [start]
    if not goal_seq:
        return [start] * (horizon + 1)

    init_label = _advance_label(start, goal_seq, 0)
    if init_label == len(goal_seq):
        return [start] * (horizon + 1)

    dist_cache = {}

    def heuristic(pos, label):
        key = (pos, label)
        if key not in dist_cache:
            dist_cache[key] = _compute_hvalue_with_label(pos, goal_seq, label)
        return dist_cache[key]

    sx, sy = start
    start_node = (sx, sy, start_time, init_label)
    heap = [(heuristic(start, init_label), 0, sx, sy, start_time, init_label)]
    visited = {start_node: 0}
    parent = {start_node: None}

    moves = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
    max_t = start_time + horizon * max_extra_factor

    best_node = start_node
    best_score = (-init_label, heuristic(start, init_label), start_time)

    while heap:
        f, g, x, y, t, label = heapq.heappop(heap)
        node = (x, y, t, label)
        if visited.get(node, math.inf) < g:
            continue

        score = (-label, heuristic((x, y), label), t)
        if score < best_score:
            best_score = score
            best_node = node

        if label == len(goal_seq):
            best_node = node
            break

        if t >= max_t:
            continue

        for dx, dy in moves:
            nx, ny = x + dx, y + dy
            nt = t + 1
            if not (0 <= nx < grid.width and 0 <= ny < grid.height):
                continue
            if grid.grid[ny][nx] != 0:
                continue

            if t < start_time + horizon:
                if (nx, ny, nt) in constraints:
                    continue
                if (x, y, nx, ny, nt) in constraints:
                    continue

            ng = g + 1
            new_label = _advance_label((nx, ny), goal_seq, label)
            new_node = (nx, ny, nt, new_label)
            if visited.get(new_node, math.inf) <= ng:
                continue
            visited[new_node] = ng
            parent[new_node] = node
            nh = heuristic((nx, ny), new_label)
            heapq.heappush(heap, (ng + nh, ng, nx, ny, nt, new_label))

    path = []
    cur = best_node
    while cur is not None:
        path.append((cur[0], cur[1]))
        cur = parent.get(cur)
    path.reverse()

    if not path:
        return None
    if len(path) < horizon + 1:
        path.extend([path[-1]] * (horizon + 1 - len(path)))
    else:
        path = path[:horizon + 1]
    return path



def windowed_ca_star(grid, agents, horizon, current_time, time_limit=2.0, max_restarts=200):
    active = [a for a in agents if a.goal_seq]
    if not active:
        return {}

    start_clock = time.time()
    restarts = 0
    while restarts < max_restarts and (time.time() - start_clock) < time_limit:
        restarts += 1
        order = list(active)
        random.shuffle(order)

        constraints = {}
        paths = {}
        failed = False

        for agent in order:
            path = multi_label_astar_bounded(
                grid=grid,
                start=agent.pos,
                goal_seq=agent.goal_seq,
                constraints=constraints,
                horizon=horizon,
                start_time=current_time,
            )

            if path is None:
                failed = True
                break

            paths[agent.agent_id] = path

            for step in range(min(len(path), horizon + 1)):
                t = current_time + step
                px, py = path[step]
                if step < horizon:
                    constraints[(px, py, t)] = agent.agent_id
                if step > 0 and step <= horizon:
                    ppx, ppy = path[step - 1]
                    if ppx != px or ppy != py:
                        constraints[(px, py, ppx, ppy, t)] = agent.agent_id

        if not failed:
            return paths

    return None



def compute_potential(agents, paths, horizon):
    count = 0
    for agent in agents:
        if agent.agent_id not in paths or not agent.goal_seq:
            continue
        path = paths[agent.agent_id]
        h_start = _compute_hvalue(agent.pos, agent.goal_seq)
        label = 0
        pos_at_w = path[-1]
        for step, pos in enumerate(path):
            label = _advance_label(pos, agent.goal_seq, label)
            if step >= horizon:
                pos_at_w = pos
                break
            pos_at_w = pos
        h_w = _compute_hvalue_with_label(pos_at_w, agent.goal_seq, label)
        if h_w < h_start:
            count += 1
    return count


class RHCRPlanner:
    def __init__(
        self,
        grid,
        agv_info,
        initial_positions,
        task_queue,
        w=10,
        h=5,
        p=1,
        w_max=30,
        ca_time_limit=2.0,
        ca_max_restarts=200,
        random_seed=0,
        use_dynamic_horizon=False,
    ):
        assert h <= w, 'h must be <= w'
        self.grid = grid
        self.agv_info = agv_info
        self.task_queue = deque(task_queue)
        self.w = w
        self.h = h
        self.p = p
        self.w_max = w_max
        self.ca_time_limit = ca_time_limit
        self.ca_max_restarts = ca_max_restarts
        self.use_dynamic_horizon = use_dynamic_horizon
        if random_seed is not None:
            random.seed(random_seed)

        self.agents = {aid: AgentState(aid, pos) for aid, pos in initial_positions.items()}
        self.current_time = 0
        self.completed_tasks = []
        self.active_tasks = {}
        self._prefetched = {aid: deque() for aid in self.agents}

        self.total_assigned_tasks = 0
        self.total_assignment_time = 0.0

    def run_lifelong(self, max_time=10000):
        episode = 0
        total_assignment_time = 0.0

        while self.current_time < max_time:
            if episode % 2 == 0:
                idle = sum(1 for a in self.agents.values() if a.phase == 'idle')
                active = len(self.active_tasks)
                print(
                    f"[ep={episode}] t={self.current_time} | "
                    f"completed={len(self.completed_tasks)} assigned={self.total_assigned_tasks}| "
                    f"active={active} idle={idle} queue={len(self.task_queue)}",
                    flush=True,
                )

            t_start = time.perf_counter()
            self._assign_tasks_greedy()
            total_assignment_time += time.perf_counter() - t_start

            if not self.active_tasks and not self.task_queue and all(a.phase == 'idle' for a in self.agents.values()):
                break

            self._update_goal_sequences()
            if self.use_dynamic_horizon:
                paths = self._plan_dynamic_horizon()
            else:
                paths = self._plan_fixed_horizon()

            if paths is None:
                print(
                    f"[t={self.current_time}] Windowed MAPF failed; "
                    f"return assigned tasks to queue.",
                    flush=True,
                )

                self._return_all_assigned_tasks_to_queue()
                self.current_time += self.h
                episode += 1
                continue

            self._execute_steps(paths, self.h)
            episode += 1

        self.total_assignment_time = total_assignment_time
        return self.completed_tasks, self.total_assigned_tasks

    def _return_all_assigned_tasks_to_queue(self):
        returned_count = 0

        # 1) 当前 active task 回队列
        for aid, record in list(self.active_tasks.items()):
            self.task_queue.append((record.pickup, record.dropoff))
            returned_count += 1

        # 2) prefetched task 也回队列
        for aid in self.agents:
            while self._prefetched[aid]:
                pk, dk = self._prefetched[aid].popleft()
                self.task_queue.append((pk, dk))
                returned_count += 1

        # 3) 撤销这些 assignment 计数
        self.total_assigned_tasks -= returned_count

        # 4) 清理所有 agent 状态
        for aid, agent in self.agents.items():
            agent.phase = 'idle'
            agent.current_pickup = None
            agent.current_dropoff = None
            agent.goal_seq = []

        # 5) 清空 active_tasks
        self.active_tasks.clear()

    def _assign_tasks_greedy(self):
        idle_agents = [aid for aid, a in self.agents.items() if a.phase == 'idle']
        if not idle_agents or not self.task_queue:
            return

        look_ahead = min(len(idle_agents) * 3, len(self.task_queue))
        candidates = list(self.task_queue)[:look_ahead]
        rem_agents = list(idle_agents)
        rem_indices = list(range(len(candidates)))
        matched = []

        while rem_agents and rem_indices:
            best_agent, best_idx, best_cost = None, None, float('inf')
            for aid in rem_agents:
                pos = self.agents[aid].pos
                for idx in rem_indices:
                    pickup, _ = candidates[idx]
                    cost = _manhattan(pos, pickup)
                    if cost < best_cost:
                        best_cost, best_agent, best_idx = cost, aid, idx
            if best_agent is None:
                break
            matched.append((best_agent, best_idx))
            rem_agents.remove(best_agent)
            rem_indices.remove(best_idx)

        matched_set = {idx for _, idx in matched}
        self.task_queue = deque(t for i, t in enumerate(self.task_queue) if i not in matched_set)

        for aid, idx in matched:
            pickup, dropoff = candidates[idx]
            agent = self.agents[aid]
            agent.phase = 'to_pickup'
            agent.current_pickup = pickup
            agent.current_dropoff = dropoff
            self._prefetched[aid].clear()
            self.active_tasks[aid] = TaskRecord(aid, pickup, dropoff, self.current_time)
            self.total_assigned_tasks += 1

    def _update_goal_sequences(self):
        for aid, agent in self.agents.items():
            if agent.phase == 'idle':
                agent.goal_seq = []
                continue

            base = [agent.current_pickup, agent.current_dropoff] if agent.phase == 'to_pickup' else [agent.current_dropoff]
            extra = []
            for pk, dk in self._prefetched[aid]:
                extra.extend([pk, dk])
            agent.goal_seq = base + extra

            d = self._compute_d(agent)
            while d < self.h and self.task_queue:
                next_pk, next_dk = self.task_queue.popleft()
                self._prefetched[aid].append((next_pk, next_dk))
                self.total_assigned_tasks += 1
                agent.goal_seq.extend([next_pk, next_dk])
                d = self._compute_d(agent)

    def _compute_d(self, agent):
        if not agent.goal_seq:
            return 0
        d = _manhattan(agent.pos, agent.goal_seq[0])
        for j in range(1, len(agent.goal_seq)):
            d += _manhattan(agent.goal_seq[j - 1], agent.goal_seq[j])
        return d

    def _plan_fixed_horizon(self):
        active_agents = [a for a in self.agents.values() if a.goal_seq]
        if not active_agents:
            return {}
        return windowed_ca_star(
            grid=self.grid,
            agents=active_agents,
            horizon=self.w,
            current_time=self.current_time,
            time_limit=self.ca_time_limit,
            max_restarts=self.ca_max_restarts,
        )

    def _plan_dynamic_horizon(self):
        active_agents = [a for a in self.agents.values() if a.goal_seq]
        if not active_agents:
            return {}

        current_w = self.w
        while True:
            paths = windowed_ca_star(
                grid=self.grid,
                agents=active_agents,
                horizon=current_w,
                current_time=self.current_time,
                time_limit=self.ca_time_limit,
                max_restarts=self.ca_max_restarts,
            )

            if paths is None:
                if current_w >= self.w_max:
                    return None
                current_w += 1
                continue

            pot = compute_potential(active_agents, paths, current_w)
            if pot >= self.p or current_w >= self.w_max:
                return paths
            current_w += 1

    def _execute_steps(self, paths, steps):
        for step_offset in range(1, steps + 1):
            for aid, agent in self.agents.items():
                if aid not in paths or not paths[aid]:
                    continue
                path = paths[aid]
                agent.pos = path[min(step_offset, len(path) - 1)]
            self._check_arrivals(self.current_time + step_offset)
        self.current_time += steps

    def _check_arrivals(self, t):
        for aid, agent in list(self.agents.items()):
            if agent.phase == 'to_pickup':
                if agent.pos == agent.current_pickup:
                    agent.phase = 'to_dropoff'
            elif agent.phase == 'to_dropoff':
                if agent.pos == agent.current_dropoff:
                    if aid in self.active_tasks:
                        record = self.active_tasks.pop(aid)
                        record.complete_time = t
                        self.completed_tasks.append(record)
                    if self._prefetched[aid]:
                        next_pk, next_dk = self._prefetched[aid].popleft()
                        agent.current_pickup = next_pk
                        agent.current_dropoff = next_dk
                        agent.phase = 'to_pickup'
                        self.active_tasks[aid] = TaskRecord(aid, next_pk, next_dk, t)
                        base = [next_pk, next_dk]
                        extra = []
                        for pk, dk in self._prefetched[aid]:
                            extra.extend([pk, dk])
                        agent.goal_seq = base + extra
                    else:
                        agent.phase = 'idle'
                        agent.current_pickup = None
                        agent.current_dropoff = None
                        agent.goal_seq = []

    def get_throughput(self):
        return 0.0 if self.current_time <= 0 else len(self.completed_tasks) / self.current_time

    def get_avg_completion_time(self):
        times = [r.complete_time - r.assign_time for r in self.completed_tasks if r.complete_time is not None]
        return sum(times) / len(times) if times else 0.0
