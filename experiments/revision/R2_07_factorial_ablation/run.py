#!/usr/bin/env python3
"""R2-07: 16 variants x 3 original maps x 30 seeds. No per-trial wall limit."""
import argparse
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
import pandas as pd
from experiments.revision.R2_07_factorial_ablation.workload import plan_cases, build_workload, variants, write_json, ROOT
from experiments.revision.R2_07_factorial_ablation.verify_sources import verify

def prepare(a):
    checks=verify();cfg=json.loads((ROOT/'configs/experiment.json').read_text(encoding='utf-8'))
    seeds=[a.seed_start] if a.smoke else list(range(a.seed_start,a.seed_start+a.seeds))
    cases=plan_cases(smoke=a.smoke);vv=variants()
    plan=dict(revision='R2-07',baseline=cfg['baseline'],cases=cases,variants=vv,seeds=seeds,smoke=a.smoke,
              horizon=24 if a.smoke else 500,warmup=0,wall_timeout=None,bootstrap=200 if a.smoke else cfg['bootstrap'],
              code_hash=checks['source_fingerprint'],expected_trials=len(cases)*len(seeds)*16)
    out=(a.output or ROOT/('smoke_results' if a.smoke else ('formal_plan' if a.dry_run else 'results_formal'))).resolve()
    out.mkdir(parents=True,exist_ok=True);mp=out/'run_manifest.json'
    if mp.exists():assert json.loads(mp.read_text(encoding='utf-8'))['plan']==plan,'Source/plan changed; use a new output folder'
    else:write_json(mp,dict(plan=plan,environment=dict(python=sys.version,platform=platform.platform()),unit='independent seed'))
    trial_rows=[]
    for c in cases:
        for seed in seeds:
            w=build_workload(c,seed);wp=f'workloads/{c["name"]}_{seed}.json';write_json(out/wp,w)
            order=vv.copy();random.Random(f'{c["name"]}/{seed}/order').shuffle(order)
            for v in order:
                key=f'{c["name"]}_{seed}_{v["name"]}'
                job=dict(trial_id=key,case=c['name'],map=c['map'],seed=seed,variant=v,workload=wp,
                    result=f'runs/{key}.json',checkpoint=f'checkpoints/{key}.json',log=f'logs/{key}.log',
                    workload_hash=w['workload_hash'],code_hash=plan['code_hash'],horizon=c['horizon'],warmup=0)
                write_json(out/f'jobs/{key}.json',job)
                trial_rows.append(dict(trial_id=key,case=c['name'],map=c['map'],fleet=c['fleet'],seed=seed,variant=v['name'],
                    **{k:v[k] for k in ['S','L','P','R']},horizon=c['horizon'],warmup=0,backlog=c['backlog'],
                    workload_hash=w['workload_hash'],code_hash=plan['code_hash'],job=f'jobs/{key}.json'))
    pd.DataFrame(trial_rows).to_csv(out/'trial_plan.csv',index=False)
    return out,plan,trial_rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smoke',action='store_true');p.add_argument('--formal',action='store_true');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--seeds',type=int,default=30);p.add_argument('--seed-start',type=int,default=39);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.seeds<1 or a.seed_start<0 or (a.smoke and a.formal):p.error('Invalid seeds or mode')
    out,plan,rows=prepare(a)
    print(json.dumps(dict(expected_trials=plan['expected_trials'],seeds=plan['seeds'],smoke=a.smoke,horizon=plan['horizon'],warmup=0,wall_timeout=None,output=str(out)),indent=2),flush=True)
    if a.dry_run:
        print('DRY RUN: generated workloads, jobs and trial_plan.csv; no worker launched.',flush=True);return
    for entry in rows:
        jobfile=out/entry['job'];job=json.loads(jobfile.read_text(encoding='utf-8'));target=out/job['result']
        if target.exists():
            saved=json.loads(target.read_text(encoding='utf-8'))['row']
            assert saved['code_hash']==plan['code_hash'] and saved['workload_hash']==entry['workload_hash']
            print('RETAIN',entry['trial_id'],saved['status'],flush=True);continue
        log=out/job['log'];log.parent.mkdir(exist_ok=True)
        print('START',entry['trial_id'],flush=True)
        write_json(out/'current_trial.json',dict(trial_id=entry['trial_id'],state='running',started_unix=time.time()))
        interrupted=False
        captured=[]
        with log.open('w',encoding='utf-8') as stream:
            proc=subprocess.Popen([sys.executable,'-u','-m','experiments.revision.R2_07_factorial_ablation.worker','--job',str(jobfile)],cwd=ROOT.parents[2],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            try:
                for line in proc.stdout:
                    captured.append(line);stream.write(line);stream.flush()
                rc=proc.wait()
            except KeyboardInterrupt:
                # User cancellation only; no timer or automatic termination path.
                interrupted=True;proc.terminate();rc=proc.wait()
            finally:
                stream.flush();os.fsync(stream.fileno());proc.stdout.close()
        # Validate the exact captured console bytes, without reconstructing output from results.
        assert log.read_text(encoding='utf-8')==''.join(captured),'Console persistence mismatch'
        if not target.exists() or rc!=0:
            if target.exists():partial=json.loads(target.read_text(encoding='utf-8'))
            elif (out/job['checkpoint']).exists():partial=json.loads((out/job['checkpoint']).read_text(encoding='utf-8'))
            else:partial={'row':{}}
            partial['row'].update(trial_id=entry['trial_id'],case=entry['case'],map=entry['map'],seed=entry['seed'],variant=entry['variant'],
                **{k:entry[k] for k in ['S','L','P','R']},workload_hash=entry['workload_hash'],code_hash=plan['code_hash'],
                status='interrupted' if interrupted else (partial['row'].get('status') if partial['row'].get('status') in ['error','incomplete','invalid'] else 'error'),returncode=rc)
            write_json(target,partial)
        status=json.loads(target.read_text(encoding='utf-8'))['row']['status']
        write_json(out/'current_trial.json',dict(trial_id=entry['trial_id'],state=status,returncode=rc))
        print('END',entry['trial_id'],status,flush=True)
        if interrupted:break
    from experiments.revision.R2_07_factorial_ablation.audit_results import collect
    collect(out)
    print('Saved. Next: python postprocess.py '+str(out),flush=True)

if __name__=='__main__':main()
