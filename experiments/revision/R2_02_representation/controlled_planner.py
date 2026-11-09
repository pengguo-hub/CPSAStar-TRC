"""One common coordinator derived from the original one-shot CPS-A batch planner.

Only the congestion representation, rollback switch, runtime budget, and the map-specific
heuristic switch are exposed for the controlled Reviewer-2 experiment. Planning starts from
the original planner's empty TicketManager.
"""
import copy
from vendor.CPS_A.path_planner import IntegratedAGVPlanner
from controlled_search import ControlledSegmentPlanner, BudgetExceeded
from field_strategies import make_field, lookup


class ControlledPlanner(IntegratedAGVPlanner):
    def __init__(self,grid,agv_info,representation,config,budget,map_name=None,field_context=None):
        super().__init__(grid,agv_info)
        self.config,self.budget = config,budget
        self.map_name = map_name
        self.conflict_updater = make_field(representation,grid,self.ticket_manager,config,context=field_context)
        self.segment_planner = ControlledSegmentPlanner(
            grid,self.ticket_manager,self.conflict_updater,config,budget,
            use_lookahead_congestion=(map_name == "A")
        )
        self.rollback_count = self.failed_search_count = self.blocker_guard_count = 0
        self.attempt_trace,self.field_trace = [],[]
        self.timeout = False
        self._publish()

    def _publish(self):
        self.conflict_updater.batch_update_from_paths()
        self.conflict_updater.finalize_batch_update()
        self.segment_planner.congestion_dict = lookup(self.conflict_updater)
        self.field_trace.append(dict(raw_occupancy_count=len(getattr(self.conflict_updater,"path_conflict_dict",{})),
                                     temporal_domain=getattr(self.conflict_updater,"temporal_domain",None),
                                     source_metadata=getattr(self.conflict_updater,"source_metadata",None)))

    def batch_plan(self,parsed_tasks,rollback=False,publish_final=True):
        tasks = copy.deepcopy(parsed_tasks)
        self.agv_tasks = {
            aid: dict(start=tuple(i["waypoints"][0]),end=tuple(i["waypoints"][-1]),constraints=i["constraints"],
                      waypoints=[tuple(i["agv_position"]),tuple(i["source"]),tuple(i["destination"])],
                      path=[],position=tuple(i["waypoints"][0])) for aid,i in tasks.items()}
        priorities = self._sort_agvs_by_priority_and_deadline()
        self.initial_order = list(priorities)
        for aid,info in self.agv_tasks.items():
            times = set(range(self.segment_planner.MAX_WAIT+1))
            if self.ticket_manager.reserve(aid,[(info["waypoints"][0],t) for t in sorted(times)],priorities[aid]):
                info["reserved_start_times"] = times
        paths,pending,attempts = {},{},{}
        queue = list(priorities)
        committed = set()
        planned_count = 0
        current = None
        try:
            while queue:
                self.budget.check()
                current = queue.pop(0)
                priority = priorities[current]
                self.attempt_trace.append(current)
                path,times = self.segment_planner.plan_agv(current,self.agv_tasks[current]["waypoints"],
                                                         priority,self.agv_info,0,enable_turn_penalty=True)
                if path:
                    paths[current] = path
                    self.agv_tasks[current].update(path=path,times=times,status="planned")
                    self._release_unused_start_reservations(current)
                    self.conflict_updater.accumulate_path(path,times,current)
                    pending[current] = (path,times)
                    planned_count += 1
                    if planned_count % self.config.update_interval == 0:
                        self._publish()
                        committed.update(pending)
                        pending.clear()
                else:
                    self.failed_search_count += 1
                    if not rollback:
                        continue
                    attempts[current] = attempts.get(current,0)+1
                    if attempts[current] > self.config.retry_limit:
                        continue
                    legacy = super()._find_blocker(current,priority,committed,priorities)
                    if legacy is not None and legacy not in pending:
                        self.blocker_guard_count += 1
                    excluded = committed | (set(self.agv_tasks)-set(pending))
                    blocker = super()._find_blocker(current,priority,excluded,priorities)
                    if blocker is None:
                        candidates = [a for a in pending if a not in committed and a != current]
                        if not candidates:
                            continue
                        blocker = max(candidates,key=lambda a:priorities[a])
                    assert blocker in pending and blocker not in committed
                    self._rollback_agv(blocker,pending,planned_count,paths)
                    planned_count -= 1
                    pending.pop(blocker,None)
                    self.rollback_count += 1
                    old_blocker,old_failed = priorities[blocker],priorities[current]
                    priorities[current],priorities[blocker] = old_blocker+1e-4,old_failed-1e-4
                    rtimes = {round(i*self.config.delta,1) for i in range(self.segment_planner.MAX_WAIT+1)}
                    self.ticket_manager.reserve(blocker,[(self.agv_tasks[blocker]["waypoints"][0],t) for t in sorted(rtimes)],priorities[blocker])
                    self.agv_tasks[blocker]["reserved_start_times"] = rtimes
                    queue.insert(0,current)
                    queue.append(blocker)
                current = None
            if publish_final and self.conflict_updater.pending_paths:
                self._publish()
            self.budget.check()
        except BudgetExceeded:
            self.timeout = True
            if current is not None and current not in paths:
                self.ticket_manager.release_all(current)
        for aid in self.agv_tasks:
            if aid not in paths:
                self.ticket_manager.release_all(aid)
        self.paths = paths
        return paths
