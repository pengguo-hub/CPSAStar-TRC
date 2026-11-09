"""Audit all planned rows, including missing/failed trials. No physical collision test."""
import argparse,json,hashlib,math
from pathlib import Path
import numpy as np
import pandas as pd
from experiments.revision.R2_07_factorial_ablation.workload import digest, write_json, BASELINE

KEYS=['throughput','throughput_fixed_window','waiting_time','flow_time','waiting_all_arrived','restricted_flow_all_arrived','queue_length',
      'source_field_exposure','source_raw_slot_exposure','completion_fraction','planning_seconds','planning_p95','loop_wall_seconds','instrumented_pure_seconds',
      'queue_wait_all_arrived','assigned_wait_all_arrived']

def collect(output):
    out=Path(output);manifest=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'));plan=manifest['plan']
    trials=pd.read_csv(out/'trial_plan.csv');assert len(trials)==plan['expected_trials'] and not trials.trial_id.duplicated().any()
    rows=[];quality=[];fingerprints={}
    for _,e in trials.iterrows():
        job=json.loads((out/e.job).read_text(encoding='utf-8'));p=out/job['result'];w=json.loads((out/job['workload']).read_text(encoding='utf-8'))
        assert w['workload_hash']==digest({k:v for k,v in w.items() if k!='workload_hash'})==e.workload_hash
        r={k:None for k in KEYS};r.update(e.to_dict(),status='not_run',eligible=False,expected_horizon=int(e.horizon));issues=[]
        if p.exists():
            fingerprints[str(p.relative_to(out))]=hashlib.sha256(p.read_bytes()).hexdigest();result=json.loads(p.read_text(encoding='utf-8'));r.update(result['row'])
            for key in ['trial_id','case','seed','variant','workload_hash','code_hash','S','L','P','R']:
                if r.get(key)!=e[key]:issues.append('identity_mismatch:'+key)
            if r.get('status')=='completed':
                try:
                    ledger=result['requests'];trace=result['queue_trace'];frames=result['executed_frames'];end=int(e.horizon)
                    assert r['observed_time']==end and r['warmup']==0 and len(trace)==end
                    assert [t['time'] for t in trace]==list(range(end)) and all(t['duration']==1 for t in trace)
                    assert [f['time'] for f in frames]==list(range(end+1))
                    assert len(ledger)==len(w['requests'])==int(e.backlog)
                    assert len({x['id'] for x in ledger})==len(ledger)
                    completed=[x for x in ledger if x['completion'] is not None]
                    assert len(completed)==r['completed'] and r['arrived']==r['completed']+r['final_backlog']
                    events=result['events'];done=[v['request'] for v in events if v['event']=='completion']
                    assert len(done)==len(set(done))==len(completed) and set(done)=={x['id'] for x in completed}
                    for x,source in zip(ledger,w['requests']):
                        assert all(x[k]==source[k] for k in ['id','release','pickup','dropoff'])
                        observed=x['completion'] if x['completion'] is not None else end
                        assert math.isclose(x['queue_wait']+x['assigned_wait']+x['movement_time'],observed,abs_tol=1e-8)
                    assert math.isclose(sum(x['queue_wait'] for x in ledger),sum(t['queue_length']*t['duration'] for t in trace),abs_tol=1e-8)
                    def check(key,expected):
                        got=r.get(key)
                        assert (got is None and expected is None) or math.isclose(got,expected,rel_tol=1e-9,abs_tol=1e-9),key
                    avg=lambda values:float(np.mean(values)) if values else None
                    check('throughput',len(completed)/end);check('throughput_fixed_window',len(completed)/end)
                    check('waiting_time',avg([x['queue_wait']+x['assigned_wait'] for x in completed]))
                    check('flow_time',avg([x['completion'] for x in completed]))
                    check('waiting_all_arrived',avg([x['queue_wait']+x['assigned_wait'] for x in ledger]))
                    check('restricted_flow_all_arrived',avg([x['completion'] if x['completion'] is not None else end for x in ledger]))
                    for key in ['queue_length','source_field_exposure','source_raw_slot_exposure']:check(key,avg([t[key] for t in trace]))
                except (AssertionError,KeyError,TypeError,ValueError) as err:issues.append('record_audit:'+str(err))
            else:issues.append('trial_status:'+str(r.get('status')))
            log=out/job['log'];r['console_summary_present']=log.exists() and '\nRESULT ' in log.read_text(encoding='utf-8',errors='replace')
        else:issues.append('not_run')
        r['eligible']=r['status']=='completed' and not issues
        if r['status']=='completed' and issues:r['status']='invalid'
        quality.append(dict(trial_id=e.trial_id,status=r['status'],eligible=r['eligible'],reason='; '.join(issues),console_summary_present=r.get('console_summary_present',False)))
        rows.append(r)
    frame=pd.DataFrame(rows);frame.to_csv(out/'raw_results.csv',index=False);pd.DataFrame(quality).to_csv(out/'data_quality.csv',index=False)
    status=dict(expected_trials=len(trials),recorded_trials=int((frame.status!='not_run').sum()),eligible_trials=int(frame.eligible.sum()),
        status_counts={str(k):int(v) for k,v in frame.status.value_counts().items()},smoke=plan['smoke'],
        console_missing=int(((frame.status!='not_run')&~frame.get('console_summary_present',pd.Series(False,index=frame.index)).fillna(False)).sum()),
        input_fingerprint=digest(fingerprints))
    write_json(out/'completion_status.json',status);print(json.dumps(status,indent=2),flush=True)
    return frame,plan,status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();collect(a.output)
