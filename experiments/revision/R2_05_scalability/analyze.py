"""Audit saved trials, then summarize independent seeds. Does not run simulations."""
import argparse,ast,csv,gzip,itertools,json,math
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t
from experiments.revision.R2_05_scalability.common import read_json, write_json, digest

METRICS=['throughput','completion_fraction','planning_seconds','source_success_percent','original_formula_pure_seconds',
         'observer_adjusted_pure_seconds','native_loop_wall_seconds','trial_wall_seconds','worker_wall_seconds',
         'segment_seconds','segment_mean','segment_p95','batch_planning_p95','waiting_time','flow_time','restricted_flow_time',
         'queue_length','backlog','arrived','completed','unfinished','final_queue','actual_arrival_rate',
         'traffic_encounter_rate','traffic_eligible_moves']

def write_csv(path,rows,fields=None):
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def gz_records(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:
            if line.strip():yield json.loads(line)

def traffic_from_trace(timeline,excluded,headway,end):
    """Offline replay of moving cell arrivals; neither collisions nor route feasibility."""
    excluded=set(map(tuple,excluded));arrivals=[]
    for frame in timeline:
        for aid,assigned in frame['assigned'].items():
            old=frame['positions'][aid];new=frame['next_positions'][aid]
            if old!=new and tuple(new) not in excluded:
                arrivals.append((frame['next_time'],aid,assigned['request'],tuple(new)))
    evidence=[]
    for t,aid,rid,node in arrivals:
        if not headway<t<=end-headway:continue
        others=[dict(agent=a,time=s) for s,a,_,q in arrivals if a!=aid and q==node and abs(s-t)<=headway]
        evidence.append(dict(time=t,agent=aid,request=rid,node=list(node),encounter=bool(others),other_arrivals=others))
    return evidence

def audit_trial(folder,w,row):
    issues=[]
    def check(ok,message):
        if not ok:issues.append(message)
    check(row.get('workload_hash')==w['workload_hash'],'workload hash differs')
    check(digest({k:v for k,v in w.items() if k!='workload_hash'})==w['workload_hash'],'input payload hash differs')
    if row.get('status')!='completed' or not row.get('eligible'):return issues+['not a complete eligible trial']
    try:
        requests=read_json(folder/'requests.json');byid={r['id']:r for r in requests}
        events=list(gz_records(folder/'events.jsonl.gz'));timeline=list(gz_records(folder/'timeline.jsonl.gz'))
        state=read_json(folder/'final_native_state.json');supplied={r['id']:r for r in w['requests']}
        check(digest(state)==row['native_state_hash'],'native final state hash differs')
        logrows=[ast.literal_eval(line[7:]) for line in (folder/'native.log').read_text(encoding='utf-8').splitlines() if line.startswith('RESULT ')]
        check(len(logrows)==1 and all(row.get(k)==v for k,v in logrows[0].items()),'log/result final record differs')
        check(len(byid)==len(requests),'duplicate ledger IDs')
        check(set(byid)==set(supplied),'ledger does not cover full input stream')
        queued=set();active={};done=set();released=set();ei=0;wait=defaultdict(float);moves=defaultdict(float);duration=0.
        def event(e):
            kind=e['event'];rid=e.get('request');aid=e.get('agent')
            if kind=='release':
                check(rid not in released,'duplicate release');released.add(rid);queued.add(rid)
                check(e['time']==supplied[rid]['release'],'release time mismatch')
            elif kind=='assignment':
                check(rid in queued and aid not in active,'invalid task assignment partition');queued.discard(rid);active[aid]=rid
            elif kind=='requeue':
                check(active.get(aid)==rid,'requeue identity mismatch');active.pop(aid,None);queued.add(rid)
            elif kind=='completion':
                check(active.get(aid)==rid and rid not in done,'completion identity mismatch')
                active.pop(aid,None);done.add(rid);check(byid[rid]['completion']==e['time'],'completion timestamp mismatch')
            elif kind=='pickup':check(active.get(aid)==rid,'pickup identity mismatch')
        for f in timeline:
            while ei<len(events) and events[ei]['time']<=f['time']:event(events[ei]);ei+=1
            check(f['time']==duration,'time trace not continuous from zero')
            check(f['duration']==1 and f['next_time']==f['time']+1,'nonunit simulation step')
            check(active=={a:s['request'] for a,s in f['assigned'].items()},'active IDs differ from event replay')
            check(len(queued)==f['queue_length'] and len(queued)+len(active)==f['backlog'],'queue/backlog count mismatch')
            dt=f['duration'];duration+=dt
            for rid in queued:wait[rid]+=dt
            for aid,rid in active.items():
                (wait if f['positions'][aid]==f['next_positions'][aid] else moves)[rid]+=dt
        while ei<len(events):event(events[ei]);ei+=1
        check(duration==500 and state['current_time']==500,'not exactly 500 steps')
        check(len(done)==row['completed']==len(state['completed_tasks']),'completed count mismatch')
        check(len(queued)==row['final_queue']==len(state['task_queue']),'final queue mismatch')
        check(len(active)==row['active_tasks']==len(state['agv_tasks']),'active count mismatch')
        check(len(done)+len(queued)+len(active)==row['arrived'],'task count conservation failure')
        check(set(queued)|set(active.values())|done==released,'final request partition mismatch')
        check(len(done)+len(active)==state['total_assigned_tasks']==row['source_total_assigned'],'source assigned identity differs')
        assigned=len(done)+len(active)
        check(abs(row['source_success_percent']-(100*len(done)/assigned if assigned else 0.))<1e-9,'native success formula differs')
        check(abs(row['throughput']-len(done)/500)<1e-12,'throughput formula mismatch')
        check(row['completion_fraction'] is None if not released else abs(row['completion_fraction']-len(done)/len(released))<1e-12,'completion fraction mismatch')
        for rid,r in byid.items():
            check(abs(wait[rid]-r['waiting_time'])<1e-9,'request waiting mismatch')
            check(abs(moves[rid]-r['movement_time'])<1e-9,'request movement duration mismatch')
            check(abs(wait[rid]+moves[rid]-r['restricted_flow_time'])<1e-9,'request lifetime mismatch')
        for metric in ['queue_length','backlog']:
            check(abs(row[metric]-sum(f[metric]*f['duration'] for f in timeline)/500)<1e-9,metric+' mean mismatch')
        check(abs(row['planning_seconds']-sum(f['planning_seconds'] for f in timeline))<1e-8,'batch timing sum mismatch')
        for metric,values in [('waiting_time',[byid[r]['waiting_time'] for r in done]),
                              ('flow_time',[byid[r]['completion']-byid[r]['release'] for r in done]),
                              ('restricted_flow_time',[r['restricted_flow_time'] for r in requests])]:
            check(row[metric] is None if not values else abs(row[metric]-sum(values)/len(values))<1e-9,metric+' mean mismatch')
        segments=list(gz_records(folder/'segment_calls.jsonl.gz'))
        check(len(segments)==row['segment_calls'],'segment call count mismatch')
        check(abs(sum(s['seconds'] for s in segments)-row['segment_seconds'])<1e-8,'segment time sum mismatch')
        if w['case']['traffic_coupling']:
            evidence=read_json(folder/'traffic_evidence.json');den=len(evidence['encounters']);num=sum(e['encounter'] for e in evidence['encounters'])
            check(traffic_from_trace(timeline,evidence['endpoint_buffer'],evidence['headway_radius'],500)==evidence['encounters'],
                  'traffic exposure differs from independent trajectory replay')
            check(den==row['traffic_eligible_moves'] and num==row['traffic_encounter_moves'],'traffic counts mismatch')
            check(row['traffic_encounter_rate'] is None if not den else abs(row['traffic_encounter_rate']-num/den)<1e-12,'traffic rate mismatch')
    except Exception as exc:issues.append('raw audit error: '+repr(exc))
    return sorted(set(issues))

def statistics(values):
    values=[float(v) for v in values if v is not None and math.isfinite(float(v))];n=len(values)
    if not n:return dict(n=0,mean=None,std=None,ci_low=None,ci_high=None)
    mean=float(np.mean(values))
    if n<2:return dict(n=n,mean=mean,std=None,ci_low=None,ci_high=None)
    std=float(np.std(values,ddof=1));half=float(student_t.ppf(.975,n-1))*std/math.sqrt(n)
    return dict(n=n,mean=mean,std=std,ci_low=mean-half,ci_high=mean+half)

def contrasts():
    return [('fleet','A_fleet30','A_fleet10'),('fleet','A_fleet30','A_fleet50'),
        ('map_fixed_fleet','A_open_base','A_map2_fixed'),('map_fixed_fleet','A_open_base','A_map3_fixed'),
        ('map_fixed_density','A_open_base','A_map2_density'),('map_fixed_density','A_open_base','A_map3_density'),
        ('arrival_rate','A_open_base','A_rate0.25'),('arrival_rate','A_open_base','A_rate1.0'),('arrival_rate','A_open_base','A_rate2.0'),
        ('traffic_coupling','B_traffic_dispersed','B_traffic_intermediate'),('traffic_coupling','B_traffic_dispersed','B_traffic_shared')]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();base=a.input.resolve();out=(a.output or base/'analysis').resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=read_json(base/'manifest.json');spec=manifest['spec'];rows=[];attempts=[];audit=[];workloads={}
    for trial in manifest['trials']:
        w=read_json(base/trial['workload']);workloads[(trial['case'],trial['seed'])]=w;chosen=False
        for attempt in trial['attempts']:
            folder=base/attempt['directory'];rpath=folder/'result.json'
            if not rpath.exists():
                attempts.append(dict(case=trial['case'],seed=trial['seed'],attempt=attempt['directory'],state=attempt['state'],eligible=False,reason='no result; retain logs/progress/PID'));continue
            r=read_json(rpath)['row'];issues=audit_trial(folder,w,r)
            if r.get('execution_hash')!=spec['execution_hash']:issues.append('source hash mismatch')
            if r.get('purpose')!=spec['purpose']:issues.append('purpose mismatch; never combine smoke and formal')
            if attempt.get('returncode')!=0:issues.append('worker exit not zero')
            valid=not issues and r.get('eligible',False)
            audit.append(dict(case=trial['case'],seed=trial['seed'],attempt=attempt['directory'],valid=valid,issues=issues))
            attempts.append(dict(case=trial['case'],seed=trial['seed'],attempt=attempt['directory'],state=r.get('status'),eligible=valid,reason='; '.join(issues)))
            if valid and not chosen:
                rows.append(dict(r,audit_valid=True,attempt_directory=str(folder)));chosen=True
        if not chosen:
            rows.append(dict(case=trial['case'],seed=trial['seed'],status=trial['state'],eligible=False,audit_valid=False,
                             purpose=spec['purpose'],reason='no completed audited attempt'))
    # Source input matching is checked independently of trajectory outcomes.
    matching=[]
    for seed in spec['seeds']:
        group=[workloads[(c,seed)] for c in ['B_traffic_dispersed','B_traffic_intermediate','B_traffic_shared'] if (c,seed) in workloads]
        if len(group)!=3:continue
        equal={k:len({w[k] for w in group})==1 for k in ['map_hash','release_hash','pickup_hash','initial_positions_hash']}
        equal['distance_sequence']=all([r['intrinsic_distance'] for r in w['requests']]==[r['intrinsic_distance'] for r in group[0]['requests']] for w in group)
        equal['destination_marginals']=all(Counter(tuple(r['dropoff']) for r in w['requests'])==Counter(tuple(r['dropoff']) for r in group[0]['requests']) for w in group)
        matching.append(dict(seed=seed,valid=all(equal.values()),checks=equal))
    summary=[];wide=[]
    for c in spec['cases']:
        allr=[r for r in rows if r['case']==c['name']];valid=[r for r in allr if r.get('audit_valid')]
        meta=dict(case=c['name'],map=c['map'],fleet=c['fleet'],tiles=c['tiles'],arrival_rate=c['arrival_rate'],mode=c['mode'],
                  n_expected=len(allr),n_valid=len(valid),purpose=spec['purpose'])
        flat=dict(meta)
        for metric in METRICS:
            stat=statistics([r.get(metric) for r in valid]);summary.append(dict(meta,metric=metric,**stat))
            for k,v in stat.items():flat[metric+'_'+k]=v
        wide.append(flat)
    paired=[]
    for family,baseline,other in contrasts():
        for metric in ['throughput','completion_fraction','planning_seconds']+(['traffic_encounter_rate'] if family=='traffic_coupling' else []):
            left={r['seed']:r.get(metric) for r in rows if r['case']==baseline and r.get('audit_valid') and r.get(metric) is not None}
            right={r['seed']:r.get(metric) for r in rows if r['case']==other and r.get('audit_valid') and r.get(metric) is not None}
            seeds=sorted(left.keys()&right.keys());d=[right[s]-left[s] for s in seeds]
            if not seeds:continue
            stat=statistics(d);pvalue=None
            if len(d)>1:
                permutations=[abs(sum(x*sgn for x,sgn in zip(d,signs))) for signs in itertools.product([-1,1],repeat=len(d))]
                pvalue=sum(x>=abs(sum(d))-1e-12 for x in permutations)/len(permutations)
            paired.append(dict(family=family,baseline=baseline,other=other,metric=metric,seeds=','.join(map(str,seeds)),
                               contrast='other minus baseline',**stat,sign_flip_p_unadjusted=pvalue))
    for family in {r['family'] for r in paired}:
        tests=sorted([r for r in paired if r['family']==family and r['sign_flip_p_unadjusted'] is not None],key=lambda x:x['sign_flip_p_unadjusted'])
        bound=0.
        for i,r in enumerate(tests):bound=max(bound,(len(tests)-i)*r['sign_flip_p_unadjusted']);r['sign_flip_p_holm']=min(1.,bound)
    write_csv(out/'trial_results.csv',rows);write_csv(out/'trial_audit.csv',attempts,fields=['case','seed','attempt','state','eligible','reason'])
    write_csv(out/'summary_long.csv',summary);write_csv(out/'summary_results.csv',wide)
    write_csv(out/'paired_contrasts.csv',paired,fields=['family','baseline','other','metric','seeds','contrast','n','mean','std','ci_low','ci_high','sign_flip_p_unadjusted','sign_flip_p_holm'])
    write_json(out/'raw_audit.json',audit);write_json(out/'traffic_matching.json',matching)
    status=dict(purpose=spec['purpose'],seeds=spec['seeds'],condition_count=len(spec['cases']),full_formal_matrix_planned=spec['purpose']=='formal' and len(spec['cases'])==14 and spec['seeds']==list(range(1001,1006)),planned_trials=len(manifest['trials']),valid_trials=sum(r.get('audit_valid',False) for r in rows),
        incomplete_or_invalid=sum(not r.get('audit_valid',False) for r in rows),execution_hash=spec['execution_hash'],
        independent_unit='seed',confidence_interval='two-sided 95% Student t interval across seeds; sample SD (ddof=1); no CI for n=1',
        sign_flip='paired exact sign-flip; Holm within each axis across listed primary metrics; with five pairs the minimum two-sided raw p is 0.0625',
        no_physical_correctness_check=True,traffic_matching_valid=all(r['valid'] for r in matching))
    write_json(out/'analysis_status.json',status)
    report=['# Result audit', '', 'Purpose: **'+spec['purpose']+'**.', '',f"Audited valid trials: {status['valid_trials']}/{status['planned_trials']}. No missing or failed trial was imputed.",
            '', 'Statistics use independent seeds, never tasks or frames. No confidence interval is computed for n=1.',
            '', 'Completion fraction is completed/released; the paper success percentage completed/net-assigned is separate.',
            '', 'Planning time is cumulative original batch work with measured observer callback time subtracted. Pure-time and total-wall scopes are separate columns.',
            '', 'These checks establish task/record consistency, not physical collision correctness.',
            '', 'Traffic labels denote fixed OD pairings, not proven low/medium/high realized congestion. Read traffic metrics and paired intervals before making a congestion-gradient claim.']
    if spec['purpose']!='formal':report+=['','**VALIDATION ONLY. Do not use these results or figures as formal manuscript evidence.**']
    (out/'audit_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps(status,indent=2));return 0 if status['incomplete_or_invalid']==0 and status['traffic_matching_valid'] else 2

if __name__=='__main__':raise SystemExit(main())
