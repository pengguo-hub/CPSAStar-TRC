"""Audited reconstruction, NOT an exact reproduction of the supplied final script.
Uses Response's mean +/- sample SD convention; does not implement missing experiments.
"""
from pathlib import Path
import pandas as pd,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[5]
def main():
 data=ROOT/'results/revision/R2_02_representation';out=ROOT/'figures/revision/R2_02_representation/reconstruction';out.mkdir(parents=True,exist_ok=True)
 raw=pd.read_csv(data/'raw_results.csv');tasks=pd.read_csv(data/'task_results.csv');rows=[]
 for (m,n),g in raw.groupby(['map','task_count']):
  for comp in ['no_field','raw','exponential','linear','uniform','historical_gaussian','learned_gaussian']:
   a=g[g.representation=='gaussian'].set_index('seed');b=g[g.representation==comp].set_index('seed')
   for seed in a.index:
    td=tasks[(tasks['map']==m)&(tasks.task_count==n)&(tasks.seed==seed)]
    aa=td[(td.representation=='gaussian')&td.success].set_index('agv_id');bb=td[(td.representation==comp)&td.success].set_index('agv_id');ids=aa.index.intersection(bb.index)
    av=aa.loc[ids,'neutral_congestion_exposure'].mean();bv=bb.loc[ids,'neutral_congestion_exposure'].mean()
    rows.append(dict(map=m,task_count=n,seed=seed,comparator=comp,success_pp=100*(a.loc[seed,'success_rate']-b.loc[seed,'success_rate']),exposure_reduction_percent=100*(bv-av)/bv,common_successful_tasks=len(ids)))
 d=pd.DataFrame(rows);d.to_csv(out/'paired_seed_values.csv',index=False)
 labels=[(m,n) for m,n in d[['map','task_count']].drop_duplicates().itertuples(index=False,name=None)]
 for family,comps in [('information_source',['historical_gaussian','learned_gaussian']),('kernel',['no_field','raw','exponential','linear','uniform'])]:
  fig,axes=plt.subplots(1,2,figsize=(12,4.5))
  for ax,metric,title in zip(axes,['success_pp','exposure_reduction_percent'],['Success difference (percentage points)','Common-task exposure reduction (%)']):
   for j,c in enumerate(comps):
    sub=d[d.comparator==c];stats=sub.groupby(['map','task_count'])[metric].agg(['mean','std']).reindex(labels)
    ax.errorbar(np.arange(len(labels))+(j-(len(comps)-1)/2)*.035,stats['mean'],yerr=stats['std'],marker='o',capsize=3,label=c.replace('_',' '))
   ax.set_xticks(range(len(labels)),[f'{m}{n}' for m,n in labels]);ax.axhline(0,color='#777',lw=.8);ax.set_title(title);ax.grid(axis='y',alpha=.2)
  axes[0].legend(fontsize=8);fig.suptitle('Audited reconstruction: Gaussian vs comparator; mean ± sample SD (5 paired seeds)',fontsize=11)
  fig.tight_layout();fig.savefig(out/(family+'_mean_sd.png'),dpi=180);fig.savefig(out/(family+'_mean_sd.pdf'));plt.close(fig)
if __name__=='__main__':main()
