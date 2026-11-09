"""Read-only backlog endpoints. All 3000 requests contribute through step 500.
No 100-step censoring; no completed-only selection for primary time metrics.
"""
import numpy as np
from recorder_base import Recorder as LifecycleRecorder
from mechanism import before_batch
def runtime_workload(w):return dict(w,grid=w['map_grid'])
class Recorder(LifecycleRecorder):
    def __init__(self,w,out,variant):
        super().__init__(runtime_workload(w),out);self.workload=w;self.variant=variant;self.plan_attempts=0;self.plan_failures=0
    def keep_alive(self,now):return now<self.workload['case']['horizon']
    def before_planning(self,p):before_batch(p,self.variant)
    def results(self,p,status):
        row=super().results(p,status);req=[self.ledger[r['id']] for r in self.workload['requests']];done=[r for r in req if r['completion'] is not None];end=p.current_time
        avg=lambda a:float(np.mean(a)) if a else None
        # Deliberately preserve the whole predetermined request population.
        row.update(requested_horizon=self.workload['case']['horizon'],followup=500,concentration=None,
            od_mode=self.workload['case']['od_mode'],static_congestion_potential=self.workload['reference_overlap'],
            cohort_n=len(req),metric_protocol='all_requests_full_horizon_restricted_time',
            completed_only_flow=row['flow_time'],completed_only_total_waiting=row['waiting_time'],
            waiting_time=avg([r['queue_wait']+r['assigned_wait'] for r in req]),
            queue_waiting_time=avg([r['queue_wait'] for r in req]),
            execution_stall_time=avg([r['assigned_wait'] for r in req]),
            movement_time=avg([r['movement_time'] for r in req]),
            flow_time=avg([r['restricted_flow_time'] for r in req]),
            completed_only_service_time=avg([r['completion']-r['first_assignment'] for r in done]),
            completed_only_stall_time=avg([r['assigned_wait'] for r in done]),
            completed_only_movement_time=avg([r['movement_time'] for r in done]),
            unfinished_fraction=row['unfinished']/len(req),
            assigned_wip=avg([len(f['assigned']) for f in self.timeline]),
            active_stalled_queue=avg([sum(f['positions'][a]==f['next_positions'][a] for a in f['assigned']) for f in self.timeline]),
            mean_active_fraction=avg([len(f['assigned'])/len(self.agents) for f in self.timeline]),
            planning_attempts=self.plan_attempts,planning_failures=self.plan_failures,
            planning_failure_fraction=self.plan_failures/self.plan_attempts if self.plan_attempts else None,
            physical_validation_performed=False,persistent_hold_fix_applied=False)
        # Primary exposure variable is precomputed OD overlap, not post-run positions.
        frames=[dict(time=f['time'],positions=f['positions']) for f in self.timeline]
        if self.timeline:frames.append(dict(time=end,positions=self.timeline[-1]['next_positions']))
        return dict(row=row,requests=req,events=self.events,timeline=self.timeline,executed_frames=frames)
