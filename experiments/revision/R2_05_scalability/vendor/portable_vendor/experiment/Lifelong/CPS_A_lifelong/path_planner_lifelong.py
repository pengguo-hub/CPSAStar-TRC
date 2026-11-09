#在任务分配增加冲突场
from collections import deque
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.Conflict_Field_Updater import ConflictFieldUpdater
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.Segment_Planner import SegmentPlanner
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.CPS_A_lifelong.Ticket_Manager import TicketManager
import time

class LifelongPlanner:
    def __init__(self, grid, agv_info, initial_positions, task_queue,
                 use_priority_replan=False):
        """
        Args:
            grid:                 GridMap 对象
            agv_info:             {agv_id: {'speed': float}}
            initial_positions:    {agv_id: (x, y)}，由 BenchmarkLoader 提供
            task_queue:           deque of (pickup, dropoff)，由 BenchmarkLoader 提供
            use_priority_replan:  True  → 规划失败时使用优先级交换+回滚（带重规划上限）
                                  False → 规划失败直接标记 failed，AGV 回到 idle
        """
        self.grid = grid
        self.agv_info = agv_info
        self.ticket_manager   = TicketManager()
        self.conflict_updater = ConflictFieldUpdater(grid, self.ticket_manager)
        self.segment_planner  = SegmentPlanner(grid, self.ticket_manager, self.conflict_updater)

        # 规划失败策略开关
        self.use_priority_replan = use_priority_replan

        # lifelong 状态
        self.current_time    = 0.0
        self.task_queue      = deque(task_queue)
        self.agv_tasks       = {}   # {agv_id: task_dict}
        self.completed_tasks = []
        self.total_assigned_tasks = 0
        self.total_assignment_time = 0.0

        # AGV 实时位置（含空闲 AGV）
        self.agv_positions = dict(initial_positions)

        # batch_plan 变量
        self.pending_agv_paths  = {}
        self.committed_agvs     = set()
        self.UPDATE_COUNT       = 40
        self.planned_count      = 0

        # 优先级重规划相关（仅 use_priority_replan=True 时使用）
        self.replan_attempts    = {}
        self.MAX_REPLAN_PER_AGV = 5

        self.USE_CON = False

    # =========================================================================
    # 主循环
    # =========================================================================
    def run_lifelong(self, max_time=10000):
        cycle = 0
        total_assignment_time = 0.0

        while self.current_time < max_time:
            if cycle % 10 == 0:
                executing = sum(1 for t in self.agv_tasks.values() if t.get('status') == 'executing')
                pending   = sum(1 for t in self.agv_tasks.values() if t.get('status') == 'pending')
                idle      = len(set(self.agv_info.keys()) - set(self.agv_tasks.keys()))
                print(f"[cycle={cycle:4d}] time={self.current_time:.1f} | "
                      f"completed={len(self.completed_tasks)} assigned={self.total_assigned_tasks} | "
                      f"executing={executing} pending={pending} idle={idle} | "
                      f"queue={len(self.task_queue)}", flush=True)

            t_start = time.perf_counter()
            self._assign_new_tasks()
            total_assignment_time += time.perf_counter() - t_start

            if not self.agv_tasks and not self.task_queue:
                break

            self._plan_one_batch()
            self._simulate_one_step()

            self.ticket_manager.release(self.current_time)
            self._clean_completed_tasks()
            self.USE_CON = True
            if cycle % 50 == 0:
                self.conflict_updater.cleanup_expired_slots(self.current_time)

            cycle += 1

        self.total_assignment_time = total_assignment_time
        return self.completed_tasks, self.total_assigned_tasks

    # =========================================================================
    # 任务分配
    # =========================================================================
    def _assign_new_tasks(self):
        busy_agvs = set(self.agv_tasks.keys())
        idle_agvs = [aid for aid in self.agv_info.keys() if aid not in busy_agvs]
        if not idle_agvs or not self.task_queue:
            return

        look_ahead = min(len(idle_agvs) * 3, len(self.task_queue))
        candidates = []
        for i, task in enumerate(self.task_queue):
            if i >= look_ahead:
                break
            candidates.append((i, task))  # (原始下标, (pickup, dropoff))

        remaining_agvs = list(idle_agvs)
        remaining_indices = [i for i, _ in candidates]
        index_to_task = {i: t for i, t in candidates}
        matched = []  # [(agv_id, original_index)]

        # USE_CON=False：纯 Manhattan，直接在匹配循环里算，不需要预算矩阵
        while remaining_agvs and remaining_indices:
            best_agv, best_index, best_cost = None, None, float('inf')
            for agv_id in remaining_agvs:
                pos = self.agv_positions.get(agv_id)
                for idx in remaining_indices:
                    pickup, _ = index_to_task[idx]
                    c = abs(pos[0] - pickup[0]) + abs(pos[1] - pickup[1])
                    if c < best_cost:
                        best_cost, best_agv, best_index = c, agv_id, idx
            if best_agv is None:
                break
            matched.append((best_agv, best_index))
            remaining_agvs.remove(best_agv)
            remaining_indices.remove(best_index)

        # 从task_queue里删除已匹配的任务（按原始下标）
        matched_indices = set(idx for _, idx in matched)
        self.task_queue = deque(
            task for i, task in enumerate(self.task_queue)
            if i not in matched_indices
        )

        # 分配
        for agv_id, idx in matched:
            pickup, dropoff = index_to_task[idx]
            current_pos = self.agv_positions[agv_id]

            self.ticket_manager.release_all(agv_id)
            self.ticket_manager.reserve(
                agv_id,
                [(current_pos, round(self.current_time, 1))],
                priority=1.0
            )

            waypoints = [current_pos, pickup]
            unique_waypoints = []
            for p in waypoints:
                if not unique_waypoints or p != unique_waypoints[-1]:
                    unique_waypoints.append(p)

            self.agv_tasks[agv_id] = {
                'start': unique_waypoints[0],
                'pickup': pickup,
                'dropoff': dropoff,
                'waypoints': unique_waypoints,
                'phase': 'to_pickup',
                'path': [],
                'times': [],
                'path_index': 0,
                'status': 'pending',
                'position': unique_waypoints[0],
                'constraints': {},
                'last_plan_time': self.current_time,
            }
            self.total_assigned_tasks += 1

    def _assign_second_phase(self, agv_id):
        """
        AGV 到达 pickup 后触发第二段：pickup → dropoff（phase='to_dropoff'）
        """
        task        = self.agv_tasks[agv_id]
        current_pos = task['position']
        dropoff     = task['dropoff']

        self.ticket_manager.release_all(agv_id)

        self.ticket_manager.reserve(
            agv_id,
            [(current_pos, round(self.current_time, 1))],
            priority=1.0
        )

        waypoints = [current_pos, dropoff]
        unique_waypoints = []
        for p in waypoints:
            if not unique_waypoints or p != unique_waypoints[-1]:
                unique_waypoints.append(p)

        task['start']          = unique_waypoints[0]
        task['waypoints']      = unique_waypoints
        task['phase']          = 'to_dropoff'
        task['path']           = []
        task['times']          = []
        task['path_index']     = 0
        task['status']         = 'pending'
        task['last_plan_time'] = self.current_time
        self.committed_agvs.discard(agv_id)
        self.pending_agv_paths.pop(agv_id, None)
        # 清除第一段的重规划计数
        self.replan_attempts.pop(agv_id, None)

    # =========================================================================
    # 规划
    # =========================================================================
    def _plan_one_batch(self):
        planning_queue = [
            aid for aid, task in self.agv_tasks.items()
            if aid not in self.committed_agvs
               and task.get('status') not in ('executing',)
        ]
        if not planning_queue:
            return

        dynamic_priorities = {}
        for agv_id in planning_queue:
            task = self.agv_tasks[agv_id]
            wait_time = self.current_time - task.get('last_plan_time', self.current_time)

            # 查当前位置的拥塞值
            pos = self.agv_positions.get(agv_id)
            if pos and self.USE_CON:
                slot = int(self.current_time // self.conflict_updater.delta)
                local_cong = self.conflict_updater.smoothed_dict.get((pos[0], pos[1], slot), 0.0)
            else:
                local_cong = 0.0

            dynamic_priorities[agv_id] = 1.0 + wait_time * 0.1 + local_cong * 0.5

        planning_queue.sort(key=lambda x: dynamic_priorities[x], reverse=True)

        while planning_queue:
            agv_id = planning_queue.pop(0)

            if agv_id not in self.agv_tasks:
                continue
            if self.agv_tasks[agv_id].get('status') == 'executing':
                continue

            weighted_priority = dynamic_priorities[agv_id]

            path, times = self.segment_planner.plan_agv(
                agv_id=agv_id,
                waypoints=self.agv_tasks[agv_id]['waypoints'],
                priority=weighted_priority,
                enable_turn_penalty=True,
                agv_info=self.agv_info,
                current_time=round(self.current_time, 1)
            )

            if path:
                self.agv_tasks[agv_id]['path'] = path
                self.agv_tasks[agv_id]['times'] = times
                self.agv_tasks[agv_id]['path_index'] = 0
                self.agv_tasks[agv_id]['status'] = 'planned'
                self.pending_agv_paths[agv_id] = (path, times)
                self.conflict_updater.accumulate_path(path, times, agv_id)
                self.planned_count += 1

                self._release_start_reservation_if_unused(agv_id, path, times)

                if self.planned_count % self.UPDATE_COUNT == 0:
                    self._commit_pending_paths()

            else:
                if self.use_priority_replan:
                    self._handle_failure_with_replan(
                        agv_id, weighted_priority,
                        planning_queue, dynamic_priorities
                    )
                else:
                    self._handle_failure_direct(agv_id)

        if self.pending_agv_paths:
            self._commit_pending_paths()

        # print(f"  [batch] total={total} success={planned_this_batch}| ")

    def _handle_failure_direct(self, agv_id):
        """
        规划失败：不再记为永久失败，而是退回 task_queue。
        AGV 本轮变 idle，后续再参与分配。
        """
        task = self.agv_tasks.pop(agv_id)

        task['status'] = 'unassigned'

        self.committed_agvs.discard(agv_id)
        self.pending_agv_paths.pop(agv_id, None)

        pickup = task['pickup']
        dropoff = task['dropoff']
        # 任务放回队尾，保持 FIFO
        self.task_queue.append((pickup, dropoff))
        self.total_assigned_tasks -= 1
        # 释放该 AGV 当前所有预约
        self.ticket_manager.release_all(agv_id)
        # 清理重规划计数
        self.replan_attempts.pop(agv_id, None)

    def _handle_failure_with_replan(self, agv_id, weighted_priority,
                                     planning_queue, dynamic_priorities):
        """
        失败策略B（use_priority_replan=True）：
        优先级交换 + blocker 回滚，超过重规划上限再标记 failed。
        """
        self.replan_attempts[agv_id] = self.replan_attempts.get(agv_id, 0) + 1
        if self.replan_attempts[agv_id] > self.MAX_REPLAN_PER_AGV:
            self._handle_failure_direct(agv_id)
            return

        blocker = self._find_blocker(
            agv_id, weighted_priority, self.committed_agvs, dynamic_priorities
        )

        if blocker is None:
            candidate_blockers = [
                bid for bid in self.pending_agv_paths.keys()
                if bid not in self.committed_agvs and bid != agv_id
            ]
            if candidate_blockers:
                blocker = max(candidate_blockers,
                              key=lambda x: dynamic_priorities.get(x, 0))
            else:
                self.agv_tasks[agv_id]['last_plan_time'] = self.current_time
                return

        # 回滚 blocker
        self._rollback_agv(blocker)
        self.planned_count -= 1
        self.pending_agv_paths.pop(blocker, None)

        # 交换优先级
        old_blocker_p = dynamic_priorities.get(blocker, 1.0)
        old_failed_p  = dynamic_priorities.get(agv_id, 1.0)
        dynamic_priorities[agv_id] = old_blocker_p + 1e-4
        dynamic_priorities[blocker] = old_failed_p - 1e-4
        if agv_id in self.agv_tasks:
            self.agv_tasks[agv_id]['priority'] = dynamic_priorities[agv_id]
        if blocker in self.agv_tasks:
            self.agv_tasks[blocker]['priority'] = dynamic_priorities[blocker]

        # 动态队列重排
        planning_queue.insert(0, agv_id)
        planning_queue.append(blocker)

    def _release_start_reservation_if_unused(self, agv_id, path, times):
        if not path or not times:
            return
        start_pos  = tuple(self.agv_tasks[agv_id]['start'])
        reserved_t = round(self.current_time, 1)

        used = any(
            tuple(p) == start_pos and abs(t - reserved_t) < 1e-9
            for p, t in zip(path, times)
        )
        if not used:
            key = (start_pos, reserved_t)
            if key in self.ticket_manager.node_reservations:
                self.ticket_manager.node_reservations[key].pop(agv_id, None)
                if not self.ticket_manager.node_reservations[key]:
                    del self.ticket_manager.node_reservations[key]
            self.ticket_manager.agv_reservations[agv_id].discard(key)

    def _commit_pending_paths(self):
        if not self.pending_agv_paths:
            return
        self.conflict_updater.batch_update_from_paths()
        self.conflict_updater.finalize_batch_update()
        self.segment_planner.congestion_dict = self.conflict_updater.smoothed_dict
        for agv_id in self.pending_agv_paths:
            if agv_id in self.agv_tasks:
                self.agv_tasks[agv_id]['status'] = 'executing'
                self.committed_agvs.add(agv_id)
        self.pending_agv_paths.clear()

    def _rollback_agv(self, agv_id):
        """回滚未固化的 AGV：释放预约，清除路径，状态回 pending"""
        self.ticket_manager.release_all(agv_id)
        self.conflict_updater.pending_paths = [
            (p, t, aid) for (p, t, aid) in self.conflict_updater.pending_paths
            if aid != agv_id
        ]
        if agv_id in self.agv_tasks:
            self.agv_tasks[agv_id]['path']       = []
            self.agv_tasks[agv_id]['times']      = []
            self.agv_tasks[agv_id]['path_index'] = 0
            self.agv_tasks[agv_id]['status']     = 'pending'
        self.pending_agv_paths.pop(agv_id, None)
        self.committed_agvs.discard(agv_id)

        if agv_id in self.agv_tasks:
            start_pos = self.agv_tasks[agv_id]['start']
            self.ticket_manager.reserve(
                agv_id,
                [(start_pos, round(self.current_time, 1))],
                priority=1.0
            )

    def _find_blocker(self, failed_agv_id, failed_priority, committed_agvs, dynamic_priorities):
        waypoints     = self.agv_tasks[failed_agv_id]['waypoints']
        waypoint_set  = set(map(tuple, waypoints))
        candidate_blockers = {}

        for bid, (bpath, btimes) in self.pending_agv_paths.items():
            if bid == failed_agv_id or bid in committed_agvs:
                continue
            if dynamic_priorities.get(bid, 0.0) < failed_priority:
                continue
            overlap = sum(1 for pos in bpath if tuple(pos) in waypoint_set)
            if overlap > 0:
                candidate_blockers[bid] = candidate_blockers.get(bid, 0) + overlap

        if not candidate_blockers:
            return None
        return max(candidate_blockers, key=candidate_blockers.get)

    # =========================================================================
    # 时间推进
    # =========================================================================
    def _simulate_one_step(self):
        next_time = float('inf')
        agv_next  = {}

        for agv_id, task in self.agv_tasks.items():
            if task.get('status') != 'executing':
                continue
            times = task['times']
            path  = task['path']
            idx   = task.get('path_index', 0)

            while idx < len(times) and times[idx] <= self.current_time + 1e-9:
                idx += 1
            task['path_index'] = idx

            if idx < len(times):
                next_time = min(next_time, times[idx])
                agv_next[agv_id] = (times[idx], path[idx])

        if next_time == float('inf'):
            self.current_time += 1
        else:
            self.current_time = next_time
            for agv_id, (t, pos) in agv_next.items():
                if abs(t - self.current_time) < 1e-9:
                    self.agv_tasks[agv_id]['position'] = pos
                    self.agv_positions[agv_id]         = pos

    # =========================================================================
    # 清理完成阶段的任务
    # =========================================================================
    def _clean_completed_tasks(self):
        """
        - 到达 pickup（phase='to_pickup'）：触发第二段规划
        - 到达 dropoff（phase='to_dropoff'）：任务完成，AGV 回到 idle
        """
        arrived_pickup  = []
        arrived_dropoff = []

        for agv_id, task in self.agv_tasks.items():
            if task.get('status') != 'executing':
                continue
            pos   = task.get('position')
            phase = task.get('phase')

            if phase == 'to_pickup' and pos == task['pickup']:
                arrived_pickup.append(agv_id)
            elif phase == 'to_dropoff' and pos == task['dropoff']:
                arrived_dropoff.append(agv_id)

        # 到达 pickup：触发第二段
        for agv_id in arrived_pickup:
            if agv_id not in self.agv_tasks:
                continue
            self._assign_second_phase(agv_id)

        # 到达 dropoff：任务完成
        for agv_id in arrived_dropoff:
            if agv_id not in self.agv_tasks:
                continue
            task     = self.agv_tasks[agv_id]
            idle_pos = task['position']

            self.ticket_manager.release_all(agv_id)

            self.agv_positions[agv_id] = idle_pos
            self.completed_tasks.append((agv_id, task))
            del self.agv_tasks[agv_id]
            self.committed_agvs.discard(agv_id)
            self.pending_agv_paths.pop(agv_id, None)
            self.replan_attempts.pop(agv_id, None)

    def get_throughput(self):
        if self.current_time <= 0:
            return 0.0
        return len(self.completed_tasks) / self.current_time



