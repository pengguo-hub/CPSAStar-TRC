"""Deterministic reanalysis of supplied outcomes; no planner/simulation imports."""
from pathlib import Path
import json,itertools,hashlib,math
import numpy as np,pandas as pd
from scipy.stats import t
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'results/revision';O=ROOT/'statistics';O.mkdir(exist_ok=True)
checks=[];effects=[];seed_effects=[]
def load(e,names):
 files=sorted(p for p in (R/e).rglob('*.csv') if p.name in names)
 return pd.concat([pd.read_csv(p) for p in files],ignore_index=True)
def summarize(x):
 x=np.array(x,dtype=float);assert np.isfinite(x).all();n=len(x);sd=x.std(ddof=1);h=t.ppf(.975,n-1)*sd/np.sqrt(n)
 return np.array([x.mean(),x.mean()-h,x.mean()+h])
def pair(a,b,metric):
 a=a.set_index('seed')[metric];b=b.set_index('seed')[metric];assert a.index.is_unique and b.index.is_unique and set(a.index)==set(b.index)
 return a.sort_index()-b.sort_index()
def add(label,x,expected,decimals=2,paired=True):
 x=pd.Series(x).sort_index();v=summarize(x);n=len(x);assert n==5,(label,n)
 for k,(value,target) in enumerate(zip(v,expected)):
  checks.append(dict(check=label,statistic=['mean','ci95_low','ci95_high'][k],calculated=value,reported=target,tolerance=.51*10**(-decimals),matches=bool(abs(value-target)<=.51*10**(-decimals))))
 signs=np.array(list(itertools.product([-1,1],repeat=n)))
 p=float(np.mean(np.abs((signs*x.to_numpy()).mean(axis=1))>=abs(x.mean())-1e-12)) if paired else np.nan
 effects.append(dict(contrast=label,mean=v[0],sd=x.std(ddof=1),n=n,ci95_low=v[1],ci95_high=v[2],p_exact_signflip=p,paired=paired,holm_family=label.split('/')[0]+'_audit_selected_paired_contrasts' if paired else 'not_tested'))
 seed_effects.extend(dict(contrast=label,seed=str(seed),effect=value) for seed,value in x.items())
def meancheck(label,value,reported,decimals):
 checks.append(dict(check=label,statistic='mean',calculated=float(value),reported=reported,tolerance=.51*10**(-decimals),matches=bool(abs(value-reported)<=.51*10**(-decimals))))
dmin=load('R1_03_dmin',['seed_results.csv']);gauss=load('R1_05_06_gaussian',['seed_results.csv']);delta=load('R1_07_08_delta',['raw_results.csv']);retry=load('R1_09_retry_limit',['raw_results.csv'])
for m,n,exp in [('A',70,[52.29,46.46,58.12]),('B',280,[74.50,73.01,75.99]),('C',200,[80.90,78.08,83.72])]:
 d=dmin[(dmin['map']==m)&(dmin.task_count==n)];add('R1_03/'+m+'_d1_minus_d3_success_pp',100*pair(d[d.d_min==1],d[d.d_min==3],'success_rate'),exp)
for m,n,exp in [('A',70,[3.93,2.97,4.90]),('B',280,[26.25,23.75,28.75]),('C',200,[18.45,17.03,19.87])]:
 d=gauss[(gauss['map']==m)&(gauss.task_count==n)&(gauss.sweep=='L')];add('R1_05_06/'+m+'_L3_minus_L1_seconds',pair(d[d.value==3],d[d.value==1],'planning_time'),exp)
for m,exp in [('STANDARD',[1.1900,1.1663,1.2137]),('FRANSEN',[4.6644,4.3976,4.9312]),('RING',[3.0712,2.9687,3.1738])]:
 d=delta[(delta.map_name==m)&(delta.delta==3)];add('R1_07_08/'+m+'_delta3_throughput',d.set_index('seed').throughput,exp,4,False)
add('R1_09/A50_R5_success_percent',retry[(retry['map']=='A')&(retry.task_count==50)&(retry.R==5)].set_index('seed').success_rate*100,[90,84.18,95.82],2,False)
rep=load('R2_02_representation',['raw_results.csv']);tasks=pd.read_csv(R/'R2_02_representation/task_results.csv')
exposure_rows=[]
for m,n,comp,exp,expexp in [('B',280,'historical_gaussian',[2.07,.29,3.86],[3.72,.48,6.96]),('B',280,'learned_gaussian',[2.64,1.15,4.13],[2.32,.15,4.50]),('B',280,'raw',[5.79,4.14,7.43],[2.93,.45,5.41]),('C',200,'raw',[6.20,3.20,9.20],[12.81,9.77,15.84])]:
 d=rep[(rep['map']==m)&(rep.task_count==n)];add('R2_02/'+m+str(n)+'_gaussian_minus_'+comp+'_success_pp',100*pair(d[d.representation=='gaussian'],d[d.representation==comp],'success_rate'),exp)
 td=tasks[(tasks['map']==m)&(tasks.task_count==n)];v={}
 for seed,g in td.groupby('seed'):
  a=g[(g.representation=='gaussian')&g.success].set_index('agv_id');b=g[(g.representation==comp)&g.success].set_index('agv_id')
  ids=a.index.intersection(b.index);assert len(ids)>0
  am=a.loc[ids,'neutral_congestion_exposure'].mean();bm=b.loc[ids,'neutral_congestion_exposure'].mean();v[seed]=100*(bm-am)/bm
  exposure_rows.append(dict(map=m,task_count=n,seed=seed,comparator=comp,common_successful_tasks=len(ids),gaussian_mean=am,comparator_mean=bm,reduction_percent=v[seed]))
 add('R2_02/'+m+str(n)+'_exposure_reduction_vs_'+comp,pd.Series(v),expexp)
