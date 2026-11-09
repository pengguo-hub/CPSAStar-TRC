"""Render audited results only. Smoke requires an explicit validation-preview flag."""
import argparse,csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.ticker import MaxNLocator
from experiments.revision.R2_05_scalability.common import read_json
from experiments.revision.R2_05_scalability.protocol import make_loader

GROUPS=[('Fleet size','16×11; initial backlog = 3000', ['A_fleet10','A_fleet30','A_fleet50'],['10','30','50'],'Number of AGVs'),
        ('Map size · fixed fleet','N = 30; λ = 0.5',['A_open_base','A_map2_fixed','A_map3_fixed'],['16×11','32×22','48×33'],'Map dimensions'),
        ('Proportional expansion','N = 30 / 120 / 270\nλ = 0.5 / 2.0 / 4.5',['A_open_base','A_map2_density','A_map3_density'],['16×11','32×22','48×33'],'Map dimensions'),
        ('Task arrival rate','16×11; N = 30',['A_rate0.25','A_open_base','A_rate1.0','A_rate2.0'],['0.25','0.5','1.0','2.0'],'Arrival intensity λ'),
        ('Traffic-demand structure','20×20; N = 8; λ = 0.5',['B_traffic_dispersed','B_traffic_intermediate','B_traffic_shared'],['Dispersed','Intermediate','Shared'],'OD pairing')]
COLOR='#DC2626'

def configure():
    plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','Liberation Serif','DejaVu Serif'],
                         'font.size':9,'axes.labelsize':10,'axes.titlesize':11,'pdf.fonttype':42,'ps.fonttype':42,
                         'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'xtick.labelsize':8.5,'ytick.labelsize':8.5})

def point_series(ax,names,lookup,metric):
    xx=[];yy=[]
    for i,name in enumerate(names):
        r=lookup.get((name,metric));value=None if r is None or not r['mean'] else float(r['mean'])
        if value is None:
            ax.text(i,.5,'Not run',transform=ax.get_xaxis_transform(),ha='center',color='#888',fontsize=8,rotation=90);continue
        xx.append(i);yy.append(value);ax.plot(i,value,'o',color=COLOR,ms=4.3,zorder=3)
        if r['ci_low'] and r['ci_high']:
            low,high=float(r['ci_low']),float(r['ci_high'])
            ax.errorbar(i,value,yerr=[[value-low],[high-value]],fmt='none',ecolor=COLOR,capsize=3,lw=1)
    if len(xx)>1:ax.plot(xx,yy,color=COLOR,lw=1.15,alpha=.85)
    ax.set_xlim(-.35,len(names)-.65);ax.grid(axis='y',ls=':',lw=.6,color='#d8d8d8');ax.set_axisbelow(True)

