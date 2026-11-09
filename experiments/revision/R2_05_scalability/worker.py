"""One process, one trial. Original planner with minimal release/recording integration."""
import argparse,platform,sys,time,traceback
from pathlib import Path
import numpy as np
from experiments.revision.R2_05_scalability.common import ROOT, read_json, write_json, execution_hash, execution_sources, native_state
from experiments.revision.R2_05_scalability.original_runtime import load_original, source_audit
from experiments.revision.R2_05_scalability.protocol import geometry
from experiments.revision.R2_05_scalability.recorder import Recorder

def execute(job):
    out=Path(job['output']);w=read_json(job['workload']);start=time.perf_counter()
    load_original()
    from experiments.revision.R2_05_scalability.integration.path_planner_lifelong import LifelongPlanner
    from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.benchmark_loader import GridMap
    grid=GridMap(w['width'],w['height'],1);grid.grid=np.array(w['grid'],dtype=int)
    recorder=Recorder(w,out);p=LifelongPlanner(grid,w['agv_info'],{a:tuple(v) for a,v in w['initial_positions'].items()},
                        recorder.initial_queue(),use_priority_replan=True,experiment=recorder)
    recorder.attach_segment_timer(p)
    write_json(out/'environment.json',dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
        processor=platform.processor(),source_hash=execution_hash(),source_files=execution_sources(),
        trial_wall_timeout=None,max_expand_enabled=False,purpose=job['purpose']))
    error=None;status='completed';loop_start=time.perf_counter()
    try:p.run_lifelong(max_time=w['case']['horizon'])
    except BaseException as e:
        status='interrupted' if isinstance(e,KeyboardInterrupt) else 'error';error=traceback.format_exc();print(error,flush=True)
    loop_wall=time.perf_counter()-loop_start
    try:
        row=recorder.results(p,status)
        row.update(native_loop_wall_seconds=loop_wall,native_assignment_seconds=p.total_assignment_time,
            original_formula_pure_seconds=loop_wall-p.total_assignment_time,
            observer_adjusted_pure_seconds=loop_wall-p.total_assignment_time-(recorder.overhead_seconds-recorder.callback_seconds.get('on_assignment',0.)),
            purpose=job['purpose'],execution_hash=execution_hash(),workload_hash=w['workload_hash'],
            native_state_hash=__import__('common').digest(native_state(p)))
        write_json(out/'final_native_state.json',native_state(p))
    except BaseException:
        row=dict(status='recording_error',eligible=False,case=w['case']['name'],seed=w['seed'],observed_time=p.current_time,
                 purpose=job['purpose'],execution_hash=execution_hash(),workload_hash=w['workload_hash'])
        error=(error or '')+'\n'+traceback.format_exc();print(error,flush=True)
    row['worker_wall_seconds']=time.perf_counter()-start
    write_json(out/'result.json',dict(row=row,error=error))
    print('RESULT '+str(row),flush=True)
    return 0 if row.get('eligible') else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);a=parser.parse_args()
    raise SystemExit(execute(read_json(a.job)))
