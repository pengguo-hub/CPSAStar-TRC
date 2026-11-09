"""One original Lifelong trial with minimal input/recording hooks, no timeout."""
import argparse,inspect,json,os,platform,time,traceback
from pathlib import Path
import sys
import numpy as np
from common import read_json,native_state
from original_runtime import load_original
from workload import grid_for,write_json,digest
from provenance import verify_job
from observations import Recorder
from mechanism import attach_plan_observer

def execute(job):
    w,sources=verify_job(job);started=time.perf_counter();out=Path(job['result']).parent
    _,_,imports=load_original()
    from integration.path_planner_lifelong import LifelongPlanner
    p=None;rec=None;error=None;status='completed';loop_wall=None
    try:
        rec=Recorder(w,out,job['variant'])
        p=LifelongPlanner(grid_for(w['case']['map']),{a:dict(speed=1.) for a in w['initial_positions']},
             {a:tuple(v) for a,v in w['initial_positions'].items()},rec.initial_queue(),use_priority_replan=True,experiment=rec)
        rec.attach_segment_timer(p);attach_plan_observer(p,rec,job['variant'])
        begin=time.perf_counter()
        try:p.run_lifelong(max_time=w['case']['horizon'])
        except BaseException as exc:
            status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'error';error=traceback.format_exc();print(error,flush=True)
        loop_wall=time.perf_counter()-begin
        result=rec.results(p,status)
        assignment=getattr(p,'total_assignment_time',0.)
        result['row'].update(native_loop_wall_seconds=loop_wall,native_assignment_seconds=assignment,
            original_formula_pure_seconds=loop_wall-assignment,
            observer_adjusted_pure_seconds=loop_wall-assignment-(rec.overhead_seconds-rec.callback_seconds.get('on_assignment',0.)),
            native_state_hash=digest(native_state(p)))
        result['native_state']=native_state(p);write_json(out/'final_native_state.json',native_state(p))
    except BaseException as exc:
        status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'error'
        error=(error or '')+'\n'+traceback.format_exc();print(error,flush=True)
        result=dict(row=dict(status=status,eligible=False,requested_horizon=w['case']['horizon'],
            observed_time=getattr(p,'current_time',0.)),requests=list(rec.ledger.values()) if rec else [],
            events=rec.events if rec else [],timeline=rec.timeline if rec else [])
    result['row'].update({k:job[k] for k in ['case','seed','variant','purpose','code_hash','job_hash','workload_hash']})
    result['row'].update(attempt_id=job['attempt_id'],worker_wall_seconds=time.perf_counter()-started)
    result['error']=error;result['execution_sources']=sources
    result['runtime_imports']=dict(imports,integration=str(Path(inspect.getfile(LifelongPlanner)).resolve()))
    result['environment']=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),processor=platform.processor(),cpu_count=os.cpu_count())
    result['settings']=dict(soft_congestion=job['variant']=='full',original_reservations=True,persistent_hold_fix_applied=False,
        wait_penalty_coefficient=1 if job['variant']=='full' else 0,
        local_priority_congestion_coefficient=.5 if job['variant']=='full' else 0,
        field_computation_retained=True,lookahead=False,rollback=True,max_wait=2,max_expand_enabled=False,
        trial_wall_timeout=None,physical_validation_performed=False,static_feasibility_precheck=False,warmup=0)
    write_json(job['result'],result);print('RESULT '+json.dumps(result['row'],ensure_ascii=False),flush=True)
    return 0 if result['row'].get('eligible') else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',type=Path,required=True);a=p.parse_args()
    raise SystemExit(execute(read_json(a.job)))