def save(fig,out,stem):
    fig.savefig(out/(stem+'.png'),dpi=400,bbox_inches='tight',facecolor='white')
    fig.savefig(out/(stem+'.pdf'),bbox_inches='tight',facecolor='white');plt.close(fig)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--validation-preview',action='store_true');a=p.parse_args();status=read_json(a.analysis/'analysis_status.json')
    validation=status['purpose']!='formal'
    if validation and not a.validation_preview:p.error('Smoke is not manuscript data; use --validation-preview')
    out=a.output or a.analysis.parent/'figures';out.mkdir(parents=True,exist_ok=True);configure()
    rows=list(csv.DictReader((a.analysis/'summary_long.csv').open(encoding='utf-8-sig')))
    lookup={(r['case'],r['metric']):r for r in rows};prefix='VALIDATION_' if validation else 'Figure_R2_05_'
    fig,axes=plt.subplots(3,5,figsize=(17.2,8.5));fig.subplots_adjust(left=.066,right=.99,top=.81,bottom=.12,hspace=.32,wspace=.38)
    metrics=['throughput','completion_fraction','planning_seconds'];labels=['Throughput\n(tasks / time step)','Task-completion fraction\n(completed / released)','Cumulative planning time (s)']
    for col,(title,subtitle,names,ticks,xlabel) in enumerate(GROUPS):
        for row,metric in enumerate(metrics):
            ax=axes[row,col];point_series(ax,names,lookup,metric)
            ax.set_xticks(range(len(names)));ax.set_xticklabels(ticks if row==2 else [])
            if row==0:
                ns=[lookup.get((n,metric),{}).get('n','0') for n in names]
                ax.set_title(title+'\n'+subtitle+'\n'+'n = '+' / '.join(ns),pad=12,fontsize=10)
            if col==0:ax.set_ylabel(labels[row])
            if row==1:ax.set_ylim(bottom=min(0,ax.get_ylim()[0]),top=max(1.03,ax.get_ylim()[1]))
            if row==2:
                ax.set_ylim(bottom=min(0,ax.get_ylim()[0]))
                ax.set_xlabel(xlabel,labelpad=8)
        axes[0,col].text(-.13,1.22,chr(97+col)+')',transform=axes[0,col].transAxes,fontsize=12,fontweight='bold')
    heading='SMOKE VALIDATION — NOT FOR MANUSCRIPT' if validation else 'Scalability of the original Lifelong CPS-A* implementation'
    fig.suptitle(heading,y=.985,fontsize=15,color='#9a5a00' if validation else '#222')
    sub='500 simulation steps · no warm-up · '+('One validation seed; no confidence intervals' if validation else 'Means and 95% Student t confidence intervals across independent seeds')
    fig.text(.5,.94,sub,ha='center',fontsize=10)
    fig.text(.066,.025,'Fleet panel: original backlogged supply. Other panels: controlled Poisson releases.\nTraffic labels describe OD pairings; actual congestion is measured separately. Planning time excludes measured observer callbacks.',fontsize=9,color='#444')
    save(fig,out,prefix+'scalability')
    fig,axes=plt.subplots(1,2,figsize=(9.2,3.9));fig.subplots_adjust(left=.09,right=.98,top=.78,bottom=.20,wspace=.38)
    names=GROUPS[-1][2];ticks=GROUPS[-1][3]
    from experiments.revision.R2_05_scalability.common import ROOT
    s=read_json(ROOT/'configs/traffic_couplings.json');ref=[s['levels'][k]['reference_overlap'] for k in ['dispersed','intermediate','shared']]
    axes[0].bar(range(3),ref,color=['#e6b8b8','#dd8e8e',COLOR],width=.55);axes[0].set_ylabel('Reference interior path overlap');axes[0].set_title('(a) Controlled geometric input')
    point_series(axes[1],names,lookup,'traffic_encounter_rate');axes[1].set_ylabel('Realized encounter fraction\n(short headway)');axes[1].set_title('(b) Measured trajectory response')
    for ax in axes:ax.set_xticks(range(3));ax.set_xticklabels(ticks);ax.grid(axis='y',ls=':',lw=.5);ax.set_axisbelow(True)
    ns=[lookup.get((n,'traffic_encounter_rate'),{}).get('n','0') for n in names]
    fig.suptitle(('VALIDATION ONLY · ' if validation else '')+'Traffic-demand manipulation and realized interactions',fontsize=12,y=.98)
    fig.text(.5,.86,'N = 8 · 20×20 · λ = 0.5 · n = '+' / '.join(ns),ha='center',fontsize=9)
    fig.text(.09,.025,'Service-point neighbourhoods excluded; encounter headway ±2 steps.\nAn ordered reference overlap does not imply ordered realized congestion.',fontsize=8.5)
    save(fig,out,prefix+'traffic_validation')
    fig,axes=plt.subplots(1,3,figsize=(11.5,3.8));fig.subplots_adjust(left=.04,right=.98,top=.85,bottom=.1,wspace=.15)
    for ax,k in zip(axes,[1,2,3]):
        l=make_loader('STANDARD',k);g=l.load_map();arr=g.grid.copy()
        for coords in l.outbound_map.values():
            for x,y in coords:arr[y,x]=2
        ax.imshow(arr,origin='lower',interpolation='none',cmap=ListedColormap(['white','#b3b3b3','#b681ce']),vmin=0,vmax=2,extent=[-.5,g.width-.5,-.5,g.height-.5])
        ax.set_xticks(np.arange(-.5,g.width,1),minor=True);ax.set_yticks(np.arange(-.5,g.height,1),minor=True)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=5));ax.yaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
        ax.grid(which='minor',color='#eeeeee',lw=.25);ax.tick_params(which='minor',length=0)
        ax.set_title(f'{g.width}×{g.height}\n{int((arr!=1).sum())} passable cells; {5*k*k} stations',fontsize=10)
        ax.set_xlabel('x');ax.set_ylabel('y');ax.set_aspect('equal')
    fig.suptitle('Map A tiling: original shelf and workstation coordinates',y=.98,fontsize=12)
    save(fig,out,'Figure_R2_05_map_layouts')
    caption='Figure. Scalability over 500 simulation steps without warm-up. Columns vary fleet size, map size at fixed fleet, proportional capacity and demand, arrival intensity, and matched OD coupling. Rows show completed tasks per simulation step, completed/released fraction, and cumulative batch-planning time. Error bars, when n≥2, are two-sided 95% Student t intervals across independent seeds. The original fleet panel uses a 3000-request initial queue; other panels use Poisson releases and are not the same workload baseline. Map expansion uses tile-local transport requests. The density branch scales both fleet and total demand. OD labels denote reference overlap, not assumed realized congestion. Original source task/occupancy semantics are retained.\n'
    if validation:caption='VALIDATION PREVIEW ONLY; n=1, no inferential interval.\n\n'+caption
    (out/'figure_caption.md').write_text(caption,encoding='utf-8');print(out)

if __name__=='__main__':main()
