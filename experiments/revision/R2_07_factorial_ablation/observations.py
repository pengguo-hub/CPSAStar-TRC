"""Passive backlog task/field recorder. No physical collision checks or planner changes."""
import time
import numpy as np
from experiments.revision.R2_07_factorial_ablation.workload import write_json

class Request(tuple):
    def __new__(cls,pickup,dropoff,rid):
        obj=super().__new__(cls,(tuple(pickup),tuple(dropoff)));obj.rid=rid;return obj

class Recorder:
    def __init__(self,workload,checkpoint=None):
        self.workload=workload;self.checkpoint=checkpoint;self.cursor=0
        self.started=time.perf_counter();self.planning_times=[]
        self.ledger={r['id']:dict(r,first_assignment=None,completion=None,assignments=0,
            queue_wait=0.,assigned_wait=0.,movement_time=0.,second_phase_count=0,requeues=0)
            for r in workload['requests']}
        self.events=[];self.trace=[];self.frames=[dict(time=0.,positions=workload['initial_positions'])]
        self.rollbacks=0;self.priority_swaps=0;self.pending_frame=None

    def initial_queue(self):
        self.cursor=len(self.workload['requests'])
        return [Request(r['pickup'],r['dropoff'],r['id']) for r in self.workload['requests']]

    def on_assignment(self,p,aid,request):
        rid=request.rid;p.agv_tasks[aid]['_request_id']=rid
        row=self.ledger[rid];row['assignments']+=1
        if row['first_assignment'] is None:row['first_assignment']=p.current_time
        self.events.append(dict(event='assignment',time=p.current_time,agent=aid,request=rid))

    def on_second_phase(self,p,aid,task):
        rid=task['_request_id'];self.ledger[rid]['second_phase_count']+=1
        self.events.append(dict(event='pickup_to_dropoff',time=p.current_time,agent=aid,request=rid))

    def on_requeue(self,p,aid,task,pickup,dropoff):
        rid=task['_request_id'];self.ledger[rid]['requeues']+=1
        self.events.append(dict(event='requeue',time=p.current_time,agent=aid,request=rid,phase=task['phase']))
        return Request(pickup,dropoff,rid)

    def on_rollback(self,p,failed,blocker,priority_swap):
        self.rollbacks+=1;self.priority_swaps+=int(priority_swap)
        self.events.append(dict(event='rollback',time=p.current_time,failed=failed,blocker=blocker,priority_swap=priority_swap))

    def on_completion(self,p,aid,task):
        rid=task['_request_id'];row=self.ledger[rid]
        if row['completion'] is not None:raise AssertionError('Duplicate request completion')
        row['completion']=p.current_time
        self.events.append(dict(event='completion',time=p.current_time,agent=aid,request=rid))

    def before_advance(self,p,planning_seconds):
        self.planning_times.append(planning_seconds)
        self.pending_frame=dict(time=p.current_time,positions=dict(p.agv_positions),
            queued=[r.rid for r in p.task_queue],assigned={a:t['_request_id'] for a,t in p.agv_tasks.items()})
        slot=int(p.current_time//p.conflict_updater.delta)
        keys=[(pos[0],pos[1],slot) for pos in p.agv_positions.values()]
        field_exposure=float(np.mean([p.conflict_updater.smoothed_dict.get(k,0.) for k in keys])) if keys else 0.
        raw_exposure=float(np.mean([p.conflict_updater.path_conflict_dict.get(k,0.) for k in keys])) if keys else 0.
        self.trace.append(dict(time=p.current_time,queue_length=len(p.task_queue),backlog=len(p.task_queue)+len(p.agv_tasks),
                               planning_seconds=planning_seconds,field_entries=len(p.conflict_updater.smoothed_dict),
                               source_field_exposure=field_exposure,source_raw_slot_exposure=raw_exposure))

    def after_cycle(self,p):
        f=self.pending_frame;dt=p.current_time-f['time'];assert dt>0
        self.trace[-1]['duration']=dt
        for rid in f['queued']:self.ledger[rid]['queue_wait']+=dt
        for aid,rid in f['assigned'].items():
            if tuple(p.agv_positions[aid])==tuple(f['positions'][aid]):self.ledger[rid]['assigned_wait']+=dt
            else:self.ledger[rid]['movement_time']+=dt
        self.frames.append(dict(time=p.current_time,positions={a:list(pos) for a,pos in p.agv_positions.items()}))
        if self.checkpoint and len(self.trace)%10==0:
            write_json(self.checkpoint,self.results(p,status='checkpoint',compute_exposure=False))

    def results(self,p,status='completed',compute_exposure=True):
        end=p.current_time
        if status=='completed' and end!=self.workload['case']['horizon']:status='incomplete'
        arrived=[self.ledger[r['id']].copy() for r in self.workload['requests'][:self.cursor]]
        completed=[r for r in arrived if r['completion'] is not None]
        for r in arrived:
            r['waiting_time']=r['queue_wait']+r['assigned_wait']
            r['flow_time']=None if r['completion'] is None else r['completion']-r['release']
            r['restricted_flow_time']=(r['completion'] if r['completion'] is not None else end)-r['release']
        # Above copies share completed references because completed was built from arrived.
        avg=lambda xs:float(np.mean(xs)) if xs else None
        trace=[r for r in self.trace if 'duration' in r]
        weights=[r['duration'] for r in trace]
        c=self.workload['case']
        row=dict(case=c['name'],map=c['map'],seed=self.workload['seed'],fleet=c['fleet'],tiles=c['tiles'],
            width=self.workload['width'],height=self.workload['height'],free_cells=self.workload['free_cells'],
            mode=c['mode'],warmup=c['warmup'],
            workload_hash=self.workload['workload_hash'],status=status,requested_horizon=c['horizon'],observed_time=end,
            arrived=len(arrived),completed=len(completed),unfinished=len(arrived)-len(completed),
            source_total_assigned=p.total_assigned_tasks,throughput=p.get_throughput(),
            throughput_fixed_window=len(completed)/c['horizon'],
            completion_fraction=len(completed)/len(arrived) if arrived else None,
            waiting_time=avg([r['waiting_time'] for r in completed]),flow_time=avg([r['flow_time'] for r in completed]),
            waiting_all_arrived=avg([r['waiting_time'] for r in arrived]),
            restricted_flow_all_arrived=avg([r['restricted_flow_time'] for r in arrived]),
            queue_length=float(np.average([r['queue_length'] for r in trace],weights=weights)) if weights else None,
            source_field_exposure=float(np.average([r['source_field_exposure'] for r in trace],weights=weights)) if weights else None,
            source_raw_slot_exposure=float(np.average([r['source_raw_slot_exposure'] for r in trace],weights=weights)) if weights else None,
            final_queue=len(p.task_queue),final_backlog=len(p.task_queue)+len(p.agv_tasks),
            rollback_count=self.rollbacks,priority_swaps=self.priority_swaps,planning_seconds=sum(self.planning_times),
            planning_p95=float(np.quantile(self.planning_times,.95)) if self.planning_times else None,
            wall_seconds=time.perf_counter()-self.started)
        row['task_ledger_valid']=(len(arrived)==len(completed)+len(p.task_queue)+len(p.agv_tasks) and len(completed)==len(p.completed_tasks))
        row['completed_horizon']=(end==c['horizon'] and len(trace)==c['horizon'])
        if status=='completed' and not (row['task_ledger_valid'] and row['completed_horizon']):row['status']='invalid'
        row['queue_wait_all_arrived']=avg([r['queue_wait'] for r in arrived])
        row['assigned_wait_all_arrived']=avg([r['assigned_wait'] for r in arrived])
        return dict(row=row,requests=arrived,events=self.events,queue_trace=self.trace,executed_frames=self.frames)
