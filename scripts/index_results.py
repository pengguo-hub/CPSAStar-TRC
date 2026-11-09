from pathlib import Path
import json,hashlib,pandas as pd
R=Path(__file__).resolve().parents[1]
def main():
 rows=[];one=[];counts={}
 for p in sorted((R/'results').rglob('*')):
  if not p.is_file() or any(x.startswith('.') for x in p.relative_to(R).parts):continue
  rel=str(p.relative_to(R));group='original_paper' if '/original_paper/' in rel else rel.split('/')[2]
  a=dict(path=rel,experiment=group,size_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),granularity='supporting input/output',row_count='',seeds='',role='unchanged source extraction')
  if p.suffix=='.csv':
   d=pd.read_csv(p);a.update(row_count=len(d),columns=';'.join(d.columns))
   if 'seed' in d:a.update(seeds=';'.join(map(str,sorted(d.seed.unique()))),granularity='task within seed' if p.name=='task_results.csv' else 'per-seed rows')
   elif 'runs' in d or 'num_seeds' in d:a['granularity']='aggregate only; per-seed outcomes absent'
   if p.name in ['raw_results.csv','seed_results.csv','joint_raw_results.csv','cross_raw_results.csv','omega_interactions_raw_results.csv']:counts[group]=counts.get(group,0)+len(d)
  if '/one_shot/' in rel and p.suffix=='.json':
   j=json.loads(p.read_text());a.update(granularity='per-algorithm per-seed',row_count=sum(len(x) for x in j['results'].values()),seeds=';'.join(map(str,j['seeds'])))
   for algo,ss in j['results'].items():
    for seed,metrics in ss.items():one.append(dict(source_file=rel,map=j['map_key'],task_count=j['task_count'],algorithm=algo,seed=int(seed),**metrics))
  if group=='R2_05_scalability' and p.name=='result.json':
   j=json.loads(p.read_text())['row'];a.update(granularity='final per-trial row',row_count=1,seeds=str(j['seed']));counts[group]=counts.get(group,0)+1
  rows.append(a)
 pd.DataFrame(rows).to_csv(R/'RESULTS_MANIFEST.csv',index=False);pd.DataFrame(one).to_csv(R/'statistics/original_one_shot_per_seed_derived.csv',index=False)
 summary=dict(revision_analysis_rows=counts,revision_analysis_row_total=sum(counts.values()),original_one_shot_algorithm_seed_rows=len(one),original_one_shot_files=len(set(x['source_file'] for x in one)),result_files=len(rows))
 (R/'statistics/result_inventory_summary.json').write_text(json.dumps(summary,indent=2));print(summary)
 keys={'R1_03_dmin':['map','task_count','d_min'],'R1_05_06_gaussian':['map','task_count','sweep','value','L','T','sigma_l','sigma_t'],'R1_07_08_delta':['map_name','num_agvs','delta','max_time'],'R1_09_retry_limit':['map','task_count','R'],'R2_02_representation':['map','task_count','representation','rollback_mode'],'R2_03_parameter_interactions':['study','map','task_count','cell','alpha','beta','gamma','omega','L','T','sigma_l','sigma_t','update_interval'],'R2_04_operational_metrics':['map','fleet','od_mode','variant','horizon']}
 for e,k in keys.items():
  d=pd.concat([pd.read_csv(p) for p in (R/'results/revision'/e).rglob('*.csv') if p.name in ['seed_results.csv','raw_results.csv','joint_raw_results.csv','cross_raw_results.csv','omega_interactions_raw_results.csv']])
  o=d.groupby(k,dropna=False).agg(n_rows=('seed','size'),n_seeds=('seed','nunique'),seeds=('seed',lambda v:';'.join(map(str,sorted(set(v)))))).reset_index();o.to_csv(R/'statistics'/(e+'_observed_conditions.csv'),index=False)
if __name__=='__main__':main()
