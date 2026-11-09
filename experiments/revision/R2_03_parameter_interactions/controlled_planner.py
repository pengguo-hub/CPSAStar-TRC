"""Full-batch one-shot CPS-A coordinator for R2-03.

This follows experiment.zip/CPS_A/path_planner.py::batch_plan. There is no
external/background planner. Every parameter cell starts from an empty
reservation table and CPS-A plans the complete paired task batch itself.
"""
import copy
from vendor.CPS_A.path_planner import IntegratedAGVPlanner
from vendor.CPS_A.Ticket_Manager import TicketManager
from controlled_search import ControlledSegmentPlanner
from field_strategies import make_gaussian_field
from config import LOOKAHEAD_BY_MAP

class ControlledPlanner(IntegratedAGVPlanner):
    def __init__(self, grid, agv_info, map_name, config):
        # Do not retain the parent's hard-coded field/search objects.
        super().__init__(grid, agv_info)
        self.config = config
        self.map_name = map_name
        self.ticket_manager = TicketManager()
        self.conflict_updater = make_gaussian_field(grid, self.ticket_manager, config)
        self.segment_planner = ControlledSegmentPlanner(
            grid, self.ticket_manager, self.conflict_updater, config, LOOKAHEAD_BY_MAP[map_name]
        )
        self.rollback_count = 0
        self.failed_search_count = 0
        self.field_update_count = 0

    def _publish(self):
        self.conflict_updater.batch_update_from_paths()
        self.conflict_updater.finalize_batch_update()
        self.segment_planner.congestion_dict = self.conflict_updater.smoothed_dict
        self.field_update_count += 1

    def batch_plan(self, parsed_tasks):
        time_now = 0
        tasks = copy.deepcopy(parsed_tasks)
        for _, info in tasks.items():
            info["waypoints"] = [tuple(pt) for pt in info["waypoints"]]
        self.agv_tasks = {
            aid: {
                'start': info['waypoints'][0],
                'end': info['waypoints'][-1],
                'constraints': info['constraints'],
                'waypoints': [tuple(info['agv_position']), tuple(info['source']), tuple(info['destination'])],
                'path': [],
                'position': info['waypoints'][0],
            }
            for aid, info in tasks.items()
        }
        priorities = self._sort_agvs_by_priority_and_deadline()
        for aid, info in self.agv_tasks.items():
            reservations = []
            start_pos = info['waypoints'][0]
            reserved_times = set()
            for i in range(self.segment_planner.MAX_WAIT + 1):
                t = time_now + i
                reservations.append((start_pos, t))
                reserved_times.add(t)
            if self.ticket_manager.reserve(aid, reservations, priorities[aid]):
                self.agv_tasks[aid]['reserved_start_times'] = reserved_times

        paths = {}
        planned_count = 0
        dynamic_priorities = dict(priorities)
        planning_queue = list(priorities.keys())
        committed_agvs = set()
        pending_agv_paths = {}
        replan_attempts = {}

        while planning_queue:
            aid = planning_queue.pop(0)
            weighted_priority = dynamic_priorities[aid]
            path, times = self.segment_planner.plan_agv(
                agv_id=aid,
                waypoints=self.agv_tasks[aid]['waypoints'],
                priority=weighted_priority,
                enable_turn_penalty=True,
                agv_info=self.agv_info,
                current_time=round(time_now, 1),
            )
            if path:
                paths[aid] = path
                self.agv_tasks[aid]['path'] = path
                self.agv_tasks[aid]['times'] = times
                self.agv_tasks[aid]['status'] = 'planned'
                self._release_unused_start_reservations(aid)
                self.conflict_updater.accumulate_path(path, times, aid)
                pending_agv_paths[aid] = (path, times)
                planned_count += 1
                if planned_count % self.config.update_interval == 0:
                    self._publish()
                    committed_agvs |= set(pending_agv_paths.keys())
                    pending_agv_paths.clear()
            else:
                self.failed_search_count += 1
                replan_attempts[aid] = replan_attempts.get(aid, 0) + 1
                if replan_attempts[aid] > self.config.retry_limit:
                    continue
                blocker = self._find_blocker(aid, weighted_priority, committed_agvs, dynamic_priorities)
                if blocker is None:
                    candidates = [b for b in pending_agv_paths if b not in committed_agvs and b != aid]
                    if candidates:
                        blocker = max(candidates, key=lambda x: dynamic_priorities[x])
                    else:
                        continue
                # The original one-shot source performs local rollback only within the uncommitted batch.
                if blocker not in pending_agv_paths or blocker in committed_agvs:
                    candidates = [b for b in pending_agv_paths if b not in committed_agvs and b != aid]
                    if not candidates:
                        continue
                    blocker = max(candidates, key=lambda x: dynamic_priorities[x])
                self._rollback_agv(blocker, pending_agv_paths, planned_count, paths)
                planned_count -= 1
                pending_agv_paths.pop(blocker, None)
                self.rollback_count += 1
                old_blocker_p = dynamic_priorities[blocker]
                old_failed_p = dynamic_priorities[aid]
                dynamic_priorities[aid] = old_blocker_p + 1e-4
                dynamic_priorities[blocker] = old_failed_p - 1e-4
                start_pos = self.agv_tasks[blocker]['waypoints'][0]
                re_times = set()
                reservations = []
                for i in range(self.segment_planner.MAX_WAIT + 1):
                    t = round(time_now + i * self.conflict_updater.delta, 1)
                    reservations.append((start_pos, t))
                    re_times.add(t)
                self.ticket_manager.reserve(blocker, reservations, dynamic_priorities[blocker])
                self.agv_tasks[blocker]['reserved_start_times'] = re_times
                planning_queue.insert(0, aid)
                planning_queue.append(blocker)

        if self.conflict_updater.pending_paths:
            self._publish()
        self.paths = paths
        return paths