pd.DataFrame(exposure_rows).to_csv(O/'R2_02_common_successful_task_audit.csv',index=False)
inter=load('R2_03_parameter_interactions',['joint_raw_results.csv','cross_raw_results.csv']);cells=[]
for (study,m,n),g in inter.groupby(['study','map','task_count']):
 baseline=g[(g.L==1)&(g['T']==1)&(g.sigma_l==2)&(g.sigma_t==2)&(g.gamma==5)&(g.update_interval==20)]
 if baseline.empty:continue
 baseline=baseline.drop_duplicates('seed')
 for cell,gg in g.groupby('cell'):
  v=pair(gg,baseline,'success_rate')*100;a=summarize(v)
  cells.append(dict(study=study,map=m,task_count=n,cell=cell,mean=a[0],ci95_low=a[1],ci95_high=a[2],seed_effects=json.dumps(v.to_dict())))
cd=pd.DataFrame(cells);cd.to_csv(O/'R2_03_all_cell_differences.csv',index=False)
for study,exp in [('sigma_l_sigma_t',[3.71,1.69,5.74]),('L_T',[-5,-8.20,-1.80]),('gamma_sigma_l',[3.43,-1.20,8.05]),('gamma_sigma_t',[-2,-9.16,5.16]),('gamma_K',[-4,-11.77,3.77])]:
 g=cd[(cd.study==study)&(((cd['map']=='A')&(cd.task_count==70))|((cd['map']=='B')&(cd.task_count==280))|((cd['map']=='C')&(cd.task_count==200)))]
 matching=g[(g[['mean','ci95_low','ci95_high']].to_numpy()-np.array(exp)).__abs__().max(axis=1)<=.0051]
 if len(matching):
  a=matching.iloc[0];add('R2_03/'+study+'/'+str(a['map'])+'/'+str(a.cell),pd.Series(json.loads(a.seed_effects)),exp)
 else:
  meancheck('R2_03/'+study+'_reported_CI_not_found',float('nan'),exp[0],2)
od=load('R2_04_operational_metrics',['raw_results.csv']);sel=od[od.fleet==od['map'].map({'STANDARD':50,'FRANSEN':200,'RING':160})]
for metric,exp,dec in [('throughput',[.1945,.1733,.2156],4),('waiting_time',[-9.39,-10.85,-7.93],2),('flow_time',[-7.58,-9.02,-6.13],2),('queue_length',[-46.92,-55.60,-38.23],2)]:
 pivot=sel.pivot(index=['seed','map','od_mode'],columns='variant',values=metric);v=(pivot['full']-pivot.control).groupby('seed').mean();add('R2_04/pooled_full_minus_control_'+metric,v,exp,dec)
man=json.loads((R/'R2_05_scalability/manifest.json').read_text());rows=[]
for trial in man['trials']:
 ats=[a for a in trial['attempts'] if a['state']=='completed'];assert len(ats)==1
 obj=json.loads((R/'R2_05_scalability'/ats[0]['directory']/'result.json').read_text());row=obj['row'];assert row['seed']==trial['seed'] and row['case']==trial['case'];rows.append(row)
scale=pd.DataFrame(rows);scale.to_csv(O/'R2_05_raw_results_70_derived.csv',index=False)
for aa,bb,metric,exp,dec in [
('A_fleet50','A_fleet10','throughput',[.7108,.6850,.7366],4),
('A_fleet50','A_fleet10','planning_seconds',[6.66,5.24,8.09],2),
('A_rate2.0','A_rate1.0','throughput',[.0424,.0043,.0805],4),
('A_rate2.0','A_rate1.0','queue_length',[226.33,207.61,245.04],2),
('A_rate2.0','A_rate1.0','waiting_time',[85.86,77.72,94.00],2),
('A_map3_fixed','A_open_base','throughput',[.0084,.0007,.0161],4),
('A_map3_fixed','A_open_base','planning_seconds',[-.336,-.450,-.222],3),
('A_map3_density','A_open_base','throughput',[3.6228,3.4787,3.7669],4),
('A_map3_density','A_open_base','planning_seconds',[15.48,14.13,16.83],2),
('B_traffic_shared','B_traffic_dispersed','throughput',[-.3324,-.4073,-.2575],4)]:
 add('R2_05/'+aa+'_minus_'+bb+'_'+metric,pair(scale[scale.case==aa],scale[scale.case==bb],metric),exp,dec)
