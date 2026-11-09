"""Audit existing runs and compare arms / OD modes. No simulations are launched."""
from pathlib import Path
from collections import Counter
import argparse,itertools,json
import numpy as np
import pandas as pd
from scipy.stats import t,ttest_1samp
from experiments.revision.R2_04_operational_metrics.workload import write_json, digest, validate_workload
from experiments.revision.R2_04_operational_metrics.provenance import cached_result, execution_sources, file_hash

PRIMARY=['throughput','waiting_time','flow_time','queue_length']
AUX=['queue_waiting_time','execution_stall_time','movement_time','active_stalled_queue','mean_active_fraction','completed_only_service_time','completed_only_flow','completed','unfinished_fraction','planning_seconds','requeues']
def close(a,b):assert np.isclose(a,b,rtol=1e-10,atol=1e-8),(a,b)
def audit_one(result,w):
    r=result['row'];H=w['case']['horizon'];req={q['id']:q for q in result['requests']};frames=result['executed_frames'];trace=result['timeline'];events=result['events']
    assert len(req)==3000 and len(trace)==500 and len(frames)==501
    assert frames[0]['positions']==w['initial_positions'];assert digest(result['native_state'])==r['native_state_hash']
    for q in w['requests']:assert all(req[q['id']][k]==v for k,v in q.items())
    qset=set();active={};done=set();released=set();phase={};qwait=Counter();stall=Counter();move=Counter();assign=Counter();rq=Counter();i=0
    def event(e):
        k=e['event'];rid=e.get('request');aid=e.get('agent');now=e['time']
        if k=='release':assert rid not in released and now==req[rid]['release'];released.add(rid);qset.add(rid)
        elif k=='assignment':
            assert rid in qset and aid not in active;qset.remove(rid);active[aid]=rid;phase[aid]='pickup';assign[rid]+=1
            if assign[rid]==1:assert req[rid]['first_assignment']==now
        elif k=='pickup':assert active[aid]==rid and phase[aid]=='pickup' and frames[int(now)]['positions'][aid]==req[rid]['pickup'];phase[aid]='dropoff'
        elif k=='requeue':assert active.pop(aid)==rid;phase.pop(aid);qset.add(rid);rq[rid]+=1
        elif k=='completion':
            assert active.pop(aid)==rid and phase.pop(aid)=='dropoff' and rid not in done and frames[int(now)]['positions'][aid]==req[rid]['dropoff'] and req[rid]['completion']==now;done.add(rid)
        elif k=='plan':assert active.get(aid)==rid and e['wait_field_enabled']==(r['variant']=='full')
    for now,f in enumerate(trace):
        assert f['time']==now and f['duration']==1 and f['next_time']==now+1
        assert f['positions']==frames[now]['positions'] and f['next_positions']==frames[now+1]['positions']
        while i<len(events) and events[i]['time']<=now:event(events[i]);i+=1
        assert len(qset)==f['queue_length']
        if 'queued_ids' in f:assert qset==set(f['queued_ids']) and len(qset)==len(f['queued_ids'])
        assert active=={a:z['request'] for a,z in f['assigned'].items()};assert len(qset)+len(active)==f['backlog']
        for rid in qset:qwait[rid]+=1
        for aid,rid in active.items():
            if f['positions'][aid]==f['next_positions'][aid]:stall[rid]+=1
            else:move[rid]+=1
    while i<len(events):event(events[i]);i+=1
    assert len(done)==r['completed'] and len(qset)==r['final_queue'] and len(active)==r['active_tasks']
    assert len(done)+len(qset)+len(active)==r['arrived']==r['generated']==3000
    for rid,q in req.items():
        assert qwait[rid]==q['queue_wait'] and stall[rid]==q['assigned_wait'] and move[rid]==q['movement_time']
        assert assign[rid]==q['assignment_events'] and rq[rid]==q['requeues']
        assert qwait[rid]+stall[rid]+move[rid]==(q['completion'] if q['completion'] is not None else H)-q['release']
    close(r['throughput'],len(done)/H);close(r['waiting_time'],sum(qwait.values())/3000+sum(stall.values())/3000)
    close(r['flow_time'],sum((q['completion'] if q['completion'] is not None else H)-q['release'] for q in req.values())/3000)
    close(r['queue_length'],sum(f['queue_length'] for f in trace)/H);close(r['flow_time'],r['waiting_time']+r['movement_time'])
    close(r['flow_time'],(r['queue_length']+r['assigned_wip'])*H/3000)
    close(r['static_congestion_potential'],w['reference_overlap'])
    assert result['settings']['wait_penalty_coefficient']==(1 if r['variant']=='full' else 0)
    assert result['settings']['local_priority_congestion_coefficient']==(.5 if r['variant']=='full' else 0)
    return dict(verified=True,requests=3000,intervals=500,frames=501)
def ci(x):
    x=np.asarray(x,float);mu=float(x.mean()) if len(x) else np.nan
    if len(x)<2:return mu,np.nan,np.nan
    h=t.ppf(.975,len(x)-1)*x.std(ddof=1)/np.sqrt(len(x));return mu,mu-h,mu+h
def signflip(x):
    x=np.asarray(x,float)
    if len(x)>20:return np.nan
    return float(np.mean([abs(np.mean(x*np.array(s)))>=abs(x.mean())-1e-12 for s in itertools.product([-1,1],repeat=len(x))])) if len(x)>1 else np.nan
