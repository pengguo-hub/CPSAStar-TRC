"""One trial using packaged original Lifelong with explicit S/L/P/R treatment switches."""
import argparse
import json
import time
import traceback
from pathlib import Path
from experiments.revision.R2_07_factorial_ablation.CPS_A_lifelong.path_planner_lifelong import LifelongPlanner
from experiments.revision.R2_07_factorial_ablation.workload import grid_for, write_json, digest
from experiments.revision.R2_07_factorial_ablation.observations import Recorder
from experiments.revision.R2_07_factorial_ablation.verify_sources import verify

def execute(job,output_root):
    root=Path(output_root);w=json.loads((root/job['workload']).read_text(encoding='utf-8'));v=job['variant']
    assert w['workload_hash']==digest({k:x for k,x in w.items() if k!='workload_hash'})
    checks=verify();assert checks['source_fingerprint']==job['code_hash']
    print(json.dumps(dict(event='trial_start',trial_id=job['trial_id'],imports=checks['imports'],code_hash=job['code_hash']),ensure_ascii=False),flush=True)
    positions={a:tuple(p) for a,p in w['initial_positions'].items()}
    recorder=Recorder(w,root/job['checkpoint'])
    planner=LifelongPlanner(grid_for(w['case']['map']),{a:{'speed':1.} for a in positions},positions,recorder.initial_queue(),
        use_priority_replan=bool(v['R']),experiment=recorder,smoothing=bool(v['S']),use_lookahead=bool(v['L']),use_priority=bool(v['P']))
    error=None;status='completed';start=time.perf_counter()
    try:planner.run_lifelong(max_time=w['case']['horizon'])
    except KeyboardInterrupt:status='interrupted';error='KeyboardInterrupt'
    except Exception:status='error';error=traceback.format_exc()
    loop_seconds=time.perf_counter()-start
    result=recorder.results(planner,status=status)
    result['row'].update(variant=v['name'],**{k:v[k] for k in ['S','L','P','R']},trial_id=job['trial_id'],code_hash=job['code_hash'],
        assignment_seconds=planner.total_assignment_time,loop_wall_seconds=loop_seconds,
        instrumented_pure_seconds=loop_seconds-planner.total_assignment_time)
    result['runtime_imports']=checks['imports'];result['error']=error
    write_json(root/job['result'],result)
    print('RESULT '+json.dumps(result['row'],ensure_ascii=False),flush=True)
    return 0 if result['row']['status']=='completed' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--job',required=True,type=Path);a=p.parse_args()
    job_path=a.job.resolve();raise SystemExit(execute(json.loads(job_path.read_text(encoding='utf-8')),job_path.parent.parent))