for case,q,w in [('A_rate0.25',[.70,.39,1.01],[.34,.26,.41]),('A_open_base',[.84,.52,1.15],[.61,.50,.71]),('A_rate1.0',[26.70,13.60,39.79],[27.38,15.11,39.65]),('A_rate2.0',[253.02,234.27,271.78],[113.24,107.06,119.42])]:
 d=scale[scale.case==case].set_index('seed');add('R2_05/Table2_'+case+'_queue',d.queue_length,q,2,False);add('R2_05/Table2_'+case+'_waiting',d.waiting_time,w,2,False)
factor=load('R2_07_factorial_ablation',['raw_results.csv']);factor.to_csv(O/'R2_07_raw_results_240_derived.csv',index=False)
assert len(factor)==240 and factor.groupby(['map','seed']).size().eq(16).all()
frows=[]
for m,g in factor.groupby('map'):
 for metric in ['throughput','queue_length','planning_seconds','instrumented_pure_seconds','rollback_count']:
  def conditional(f,on,other,state):
   gg=g[g[other]==state];p=gg.groupby(['seed',f])[metric].mean().unstack(f);return p[on]-p[1-on]
  s0=conditional('S',1,'L',0);s1=conditional('S',1,'L',1);p0=conditional('P',1,'R',0);p1=conditional('P',1,'R',1)
  for label,v in [('S|L0',s0),('S|L1',s1),('SxL',s1-s0),('P|R0',p0),('P|R1',p1)]:
   a=summarize(v);frows.append(dict(map=m,metric=metric,contrast=label,mean=a[0],ci95_low=a[1],ci95_high=a[2]))
  if metric=='throughput':
   a={'STANDARD':[-.005,.056,.061],'FRANSEN':[.040,.599,.559],'RING':[.020,.142,.122]}[m]
   for label,v,expect in zip(['S|L0','S|L1','SxL'],[s0,s1,s1-s0],a):meancheck('R2_07/Table3_'+m+'_'+label+'_throughput',v.mean(),expect,3)
   exp={'STANDARD':[.0608,.0451,.0765],'FRANSEN':[.5585,.5019,.6151],'RING':[.1220,.0815,.1625]}[m];add('R2_07/'+m+'_SxL_throughput',s1-s0,exp,4)
  if metric=='queue_length':
   a={'STANDARD':[-.7,-14.0,-13.3],'FRANSEN':[-11.3,-147.7,-136.4],'RING':[-6.9,-39.0,-32.1]}[m]
   for label,v,expect in zip(['S|L0','S|L1','SxL'],[s0,s1,s1-s0],a):meancheck('R2_07/Table3_'+m+'_'+label+'_queue',v.mean(),expect,1)
  if metric=='instrumented_pure_seconds':
   exp={'STANDARD':[-3.24,-5.43,-1.05],'FRANSEN':[-26.13,-28.28,-23.97],'RING':[-24.87,-27.80,-21.94]}[m];add('R2_07/Table4_'+m+'_P_given_R1_instrumented_pure_seconds',p1,exp)
   meancheck('R2_07/Table4_'+m+'_P_given_R0_seconds',p0.mean(),{'STANDARD':.09,'FRANSEN':-1.07,'RING':1.88}[m],2)
  if metric=='rollback_count':
   a=g[(g.P==0)&(g.R==1)][metric].mean();b=g[(g.P==1)&(g.R==1)][metric].mean()
   e={'STANDARD':[933,747,19.9],'FRANSEN':[3309,1713,48.2],'RING':[2231,1557,30.2]}[m]
   for label,value,expect,dec in zip(['P0_R1','P1_R1','reduction_percent'],[a,b,100*(a-b)/a],e,[0,0,1]):meancheck('R2_07/Table4_'+m+'_'+label,value,expect,dec)
pd.DataFrame(frows).to_csv(O/'R2_07_conditional_metric_definitions.csv',index=False)
ef=pd.DataFrame(effects);ef['p_holm_audit_family']=np.nan
for fam,idx in ef[ef.paired].groupby('holm_family').groups.items():
 idx=list(idx);order=sorted(idx,key=lambda i:ef.loc[i,'p_exact_signflip']);running=0
 for rank,i in enumerate(order):running=max(running,(len(order)-rank)*ef.loc[i,'p_exact_signflip']);ef.loc[i,'p_holm_audit_family']=min(1,running)
ef.to_csv(O/'paired_contrasts_and_mean_intervals.csv',index=False);pd.DataFrame(seed_effects).to_csv(O/'seed_effects.csv',index=False)
ch=pd.DataFrame(checks);ch.to_csv(O/'response_numeric_checks.csv',index=False)
summary={'checked_numeric_entries':len(ch),'matches':int(ch.matches.sum()),'mismatches':int((~ch.matches).sum()),'n_independent_seeds':5,'two_sided_exact_signflip_minimum_p':2/32,'source':'supplied result rows only; Response figures/tables/narrative transcription','historical_holm_families_not_assumed':True}
(O/'audit_summary.json').write_text(json.dumps(summary,indent=2))
print(summary);print(ch[~ch.matches].to_string(index=False))
