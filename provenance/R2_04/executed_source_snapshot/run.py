"""Frozen paired R2-04 design with original Lifelong. No trial timeout."""
import argparse,json,platform,random,sys
from pathlib import Path
import pandas as pd
from workload import plan_cases,build_workload,write_json,digest,FLEETS
from provenance import ROOT,execution_sources,job_hash,file_hash,cached_result
from original_runtime import source_audit
from execution import output_lock,run_trial,emit,utc,read_optional

def gate_check():
    expected=read_optional(ROOT/'provenance/r204_baseline_files.json')
    assert expected and all(file_hash(ROOT/name)==h for name,h in expected.items()),'Supplied R2-04 baseline changed'
    assert all(r['matches'] for r in source_audit()),'Original source mismatch'
    return dict(kind='byte_identity_to_supplied_R2_04_baseline',unchanged_files=len(expected),
        planner_and_intervention_unchanged=True,new_protocol_behavior_evidence='validation/smoke_report.md')

def refresh_tables(out,manifest):
    plan=manifest['plan'];rows=[];quality=[]
    for c in plan['cases']:
      for seed in plan['seeds']:
       for variant in plan['variants']:
        key=f'{c["name"]}_{seed}_{variant}';j=read_optional(out/'jobs'/f'{key}.json')
        r=read_optional(out/'runs'/f'{key}.json')
        if r:row=r['row']
        else:
            attempts=list((out/'attempts'/key).glob('*/attempt.json'))
            row=dict(case=c['name'],seed=seed,variant=variant,map=c['map'],fleet=c['fleet'],concentration=c['concentration'],
                purpose=plan['purpose'],status='unfinished' if attempts else 'planned',eligible=False,
                requested_horizon=500,workload_hash=j['workload_hash'],code_hash=j['code_hash'],job_hash=j['job_hash'])
        rows.append(row);quality.append(dict(case=row['case'],seed=seed,variant=variant,status=row['status'],eligible=bool(row.get('eligible') and row['status']=='completed')))
    pd.DataFrame(rows).to_csv(out/'raw_results.csv',index=False);pd.DataFrame(quality).to_csv(out/'data_quality.csv',index=False)
    valid=sum(q['eligible'] for q in quality)
    write_json(out/'completion_status.json',dict(expected_trials=len(rows),validated_trials=valid,remaining_or_invalid=len(rows)-valid,
        smoke=plan['smoke'],formal_complete=plan['purpose']=='formal' and valid==len(rows),purpose=plan['purpose'],
        independent_seed_count=len(plan['seeds']),seeds=plan['seeds'],suite=plan['suite'],trial_wall_timeout=None,
        status_counts=pd.Series([r['status'] for r in rows]).value_counts().to_dict()))

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--formal',action='store_true');g.add_argument('--smoke',action='store_true')
    p.add_argument('--suite',choices=['core','stress','all'],default='all');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',type=int,default=None);p.add_argument('--seed-start',type=int,default=None)
    p.add_argument('--cases',nargs='+');p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--retry-trial',nargs='+');p.add_argument('--stop-after',type=int,help='Pause between completed trials, never truncate a trial')
    p.add_argument('--heartbeat',type=float,default=20.);p.add_argument('--workers',type=int,choices=[1],default=1,help='Sequential timing for this rebuilt protocol')
    a=p.parse_args();purpose='formal' if a.formal else 'smoke'
    n=a.seeds if a.seeds is not None else (5 if a.formal else 1)
    start=a.seed_start if a.seed_start is not None else (39 if a.formal else 7)
    if n<1 or not set(range(start,start+n))<=set(range(39,44) if a.formal else [7,8]):p.error('Formal frozen seeds are 39–43; smoke seeds are 7–8')
    if a.heartbeat<=0 or a.stop_after is not None and a.stop_after<1:p.error('Positive heartbeat / stop-after required')
    if a.retry_trial and not a.resume:p.error('--retry-trial requires --resume after inspecting old attempts')
    frozen=read_optional(ROOT/'configs/experiment.json')
    if frozen['fleets']!=FLEETS or frozen['formal_seeds']!=list(range(39,44)) or frozen['tasks']!=3000:p.error('Frozen config differs from workload.py')
    gate=gate_check();cases=plan_cases()
    if a.suite!='all':cases=[c for c in cases if c['fleet']==(min if a.suite=='core' else max)(FLEETS[c['map']])]
    if a.cases:
        if not set(a.cases)<={c['name'] for c in cases}:p.error('Case outside selected suite')
        cases=[c for c in cases if c['name'] in a.cases]
    sources=execution_sources();plan=dict(schema=4,cases=cases,seeds=list(range(start,start+n)),variants=['control','full'],
        purpose=purpose,smoke=a.smoke,pilot=False,suite=a.suite,horizon=500,warmup=0,timeout=None,execution_code_hash=digest(sources))
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    with output_lock(out):
        mp=out/'run_manifest.json'
        if mp.exists():
            if not a.resume:p.error('Output exists. Use --resume with identical selection, or a new directory')
            manifest=read_optional(mp)
            if manifest['plan']!=plan or manifest['execution_sources']!=sources:p.error('Plan/source mismatch; preserve old output and use a new directory')
        else:
            if any(x.name!='.run.lock' for x in out.iterdir()):p.error('Refusing to overwrite nonempty output')
            manifest=dict(plan=plan,execution_sources=sources,created_utc=utc(),baseline_gate=gate,
                environment=dict(python=sys.version,platform=platform.platform(),workers=1),statistical_unit='independent seed; Full/Control paired')
            write_json(mp,manifest)
            for name in sources:
                target=out/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
        jobs=[];matching=[]
        for c in cases:
          for seed in plan['seeds']:
            w=build_workload(c,seed);wf=out/'workloads'/f'{c["name"]}_{seed}.json'
            if wf.exists():assert read_optional(wf)==w,'Frozen workload changed'
            else:write_json(wf,w)
            variants=['control','full'];random.Random(f'{c["name"]}/{seed}/order').shuffle(variants)
            matching.append(dict(case=c['name'],seed=seed,workload_hash=w['workload_hash'],release_hash=w['release_hash'],
                od_hash=w['od_hash'],initial_state_hash=w['initial_state_hash'],order=','.join(variants)))
            for v in variants:
                key=f'{c["name"]}_{seed}_{v}';j=dict(case=c['name'],seed=seed,variant=v,purpose=purpose,
                    code_hash=plan['execution_code_hash'],condition=c,workload_hash=w['workload_hash'],workload_file=str(wf))
                j['job_hash']=job_hash(j);write_json(out/'jobs'/f'{key}.json',j);jobs.append((key,j))
        if not set(a.retry_trial or [])<={k for k,j in jobs}:p.error('Unknown retry key')
        pd.DataFrame(matching).to_csv(out/'workload_matching.csv',index=False)
        refresh_tables(out,manifest);emit('PLAN',purpose=purpose,trials=len(jobs),conditions=len(cases),seeds=plan['seeds'],trial_wall_timeout=None)
        if a.dry_run:emit('DRY_RUN',simulations_executed=0);return 0
        new=0
        try:
            for key,j in jobs:
                row,executed=run_trial(out,key,j,a.heartbeat,key in (a.retry_trial or []));refresh_tables(out,manifest)
                if row['status']!='completed':emit('PAUSED',reason='Incomplete or failed trial retained; inspect before proceeding');return 2
                new+=int(executed)
                if a.stop_after is not None and new>=a.stop_after:emit('PAUSED',reason='Requested pause BETWEEN complete trials');return 0
        except KeyboardInterrupt:
            refresh_tables(out,manifest);return 130
        emit('COMPLETE',trials=len(jobs),new_trials=new,purpose=purpose);return 0

if __name__=='__main__':raise SystemExit(main())
