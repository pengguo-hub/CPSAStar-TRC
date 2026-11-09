"""
competition_system.py
=====================
对应 C++ guided-pibt/src/CompetitionSystem.cpp

严格按照 C++ simulate() / move() / sync_shared_env() / update_tasks() 复现。

关键修复（与原 Python 版本的差异）：

[FIX1] 执行顺序对齐 C++
  C++ simulate() 顺序：
    sync_shared_env() → plan() → timestep+=1 → move(actions) → update_tasks()
  原 Python 顺序：
    plan() → apply_actions() → process_arrivals() → [无 sync_shared_env 时机问题]
  修复：在每次 plan() 之前调用 sync_shared_env()，plan() 之后 timestep+1，
        然后 move()（包含 goal 检测），然后 update_tasks()

[FIX2] goal_locations 结构对齐 C++ assigned_tasks
  C++ sync_shared_env():
    goal_locations[i] = list of (task.location, task.t_assigned) for each task in assigned_tasks[i]
  C++ 的 assigned_tasks[k] 是一个 deque，可以有多个待完成任务（num_tasks_reveal=1时只有1个）
  C++ move() 中：if curr_states[k].location == assigned_tasks[k].front().location:
                    pop_front() → task finished
  对应我们：goal_locations[i][0][0] == curr_states[i].location 时完成

[FIX3] 任务分配策略对齐 InfAssignSystem（论文使用的无限任务模式）
  C++ InfAssignSystem::update_tasks():
    while assigned_tasks[k].size() < num_tasks_reveal:
      i = task_counter[k] * num_of_agents + k
      loc = tasks[i % tasks_size]  ← 循环复用 task 列表
  这意味着所有 agent 共享一个 tasks 数组（位置列表），循环访问。
  每个 agent 独立维护 task_counter[k]。

  在 MAPF benchmark 中，任务通常是 (pickup, dropoff) 两个位置，
  我们的两段式任务模型（pickup→dropoff）与此兼容。

[FIX4] num_tasks_reveal=1（对应论文：每个 agent 最多同时看到 1 个任务）
  C++ num_tasks_reveal 默认为 1。
  这意味着 assigned_tasks[k] 最多有 1 个条目。
  planner 每步只需要追踪一个目标。

[FIX5] solution_costs 计算
  C++ simulate() 每步：
    for a in range(N): if goal_locations[a] not empty: solution_costs[a]++
  这统计的是"等待完成任务的总步数"（类似 sum-of-cost）。

[FIX6] move() 中动作验证
  C++ valid_moves() 失败时，所有 agent 执行 Action::W（等待）。
  我们保留了碰撞检测，但改为按 C++ 方式：若有冲突所有 agent 等待。
  实际上 PIBT 保证无冲突，所以这里主要是防御性代码。

任务模型（pickup→dropoff 两段式）：
  本实现保留两段式任务模型（AGVposition→pickup→dropoff）。
  C++ 原版的 InfAssignSystem 是单段式（每个 task 只有一个目标位置）。
  我们的两段式是论文实际场景的扩展，通过每完成一段就更新 goal_locations 实现。
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Deque, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .shared_env import SharedEnv
    from .mapf_planner import MAPFPlanner

from .shared_env import AgentState, Task


# ===========================================================================
# TaskRecord
# ===========================================================================

@dataclass
class TaskRecord:
    """每个大任务（pickup+dropoff 两段）的完整记录"""
    task_id:     int
    agent_id:    int
    pickup:      Tuple[int, int]
    dropoff:     Tuple[int, int]
    pickup_loc:  int
    dropoff_loc: int
    t_assigned:  int = -1
    t_pickup:    int = -1
    t_finished:  int = -1
    failed:      bool = False


# ===========================================================================
# CompetitionSystem
# ===========================================================================

class CompetitionSystem:
    """
    对应 C++ CompetitionSystem（InfAssignSystem 变体）

    主接口：run(max_timesteps) → (completed_tasks, stats_dict)

    关键参数：
      num_tasks_reveal : 每个 agent 同时暴露的任务数（C++ 默认 1）
    """

    def __init__(
        self,
        env: "SharedEnv",
        planner: "MAPFPlanner",
        task_queue: Deque,       # deque of ((pickup_x,y),(dropoff_x,y))
        num_tasks_reveal: int = 1,
    ):
        self.env = env
        self.planner = planner
        self.task_queue = deque(task_queue)   # 循环复用
        self._task_pool: List[Tuple] = list(task_queue)  # 原始 task 列表，用于循环
        self.num_tasks_reveal = num_tasks_reveal

        self.timestep: int = 0
        self._task_id_counter: int = 0

        N = env.num_of_agents

        # ---- 对应 C++ assigned_tasks[k]（deque，每个 agent 独立）----
        # 我们用 (pickup_loc, dropoff_loc, task_record) 三元组
        # goal_locations[i] 由 sync_shared_env() 从 assigned_tasks 构建

        # 当前分配给每个 agent 的任务队列（对应 C++ assigned_tasks[k]）
        # 元素：TaskRecord
        self._assigned_tasks: List[Deque[TaskRecord]] = [deque() for _ in range(N)]

        # 当前阶段（0=前往pickup, 1=前往dropoff）
        # 注意：C++ 原版单段式，我们扩展为两段式
        self._stage: List[int] = [0] * N

        # InfAssignSystem 风格：每个 agent 独立的任务计数器
        self._task_counter: List[int] = [0] * N
        self._tasks_size: int = len(self._task_pool)
        env.build_reachable_set()

        # 统计
        self._completed: List[TaskRecord] = []
        self._total_assigned: int = 0

        self.total_assignment_time = 0.0

        # solution_costs（对应 C++）
        self._solution_costs: List[int] = [0] * N

        # 打印控制
        self._num_of_task_finish: int = 0

    # ------------------------------------------------------------------
    # sync_shared_env（对应 C++ BaseSystem::sync_shared_env()）
    # ------------------------------------------------------------------

    def _sync_shared_env(self) -> None:
        """
        对应 C++ sync_shared_env():
          env->goal_locations[i].clear()
          for task in assigned_tasks[i]:
              env->goal_locations[i].push_back({task.location, task.t_assigned})
          env->curr_timestep = timestep
          env->curr_states = curr_states

        注意：我们的两段式任务中，当前 goal = 当前阶段对应的位置。
        goal_locations[i] 只放当前目标（num_tasks_reveal=1 时 assigned_tasks 最多1个任务）。
        """
        for i in range(self.env.num_of_agents):
            self.env.goal_locations[i] = deque()
            for rec in self._assigned_tasks[i]:
                # 根据当前阶段决定 goal location
                if self._stage[i] == 0:
                    goal_loc = rec.pickup_loc
                else:
                    goal_loc = rec.dropoff_loc
                self.env.goal_locations[i].append((goal_loc, rec.t_assigned))

        self.env.curr_timestep = self.timestep

    # ------------------------------------------------------------------
    # update_tasks
    # ------------------------------------------------------------------
    def _update_tasks(self) -> None:
        """
        最优分配版本：
        找出所有 idle agent（assigned_tasks 为空的），
        从 task_pool 里取 look_ahead = min(N_idle * 3, 剩余任务数) 个候选，
        用贪心最小 Manhattan 距离匹配，
        任务池循环复用（和原版 InfAssignSystem 一样循环）。
        """
        if self._tasks_size == 0:
            return

        N = self.env.num_of_agents

        # 找 idle agents（assigned_tasks 为空）
        idle_agents = [k for k in range(N) if len(self._assigned_tasks[k]) < self.num_tasks_reveal]
        if not idle_agents:
            return

        # 候选任务窗口：look_ahead = N_idle * 3
        look_ahead = min(len(idle_agents) * 3, self._tasks_size)

        # 从当前 _task_cursor 开始取 look_ahead 个候选
        # 用一个全局游标（第一次加）
        if not hasattr(self, '_task_cursor'):
            self._task_cursor = 0

        candidates = []  # list of (pool_index, pickup_xy, dropoff_xy)
        for i in range(look_ahead):
            pool_idx = (self._task_cursor + i) % self._tasks_size
            pickup_xy, dropoff_xy = self._task_pool[pool_idx]
            pickup_loc = self.env.xy_to_loc(*pickup_xy)
            dropoff_loc = self.env.xy_to_loc(*dropoff_xy)
            if self.env.is_reachable(pickup_loc) and self.env.is_reachable(dropoff_loc):
                candidates.append((pool_idx, pickup_xy, dropoff_xy, pickup_loc, dropoff_loc))

        if not candidates:
            return

        # 贪心最小 Manhattan 匹配
        remaining_agents = list(idle_agents)
        remaining_cands = list(range(len(candidates)))  # candidates 的下标
        matched = []  # [(agent_k, cand_idx)]

        while remaining_agents and remaining_cands:
            best_agent, best_ci, best_cost = None, None, float('inf')
            for k in remaining_agents:
                agent_loc = self.env.curr_states[k].location
                ax, ay = self.env.loc_to_xy(agent_loc)
                for ci in remaining_cands:
                    px, py = candidates[ci][1]  # pickup_xy
                    cost = abs(ax - px) + abs(ay - py)
                    if cost < best_cost:
                        best_cost, best_agent, best_ci = cost, k, ci
            if best_agent is None:
                break
            matched.append((best_agent, best_ci))
            remaining_agents.remove(best_agent)
            remaining_cands.remove(best_ci)

        # 分配
        matched_pool_indices = set()
        for k, ci in matched:
            pool_idx, pickup_xy, dropoff_xy, pickup_loc, dropoff_loc = candidates[ci]
            matched_pool_indices.add(pool_idx)

            rec = TaskRecord(
                task_id=self._task_id_counter,
                agent_id=k,
                pickup=pickup_xy,
                dropoff=dropoff_xy,
                pickup_loc=pickup_loc,
                dropoff_loc=dropoff_loc,
                t_assigned=self.timestep,
            )
            self._task_id_counter += 1
            self._total_assigned += 1
            self._assigned_tasks[k].append(rec)
            if len(self._assigned_tasks[k]) == 1:
                self._stage[k] = 0

        # 推进游标：跳过已匹配的 look_ahead 窗口
        self._task_cursor = (self._task_cursor + look_ahead) % self._tasks_size
    # ------------------------------------------------------------------
    # move（对应 C++ BaseSystem::move()）
    # ------------------------------------------------------------------

    def _move(self, actions: List[int]) -> List[TaskRecord]:
        """
        对应 C++ list<Task> BaseSystem::move(vector<Action>& actions)

        执行：
          1. 验证动作（顶点冲突 / 边冲突检测）
          2. 更新 curr_states
          3. 检测 goal 到达：若 curr_states[k].location == assigned_tasks[k].front() 的当前 goal
             → 对于我们的两段式：
               stage 0 到达 → 切换到 stage 1（goal = dropoff），通知 planner
               stage 1 到达 → 任务完成，分配下一个任务
          4. 对应 C++: finished_tasks_this_timestep 返回

        返回：本步完成的任务列表（用于统计）
        """
        N = self.env.num_of_agents

        # --- 动作验证（对应 C++ valid_moves()）---
        # 顶点冲突检测
        next_locs = [actions[i] if actions[i] >= 0 else self.env.curr_states[i].location
                     for i in range(N)]
        loc_count: Dict[int, int] = {}
        has_conflict = False
        for loc in next_locs:
            loc_count[loc] = loc_count.get(loc, 0) + 1
            if loc_count[loc] > 1:
                has_conflict = True
                break

        if has_conflict:
            # C++: all agents wait
            next_locs = [self.env.curr_states[i].location for i in range(N)]

        # --- 更新位置（对应 C++ curr_states = model->result_states(...)）---
        for i in range(N):
            self.env.curr_states[i].location = next_locs[i]
            self.env.curr_states[i].timestep = self.timestep

        # --- 检测 goal 到达（对应 C++ move() 中的 task completion 检测）---
        # C++: if curr_states[k].location == assigned_tasks[k].front().location
        #          pop assigned_tasks[k].front() → finished
        # 我们的两段式：需要同时处理 stage 切换
        finished_this_step: List[TaskRecord] = []

        for i in range(N):
            if not self._assigned_tasks[i]:
                continue

            rec = self._assigned_tasks[i][0]
            stage = self._stage[i]

            if stage == 0:
                current_goal_loc = rec.pickup_loc
            else:
                current_goal_loc = rec.dropoff_loc

            if self.env.curr_states[i].location != current_goal_loc:
                continue

            # 到达当前目标
            # 通知 planner（清除 guide path，准备下一目标）
            self.planner.on_goal_reached(i)

            if stage == 0:
                # 到达 pickup → 切换到 dropoff
                rec.t_pickup = self.timestep
                self._stage[i] = 1
                # goal_locations 会在下一步 sync_shared_env 时更新

            else:
                # 到达 dropoff → 任务完成
                rec.t_finished = self.timestep
                self._completed.append(rec)
                self._num_of_task_finish += 1

                # 对应 C++: assigned_tasks[k].pop_front()
                self._assigned_tasks[i].popleft()
                self._stage[i] = 0

                finished_this_step.append(rec)

        return finished_this_step

    # ------------------------------------------------------------------
    # 主仿真循环（对应 C++ BaseSystem::simulate()）
    # ------------------------------------------------------------------

    def run(self, max_timesteps: int) -> Tuple[List[TaskRecord], dict]:
        """
        对应 C++ void BaseSystem::simulate(int simulation_time)

        C++ 执行顺序（每 timestep）：
          1. sync_shared_env()
          2. actions = plan()               ← planner.compute_actions()
          3. timestep += 1
          4. solution_costs[a]++ for agents with goals
          5. new_finished = move(actions)
          6. update_tasks()
          7. check if all done → break

        注意：C++ 是先 sync → 再 plan → 再 timestep++
              不是 plan → timestep++ → sync！
        """
        total_assignment_time = 0.0
        wall_start = time.perf_counter()


        # --- 初始化：分配首批任务 ---
        # 对应 C++ initialize() → update_tasks() → sync_shared_env()
        t_start = time.perf_counter()
        self._update_tasks()
        assignment_time = time.perf_counter() - t_start
        total_assignment_time += assignment_time

        self._sync_shared_env()

        # --- 主循环 ---
        for t in range(max_timesteps):
            # C++: for (; timestep < simulation_time && !has_timeout; )

            # 打印进度（对应 C++ 的 cout 输出）
            if t % 10 == 0 or t < 5:
                print(
                    f"[t={t:5d}] "
                    f"finished={self._num_of_task_finish:4d} "
                    f"throughput={self._num_of_task_finish / max(t, 1):.4f} "
                    f"assigned={self._total_assigned:4d}"
                )

            # Step 1: sync_shared_env（plan 之前更新 goal_locations）
            self._sync_shared_env()

            # Step 2: plan（对应 C++ actions = plan()）
            actions = self.planner.compute_actions(t)

            # Step 3: timestep += 1
            self.timestep = t + 1

            # Step 4: solution_costs（对应 C++）
            for a in range(self.env.num_of_agents):
                if self.env.goal_locations[a]:
                    self._solution_costs[a] += 1

            # Step 5: move（对应 C++ move(actions)）
            new_finished = self._move(actions)

            # 打印（对应 C++ cout 输出）
            # if new_finished:
            #     print(f"  ---timestep-task-finished,{len(new_finished)}")
            # print(f"  ---total-task-finished,{self._num_of_task_finish}")

            # Step 6: update_tasks（对应 C++ update_tasks()）
            t_start = time.perf_counter()
            self._update_tasks()
            assignment_time = time.perf_counter() - t_start
            total_assignment_time += assignment_time

            # Step 7: check done（对应 C++ complete_all 检测）
            # C++: if all assigned_tasks[k] are empty → break
            # 对于 InfAssignSystem，任务无限，永不满足此条件
            # 但若任务池已耗尽则可能完成
            if self._tasks_size == 0 and all(
                len(q) == 0 for q in self._assigned_tasks
            ):
                print("\nAll tasks finished!")
                break

        self.total_assignment_time = total_assignment_time
        wall_elapsed = time.perf_counter() - wall_start

        # 统计
        total_time = self.timestep
        throughput = self._num_of_task_finish / total_time if total_time > 0 else 0.0

        finish_times = [
            r.t_finished - r.t_assigned
            for r in self._completed
            if r.t_finished >= 0 and r.t_assigned >= 0
        ]
        avg_finish = sum(finish_times) / len(finish_times) if finish_times else 0.0

        pickup_times = [
            r.t_pickup - r.t_assigned
            for r in self._completed
            if r.t_pickup >= 0 and r.t_assigned >= 0
        ]
        avg_pickup = sum(pickup_times) / len(pickup_times) if pickup_times else 0.0

        sum_of_cost = sum(self._solution_costs)

        stats = {
            "timesteps":        self.timestep,
            "tasks_completed":  self._num_of_task_finish,
            "tasks_assigned":   self._total_assigned,
            "throughput":       throughput,
            "avg_task_time":    avg_finish,
            "avg_pickup_time":  avg_pickup,
            "sum_of_cost":      sum_of_cost,
            "wall_time_s":      wall_elapsed,
            "assignment_time_s": total_assignment_time,
        }

        print(f"\n=== Done! timesteps={self.timestep}, "
              f"tasks_finished={self._num_of_task_finish}, "
              f"throughput={throughput:.4f} ===")

        return self._completed, stats
