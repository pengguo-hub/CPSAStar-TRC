"""Four performance rows, three maps, two fleet groups; audited results only."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from experiments.revision.R2_04_operational_metrics.workload import FLEETS, LEVELS, specs
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',type=Path);a=ap.parse_args();out=a.results
    d=pd.read_csv(out/'summary_results.csv');raw=pd.read_csv(out/'audited_metrics.csv');smoke=raw.purpose.eq('smoke').any()
    plt.rcParams.update({'font.family':'DejaVu Serif','font.size':8.5,'pdf.fonttype':42,'axes.spines.right':False,'axes.spines.top':False})
    metrics=['throughput','waiting_time','flow_time','queue_length'];labels=['Throughput\n(tasks / step)','Restricted total waiting\n(steps / request)','Restricted flow time\n(steps / request)','Unassigned queue\n(tasks)'];colors={'full':'#267BA5','control':'#CD713E'}
    fig,axs=plt.subplots(4,3,figsize=(10.5,7.7),sharey='row',sharex=True);fig.subplots_adjust(left=.12,right=.985,top=.85,bottom=.1,hspace=.18,wspace=.10)
    fig.legend(handles=[Line2D([],[],color=colors[v],marker='o' if v=='full' else 's',mfc=colors[v] if v=='full' else 'white',ls='-' if v=='full' else '--',label=v.title()) for v in ['full','control']],loc='upper center',ncol=2,frameon=False)
    fig.text(.56,.94,'SMOKE / VALIDATION ONLY' if smoke else 'Paired lifelong experiment: 3000 requests at t = 0; 500 steps',ha='center',color='#9D2933' if smoke else 'black',fontsize=10)
    for col,mp in enumerate(FLEETS):
        spec=specs()[mp];scores=[spec['levels'][k]['reference_overlap'] for k in LEVELS]
        axs[0,col].set_title(mp,fontsize=10,pad=23)
        for block,n in enumerate(FLEETS[mp]):axs[0,col].text(1+3.5*block,1.065,f'{n} AGVs',transform=axs[0,col].get_xaxis_transform(),ha='center',fontsize=9)
        for row,m in enumerate(metrics):
            ax=axs[row,col];ax.axvspan(3,6,color='#F1F3F5');ax.axvline(3,color='#CED3D7',lw=.6);ax.grid(axis='y',color='#DDE2E6',lw=.5);ax.set_axisbelow(True)
            for block,n in enumerate(FLEETS[mp]):
                for v,dx in [('full',-.06),('control',.06)]:
                    g=d[(d['map']==mp)&(d.fleet==n)&(d.variant==v)&(d.metric==m)].set_index('mode');xx=[];yy=[];ee=[]
                    for k,mode in enumerate(LEVELS):
                        if mode not in g.index:continue
                        z=g.loc[mode];xx.append(k+block*3.5+dx);yy.append(z['mean']);ee.append((z.ci95_high-z.ci95_low)/2 if z['n']>1 else 0.)
                    ax.errorbar(xx,yy,yerr=ee,color=colors[v],fmt='o-' if v=='full' else 's--',mfc=colors[v] if v=='full' else 'white',ms=3.5,lw=1.1,capsize=2)
            ax.set_xlim(-.4,5.9);ax.set_xticks([0,1,2,3.5,4.5,5.5],['L','M','H','L','M','H']);ax.yaxis.set_major_locator(MaxNLocator(4));ax.tick_params(length=2.5)
            if col==0:ax.set_ylabel(labels[row],labelpad=10)
            if row==3:ax.set_xlabel('Static OD overlap: L / M / H\n'+', '.join(f'{x:.3f}' for x in scores),fontsize=8)
    # Consistent full scales; show paired changes numerically in CSV rather than truncating axes.
    for row in range(4):
        upper=max(ax.get_ylim()[1] for ax in axs[row]);[ax.set_ylim(0,upper*1.04) for ax in axs[row]]
    ns=sorted(d[d.metric=='throughput']['n'].unique());fig.text(.56,.025,'Valid paired seeds per condition: '+', '.join(str(int(n)) for n in ns)+'. Error bars: 95% t intervals when n >= 2; n = 1 shows points only.',ha='center',fontsize=8)
    (out/'figures').mkdir(exist_ok=True)
    for ext in ['pdf','png']:fig.savefig(out/'figures'/f'R2_04_OD_results.{ext}',dpi=450)
    plt.close(fig)
    # Paired changes complement the full-scale means without truncating their axes.
    stats=pd.read_csv(out/'paired_statistics.csv');stats=stats[stats.comparison=='Full-Control']
    fig,axs=plt.subplots(4,3,figsize=(10.5,7.4),sharey='row',sharex=True);fig.subplots_adjust(left=.13,right=.98,top=.88,bottom=.12,hspace=.21,wspace=.12)
    fig.suptitle(('SMOKE / VALIDATION ONLY: ' if smoke else '')+'paired Full - Control',fontsize=11,color='#9D2933' if smoke else 'black',y=.97)
    delta_labels=['Throughput difference\n(tasks / step)','Waiting difference\n(steps / request)','Flow difference\n(steps / request)','Queue difference\n(tasks)']
    for col,mp in enumerate(FLEETS):
        axs[0,col].set_title(mp,fontsize=10)
        for row,m in enumerate(metrics):
            ax=axs[row,col];ax.axhline(0,color='#77838B',lw=.8);ax.axvspan(3,6,color='#F1F3F5');ax.grid(axis='y',color='#E2E6E9',lw=.5);ax.set_axisbelow(True)
            for block,n in enumerate(FLEETS[mp]):
                for k,mode in enumerate(LEVELS):
                    z=stats[(stats.group==f'{mp}_N{n}_{mode}')&(stats.metric==m)]
                    if z.empty:continue
                    z=z.iloc[0];err=(z.ci95_high-z.ci95_low)/2 if z['n']>1 else 0
                    ax.errorbar(k+3.5*block,z.mean_difference,yerr=err,color='#267BA5',fmt='o',ms=4,capsize=3,lw=1)
            ax.set_xlim(-.4,5.9);ax.set_xticks([0,1,2,3.5,4.5,5.5],['L','M','H','L','M','H']);ax.yaxis.set_major_locator(MaxNLocator(4))
            if col==0:ax.set_ylabel(delta_labels[row],fontsize=8)
            if row==3:ax.set_xlabel(f'{FLEETS[mp][0]} AGVs                 {FLEETS[mp][1]} AGVs',fontsize=8)
    fig.text(.56,.04,'Points: mean within-seed difference; bars: 95% paired t intervals.\nThroughput: positive favors Full. Waiting, flow and queue: negative favors Full.',ha='center',fontsize=8)
    for ext in ['pdf','png']:fig.savefig(out/'figures'/f'R2_04_OD_paired_effects.{ext}',dpi=450)
    plt.close(fig);print('Figures:',out/'figures')
if __name__=='__main__':main()
