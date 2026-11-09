"""Task identity, release inputs and read-only records. Never validates physical collisions."""
from collections import Counter,defaultdict
import gzip,json,time
import numpy as np
from experiments.revision.R2_04_operational_metrics.common import ROOT, write_json, read_json

class Request(tuple):
    def __new__(cls,pickup,dropoff,rid):
        q=super().__new__(cls,(tuple(pickup),tuple(dropoff)));q.rid=rid;return q

class Recorder:
    def __init__(self,w,out):
        self.w=w;self.out=out;self.cursor=0;self.active={};self.events=[];self.timeline=[];self.segment_calls=[]
        self.agents=list(w['initial_positions']);self.overhead_seconds=0.;self.callback_seconds=defaultdict(float)
        self.ledger={r['id']:dict(r,first_assignment=None,completion=None,assignment_events=0,requeues=0,
                               pickups=0,queue_wait=0.,assigned_wait=0.,movement_time=0.) for r in w['requests']}
        self.rollbacks=0;self.pending=None;self.batch_seconds=[];self.batch_inclusive=[];self.batch_started=None
        self.started=time.perf_counter()

    def initial_queue(self):
        if self.w['case']['mode']!='backlogged':return []
        self.cursor=len(self.w['requests'])
        for r in self.w['requests']:self.events.append(dict(event='release',time=0,request=r['id']))
        return [Request(r['pickup'],r['dropoff'],r['id']) for r in self.w['requests']]

    def call(self,name,*args):
        t=time.perf_counter()
        try:return getattr(self,name)(*args)
        finally:
            elapsed=time.perf_counter()-t;self.overhead_seconds+=elapsed;self.callback_seconds[name]+=elapsed
            if name=='before_planning':
                self.batch_started=time.perf_counter();self.batch_observer_start=self.overhead_seconds

    def keep_alive(self,now):
        return self.w['case']['mode']=='poisson' and now<self.w['case']['horizon']

    def before_cycle(self,p):
        while self.cursor<len(self.w['requests']):
            r=self.w['requests'][self.cursor]
            if r['release']>p.current_time:break
            p.task_queue.append(Request(r['pickup'],r['dropoff'],r['id']));self.cursor+=1
            self.events.append(dict(event='release',time=p.current_time,request=r['id'],scheduled_release=r['release']))

    def before_planning(self,p):pass

    def on_assignment(self,p,aid,request):
        rid=request.rid;r=self.ledger[rid];self.active[aid]=rid;r['assignment_events']+=1
        if r['first_assignment'] is None:r['first_assignment']=p.current_time
        self.events.append(dict(event='assignment',time=p.current_time,agent=aid,request=rid))

    def on_second_phase(self,p,aid):
        rid=self.active[aid];self.ledger[rid]['pickups']+=1
        self.events.append(dict(event='pickup',time=p.current_time,agent=aid,request=rid))

    def on_requeue(self,p,aid,request,phase):
        rid=self.active.pop(aid);self.ledger[rid]['requeues']+=1
        self.events.append(dict(event='requeue',time=p.current_time,agent=aid,request=rid,phase=phase))
        return Request(*request,rid)

    def on_rollback(self,p,failed,blocker):
        self.rollbacks+=1;self.events.append(dict(event='rollback',time=p.current_time,failed=failed,blocker=blocker))

    def on_completion(self,p,aid):
        rid=self.active.pop(aid);self.ledger[rid]['completion']=p.current_time
        self.events.append(dict(event='completion',time=p.current_time,agent=aid,request=rid))

    def attach_segment_timer(self,p):
        original=p.segment_planner._plan_segment
        def measured(*args,**kwargs):
            t=time.perf_counter();answer=None
            try:
                answer=original(*args,**kwargs);return answer
            finally:
                elapsed=time.perf_counter()-t;record_start=time.perf_counter()
                self.segment_calls.append(dict(time=p.current_time,seconds=elapsed,
                    returned_path=bool(answer is not None and answer[0])))
                self.overhead_seconds+=time.perf_counter()-record_start
        p.segment_planner._plan_segment=measured

    def before_advance(self,p):
        inclusive=time.perf_counter()-self.batch_started
        seconds=max(0.,inclusive-(self.overhead_seconds-self.batch_observer_start))
        self.batch_seconds.append(seconds);self.batch_inclusive.append(inclusive)
        self.pending=dict(time=p.current_time,positions={a:list(p.agv_positions[a]) for a in self.agents},
                          assigned={a:dict(request=self.active[a],phase=t['phase'],status=t['status']) for a,t in p.agv_tasks.items()},
                          queued=[r.rid for r in p.task_queue],planning_seconds=seconds)

    def after_cycle(self,p):
        f=self.pending;dt=p.current_time-f['time'];queued=f.pop('queued')
        for rid in queued:self.ledger[rid]['queue_wait']+=dt
        for aid,state in f['assigned'].items():
            r=self.ledger[state['request']]
            key='assigned_wait' if tuple(f['positions'][aid])==tuple(p.agv_positions[aid]) else 'movement_time'
            r[key]+=dt
        f.update(next_time=p.current_time,duration=dt,next_positions={a:list(p.agv_positions[a]) for a in self.agents},
                 queue_length=len(queued),backlog=len(queued)+len(f['assigned']),completed=len(p.completed_tasks))
        self.timeline.append(f);self.pending=None
        if len(self.timeline)%10==0:
            write_json(self.out/'progress.json',dict(status='running',observed_time=p.current_time,
                completed=len(p.completed_tasks),arrived=self.cursor,queued=len(p.task_queue),active=len(p.agv_tasks),
                elapsed_seconds=time.perf_counter()-self.started))

    def results(self,p,status):
        end=p.current_time;arrived=self.w['requests'][:self.cursor];queued=[r.rid for r in p.task_queue]
        active=list(self.active.values());done=[r['id'] for r in self.ledger.values() if r['completion'] is not None]
        ids=queued+active+done;expected=[r['id'] for r in arrived]
        ledger_ok=len(ids)==len(set(ids)) and set(ids)==set(expected) and len(done)==len(p.completed_tasks)
        assigned_ok=p.total_assigned_tasks==len(done)+len(active)
        complete=end==self.w['case']['horizon'] and sum(x['duration'] for x in self.timeline)==end
        for rid in expected:
            r=self.ledger[rid];r['waiting_time']=r['queue_wait']+r['assigned_wait']
            r['flow_time']=None if r['completion'] is None else r['completion']-r['release']
            r['restricted_flow_time']=(end if r['completion'] is None else r['completion'])-r['release']
            r['right_censored']=r['completion'] is None
            r['state']='completed' if rid in done else ('queued' if rid in queued else 'active')
        realized=[self.ledger[i] for i in expected];completed=[self.ledger[i] for i in done]
        time_balance_ok=all(abs(r['queue_wait']+r['assigned_wait']+r['movement_time']-r['restricted_flow_time'])<1e-8 for r in realized)
        avg=lambda x:float(np.mean(x)) if x else None
        trace_mean=lambda k:sum(x[k]*x['duration'] for x in self.timeline)/end if end else None
        eligible=status=='completed' and complete and ledger_ok and assigned_ok and time_balance_ok
        row=dict(case=self.w['case']['name'],seed=self.w['seed'],status=status if eligible or status!='completed' else 'invalid_ledger_or_horizon',
            fleet=len(p.agv_info),map=self.w['case']['map'],tiles=self.w['case']['tiles'],width=self.w['width'],height=self.w['height'],
            mode=self.w['case']['mode'],arrival_rate=self.w['case']['arrival_rate'],horizon=self.w['case']['horizon'],warmup=0,
            observed_time=end,eligible=eligible,arrived=self.cursor,generated=len(self.w['requests']),completed=len(done),
            unfinished=self.cursor-len(done),final_queue=len(queued),active_tasks=len(active),source_total_assigned=p.total_assigned_tasks,
            throughput=p.get_throughput() if eligible else None,partial_throughput=p.get_throughput(),
            source_success_percent=100*len(done)/p.total_assigned_tasks if p.total_assigned_tasks else 0.,
            completion_fraction=len(done)/self.cursor if self.cursor else None,
            actual_arrival_rate=self.cursor/end if end and self.w['case']['mode']=='poisson' else None,
            waiting_time=avg([r['waiting_time'] for r in completed]),flow_time=avg([r['flow_time'] for r in completed]),
            restricted_flow_time=avg([r['restricted_flow_time'] for r in realized]),
            queue_length=trace_mean('queue_length'),backlog=trace_mean('backlog'),
            assignment_events=sum(r['assignment_events'] for r in realized),requeues=sum(r['requeues'] for r in realized),
            rollbacks=self.rollbacks,planning_seconds=sum(self.batch_seconds),planning_inclusive_seconds=sum(self.batch_inclusive),
            batch_planning_mean=avg(self.batch_seconds),batch_planning_p95=float(np.quantile(self.batch_seconds,.95)) if self.batch_seconds else None,
            segment_calls=len(self.segment_calls),segment_seconds=sum(x['seconds'] for x in self.segment_calls),
            segment_mean=avg([x['seconds'] for x in self.segment_calls]),
            segment_p95=float(np.quantile([x['seconds'] for x in self.segment_calls],.95)) if self.segment_calls else None,
            observer_seconds=self.overhead_seconds,assignment_observer_seconds=self.callback_seconds.get('on_assignment',0.),
            complete_horizon=complete,ledger_valid=ledger_ok,source_assigned_identity=assigned_ok,time_balance_valid=time_balance_ok)
        write_json(self.out/'requests.json',realized)
        for name,records in [('events',self.events),('timeline',self.timeline),('segment_calls',self.segment_calls)]:
            with gzip.open(self.out/(name+'.jsonl.gz'),'wt',encoding='utf-8') as f:
                for record in records:f.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
        return row