def summarize(g,metric,kind,group):
    a,al,ah=ci(g.left);b,bl,bh=ci(g.right);v,lo,hi=ci(g.delta)
    return dict(comparison=kind,group=group,metric=metric,n=len(g),left_mean=a,left_ci_low=al,left_ci_high=ah,right_mean=b,right_ci_low=bl,right_ci_high=bh,
                mean_difference=v,ci95_low=lo,ci95_high=hi,relative_difference_percent=100*v/b if b else np.nan,
                p_exact=signflip(g.delta),p_paired_t=float(ttest_1samp(g.delta,0).pvalue) if len(g)>1 and g.delta.std()>0 else np.nan,
                status='estimable' if len(g)>1 else 'one_seed_descriptive_only')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',type=Path);a=ap.parse_args();out=a.results
    m=json.loads((out/'run_manifest.json').read_text());p=m['plan'];assert m['execution_sources']==execution_sources(),'Runtime differs; use the exact saved source snapshot'
    for name,h in m['execution_sources'].items():assert file_hash(out/'source_snapshot'/name)==h
    audits=[];rows=[]
    for c in p['cases']:
      for seed in p['seeds']:
        w=json.loads((out/'workloads'/f'{c["name"]}_{seed}.json').read_text());validate_workload(w)
        for v in p['variants']:
            key=f'{c["name"]}_{seed}_{v}';j=json.loads((out/'jobs'/f'{key}.json').read_text());j['workload_file']=str((out/'workloads'/f'{c["name"]}_{seed}.json').resolve())
            attempts=list((out/'attempts'/key).glob('*/attempt.json'))
            info=dict(case=c['name'],map=c['map'],fleet=c['fleet'],mode=c['od_mode'],seed=seed,variant=v,verified=False,
                      status='unfinished' if attempts else 'planned',attempt_count=len(attempts),reason='')
            try:
                result=cached_result(out,key,j)
                if result is not None:
                    info['status']=result['row']['status']
                    if info['status']=='completed':info.update(audit_one(result,w));rows.append(result['row'])
            except Exception as ex:info['status']='invalid_data';info['reason']=repr(ex)
            audits.append(info)
      print('AUDITED',c['name'],flush=True)
    return summarize_records(audits,rows,out,p['purpose'],p['seeds'])

def summarize_records(audits,rows,out,purpose,seeds):
    audit=pd.DataFrame(audits);audit['pair_valid']=audit.groupby(['case','seed']).verified.transform(lambda x:len(x)==2 and x.all());audit.to_csv(out/'trial_audit.csv',index=False)
    d=pd.DataFrame(rows);d.to_csv(out/'audited_metrics.csv',index=False)
    if d.empty:raise SystemExit('No verified complete records; inspect trial_audit.csv')
    long=[];ss=[]
    for (case,seed),g in d.groupby(['case','seed']):
        if set(g.variant)!={'full','control'}:continue
        f=g[g.variant=='full'].iloc[0];c=g[g.variant=='control'].iloc[0];assert f.workload_hash==c.workload_hash
        for metric in PRIMARY+AUX:
            if pd.notna(f.get(metric)) and pd.notna(c.get(metric)):long.append(dict(comparison='Full-Control',group=case,metric=metric,seed=seed,left=f[metric],right=c[metric],delta=f[metric]-c[metric]))
    for (mp,n,arm,seed),g in d.groupby(['map','fleet','variant','seed']):
        g=g.set_index('od_mode')
        for mode in ['intermediate','shared']:
            if 'dispersed' not in g.index or mode not in g.index:continue
            for metric in PRIMARY+AUX:
                l=g.loc[mode].get(metric);r=g.loc['dispersed'].get(metric)
                if pd.notna(l) and pd.notna(r):long.append(dict(comparison=mode+'-dispersed',group=f'{mp}_N{n}_{arm}',metric=metric,seed=seed,left=l,right=r,delta=l-r))
    ld=pd.DataFrame(long);ld.to_csv(out/'paired_seed_differences.csv',index=False)
    for (kind,group,metric),g in ld.groupby(['comparison','group','metric']):ss.append(summarize(g,metric,kind,group))
    stats=pd.DataFrame(ss)
    for _,g in stats[stats.metric.isin(PRIMARY)].groupby(['comparison','group']):
        vals=g.p_exact.dropna().sort_values();prev=0
        for k,(ix,v) in enumerate(vals.items()):prev=max(prev,(len(vals)-k)*v);stats.loc[ix,'p_holm_four']=min(1,prev)
    stats.to_csv(out/'paired_statistics.csv',index=False)
    armmeans=[]
    valid=audit[audit.pair_valid][['case','seed']].drop_duplicates()
    paired=d.merge(valid,on=['case','seed'],how='inner')
    for (case,mp,n,mode,arm),g in paired.groupby(['case','map','fleet','od_mode','variant']):
        for metric in PRIMARY+AUX:
            if metric in g and g[metric].notna().any():mu,lo,hi=ci(g[metric].dropna());armmeans.append(dict(case=case,map=mp,fleet=n,mode=mode,variant=arm,metric=metric,n=int(g[metric].notna().sum()),mean=mu,ci95_low=lo,ci95_high=hi))
    pd.DataFrame(armmeans).to_csv(out/'summary_results.csv',index=False)
    status=dict(purpose=purpose,planned=len(audit),verified=int(audit.verified.sum()),valid_pairs=int(audit.groupby(['case','seed']).pair_valid.first().sum()),all_valid=bool(audit.verified.all()),seeds=seeds,formal_experiment=purpose=='formal')
    write_json(out/'analysis_status.json',status);print(json.dumps(status,indent=2));return 0 if status['all_valid'] else 2
if __name__=='__main__':raise SystemExit(main())
