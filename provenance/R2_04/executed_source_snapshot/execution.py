"""Sequential subprocesses, live progress and immutable attempts; no time budget."""
import contextlib,json,os,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from workload import write_json
from provenance import ROOT,cached_result,file_hash,validate_completed
def utc():return datetime.now(timezone.utc).isoformat()
def emit(event,**fields):print(json.dumps(dict(event=event,utc=utc(),**fields),ensure_ascii=False),flush=True)
def read_optional(p):
    try:return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

@contextlib.contextmanager
def output_lock(out):
    f=(Path(out)/'.run.lock').open('a+b')
    if f.tell()==0:f.write(b'0');f.flush()
    f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:f.close()

def run_trial(out,key,job,heartbeat=20.,retry=False):
    out=Path(out);old=cached_result(out,key,job)
    if old is not None and (old['row']['status']=='completed' or not retry):
        emit('REUSED' if old['row']['status']=='completed' else 'RETAINED_FAILURE',trial=key,status=old['row']['status'])
        return old['row'],False
    base=out/'attempts'/key;base.mkdir(parents=True,exist_ok=True)
    if old is None and any(base.iterdir()) and not retry:
        raise RuntimeError('Unfinished prior attempt retained. Inspect its PID/log before explicit --retry-trial '+key)
    aid=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:12]
    dest=base/aid;dest.mkdir();started=time.perf_counter()
    j=dict(job,attempt_id=aid,result=str(dest/'result.json'))
    write_json(dest/'job.json',j)
    meta=dict(trial=key,attempt_id=aid,job_hash=job['job_hash'],code_hash=job['code_hash'],started_utc=utc(),status='running')
    write_json(dest/'attempt.json',meta)
    emit('START',trial=key,trial_wall_timeout=None,log=str(dest/'run.log'))
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONHASHSEED='0',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with (dest/'run.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-u',str(ROOT/'worker.py'),'--job',str(dest/'job.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=env)
        meta['pid']=process.pid;write_json(dest/'attempt.json',meta);nextbeat=heartbeat
        try:
            while process.poll() is None:
                elapsed=time.perf_counter()-started
                if elapsed>=nextbeat:
                    emit('HEARTBEAT',trial=key,pid=process.pid,elapsed_seconds=round(elapsed,2),last_progress=read_optional(dest/'progress.json'))
                    nextbeat=elapsed+heartbeat
                time.sleep(.1)
            code=process.wait()
        except KeyboardInterrupt:
            meta.update(status='parent_interrupted',elapsed_seconds=time.perf_counter()-started,child_returncode=process.poll())
            write_json(dest/'attempt.json',meta)
            emit('PARENT_INTERRUPTED',trial=key,pid=process.pid,note='No automatic kill. Inspect child status before retrying.')
            raise
    result=read_optional(dest/'result.json') or dict(row=dict(status='error',eligible=False),error='Worker exited without final result')
    result['row'].update({k:job[k] for k in ['case','seed','variant','purpose','code_hash','job_hash','workload_hash']})
    reason=None
    if code!=0:result['row'].update(status='interrupted' if result['row'].get('status')=='interrupted' else 'error',eligible=False);reason=f'worker exit {code}'
    elif result['row'].get('status')=='completed':
        try:validate_completed(result,j)
        except Exception as exc:result['row'].update(status='invalid',eligible=False);reason=repr(exc)
    else:result['row']['eligible']=False
    elapsed=time.perf_counter()-started
    result['row'].update(attempt_id=aid,process_wall_seconds=elapsed,worker_returncode=code,end_reason=reason)
    write_json(dest/'selected_result.json',result)
    meta.update(status=result['row']['status'],finished_utc=utc(),process_wall_seconds=elapsed,returncode=code,end_reason=reason,result_sha256=file_hash(dest/'selected_result.json'))
    write_json(dest/'attempt.json',meta)
    target=out/'runs'/f'{key}.json';write_json(target,result)
    write_json(out/'receipts'/f'{key}.json',dict(job_hash=job['job_hash'],code_hash=job['code_hash'],status=result['row']['status'],
        result_sha256=file_hash(target),attempt_directory=dest.relative_to(out).as_posix(),attempt_id=aid))
    emit('TRIAL_END',trial=key,status=result['row']['status'],elapsed_seconds=round(elapsed,3),sim_step=result['row'].get('observed_time'),completed_tasks=result['row'].get('completed'))
    return result['row'],True
