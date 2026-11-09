"""Sequential R2-05 trials; never sets a trial timeout or search budget."""
import argparse,csv,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from experiments.revision.R2_05_scalability.common import ROOT, read_json, write_json, digest, execution_hash, execution_sources
from experiments.revision.R2_05_scalability.protocol import cases, build_workload, FORMAL_SEEDS, SMOKE_SEEDS
from experiments.revision.R2_05_scalability.original_runtime import source_audit


def check_gate():
    gate=read_json(ROOT/'validation/baseline_gate.json')
    if not gate.get('behavior_gate_passed') or not gate.get('parity_passed'):
        raise RuntimeError('Native baseline/adapter equivalence gate is not passed')
    if gate['execution_hash']!=execution_hash():raise RuntimeError('Runtime source changed since baseline/parity validation')
    if not all(x['matches'] for x in source_audit()):raise RuntimeError('Original source bytes changed')
    return gate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--formal',action='store_true');g.add_argument('--smoke',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--dry-run',action='store_true')
    p.add_argument('--cases',nargs='+',help='Explicit condition subset; no changes to condition definitions')
    p.add_argument('--seeds',nargs='+',type=int,help='Subset of the frozen seeds for the selected purpose')
    p.add_argument('--resume',action='store_true');p.add_argument('--retry-incomplete',action='store_true')
    p.add_argument('--stop-after',type=int,help='Pause between trials after this many newly completed trials; no per-trial limit')
    a=p.parse_args();purpose='formal' if a.formal else 'smoke';allowed=FORMAL_SEEDS if a.formal else SMOKE_SEEDS
    selected_seeds=a.seeds or allowed
    if not set(selected_seeds)<=set(allowed):p.error('Seed is not in the frozen '+purpose+' seed set')
    selected=[c for c in cases() if not a.cases or c['name'] in a.cases]
    if a.cases and set(a.cases)!={c['name'] for c in selected}:p.error('Unknown case name')
    if a.retry_incomplete and not a.resume:p.error('--retry-incomplete requires --resume')
    if a.stop_after is not None and a.stop_after<1:p.error('--stop-after must be a positive integer')
    frozen=read_json(ROOT/'configs'/('formal.json' if a.formal else 'smoke.json'))
    if frozen['cases']!=cases() or frozen['seeds']!=allowed:p.error('Frozen JSON configuration differs from protocol.py')
    gate=check_gate()
    planned=[dict(case=c['name'],seed=s) for c in selected for s in selected_seeds]
    spec=dict(schema=1,purpose=purpose,cases=selected,seeds=selected_seeds,horizon=500,warmup=0,
              execution_hash=execution_hash(),source_files=execution_sources(),trial_timeout=None,
              planned_trials=planned,baseline_gate=gate)
    out=a.output.resolve()
    if (out/'manifest.json').exists():
        if not a.resume:p.error('Output exists: use --resume, or a new directory')
        old=read_json(out/'manifest.json')
        if digest(old['spec'])!=digest(spec):p.error('Resume spec/hash mismatch; use the same case/seed selection and runtime')
        manifest=old
    else:
        if out.exists() and any(out.iterdir()):p.error('Refusing to overwrite a nonempty directory')
        out.mkdir(parents=True,exist_ok=True)
        manifest=dict(spec=spec,created_utc=datetime.now(timezone.utc).isoformat(),trials=[])
        for c in selected:
            for s in selected_seeds:
                key=c['name']+'__seed'+str(s);wpath=out/'workloads'/(key+'.json')
                w=build_workload(c,s);write_json(wpath,w)
                manifest['trials'].append(dict(key=key,case=c['name'],seed=s,workload=wpath.relative_to(out).as_posix(),
                                              workload_hash=w['workload_hash'],state='planned',attempts=[]))
        write_json(out/'manifest.json',manifest)
    print(purpose.upper(),len(planned),'trials; 500 steps, warmup=0; NO trial timeout.',flush=True)
    if a.dry_run:
        print('Plan and inputs saved. Zero simulations executed.');return 0
    newly_completed=0
    for trial in manifest['trials']:
        completed=[x for x in trial['attempts'] if x.get('state')=='completed']
        if completed:
            record=read_json(out/completed[0]['directory']/'result.json')['row']
            if record.get('eligible') and record.get('execution_hash')==execution_hash():continue
            raise RuntimeError('Saved completed result is inconsistent: '+trial['key'])
        if trial['attempts'] and not a.retry_incomplete:
            print('Retained incomplete attempt; inspect it, then use --resume --retry-incomplete if intended:',trial['key']);return 2
        folder=Path('trials')/trial['key']/('attempt_%02d'%(len(trial['attempts'])+1));dest=out/folder;dest.mkdir(parents=True,exist_ok=False)
        job=dict(workload=str((out/trial['workload']).resolve()),output=str(dest.resolve()),purpose=purpose)
        write_json(dest/'job.json',job)
        attempt=dict(directory=folder.as_posix(),state='running',started_utc=datetime.now(timezone.utc).isoformat())
        trial['attempts'].append(attempt);trial['state']='running';write_json(out/'manifest.json',manifest)
        started=time.perf_counter();print('START',trial['key'],flush=True)
        with (dest/'native.log').open('w',encoding='utf-8',buffering=1) as log:
            env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
            process=subprocess.Popen([sys.executable,'-u','-m','experiments.revision.R2_05_scalability.worker','--job',str(dest/'job.json')],
                                     cwd=ROOT.parents[2],stdout=log,stderr=subprocess.STDOUT,env=env)
            attempt['pid']=process.pid;write_json(out/'manifest.json',manifest)
            try:code=process.wait()  # No timeout, forced termination or automatic retry.
            except KeyboardInterrupt:
                attempt.update(state='parent_interrupted',returncode=process.poll(),elapsed_seconds=time.perf_counter()-started)
                trial['state']='interrupted';write_json(out/'manifest.json',manifest)
                print('Interrupted. Logs/PID retained; no automatic kill. Inspect before retrying.');return 130
        elapsed=time.perf_counter()-started;attempt.update(returncode=code,elapsed_seconds=elapsed,
            finished_utc=datetime.now(timezone.utc).isoformat())
        if (dest/'result.json').exists():
            result=read_json(dest/'result.json');result['row']['trial_wall_seconds']=elapsed
            result['row']['worker_returncode']=code;write_json(dest/'result.json',result)
            state='completed' if code==0 and result['row'].get('eligible') else result['row'].get('status','error')
        else:state='exited_without_result'
        attempt['state']=trial['state']=state;write_json(out/'manifest.json',manifest)
        print('END',trial['key'],state,'wall=%.2fs'%elapsed,flush=True)
        if state!='completed':
            print('Stopped after an incomplete/error trial. Nothing was deleted or automatically retried.');return 2
        newly_completed+=1
        if a.stop_after is not None and newly_completed>=a.stop_after:
            print('Requested pause BETWEEN completed trials. Resume the same manifest when ready.');return 0
    print('All selected trials completed. Run analyze.py and plot_results.py on this directory.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
