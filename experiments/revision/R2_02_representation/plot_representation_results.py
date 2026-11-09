#!/usr/bin/env python3
"""All figures are computed from CSV; no manually entered performance values."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from statistics_analysis import analyze

STYLES={
 "no_field":("Collision only","#666666","o"),
 "raw":("Raw-ST","#0072B2","s"),
 "gaussian":("Gaussian-ST","#D55E00","D"),
 "exponential":("Exponential-ST","#009E73","^"),
 "linear":("Linear-ST","#E69F00","X"),
 "uniform":("Uniform-ST","#56B4E9","*"),
 "historical_gaussian":("Historical + same Gaussian","#7B68EE","v"),
 "learned_gaussian":("Learned prediction + same Gaussian","#8B4513","P"),
 "time_aggregated":("Time-aggregated","#CC79A7","v"),
 "time_shifted":("Time-shifted Gaussian","#8C6D31","P"),
}
METRICS={"success_rate":"Planning success rate (%)","planning_time":"Planning time (s)",
 "gaussian_AC":"Fixed-Gaussian congestion (AC)",
 "neutral_congestion_exposure":"Raw occupancy exposure to other planned AGVs",
 "avg_path_duration":"Path duration (steps)",
 "avg_path_length":"Travel distance (cells)","avg_wait_steps":"Waiting steps"}

def plot(input_path,reps=10000,seed=20261017):
    input_path=Path(input_path)
    summary,pairs=analyze(input_path,reps,seed)
    out=input_path.parent/"figures";out.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Serif","font.size":10,"axes.spines.top":False,
                         "axes.spines.right":False,"pdf.fonttype":42,"ps.fonttype":42})
    for (protocol,mode),group in summary.groupby(["protocol","rollback_mode"]):
        maps=sorted(group["map"].unique())
        for metric,label in METRICS.items():
            fig,axes=plt.subplots(1,len(maps),figsize=(4.3*len(maps),3.7),squeeze=False)
            for ax,m in zip(axes.flat,maps):
                for rep,(name,color,marker) in STYLES.items():
                    s=group[(group["map"]==m)&(group.metric==metric)&(group.representation==rep)].sort_values("task_count")
                    if s.empty:continue
                    scale=100 if metric=="success_rate" else 1
                    x=s.task_count.to_numpy(float);y=s["mean"].to_numpy(float)*scale
                    ax.plot(x,y,color=color,marker=marker,markersize=4,linewidth=1.4,label=name)
                    lo=s.ci95_low.to_numpy(float)*scale;hi=s.ci95_high.to_numpy(float)*scale
                    valid=np.isfinite(lo)&np.isfinite(hi)
                    if valid.any():
                        if len(x)==1:
                            ax.vlines(x[valid],lo[valid],hi[valid],color=color,linewidth=1.2)
                            ax.plot(x[valid],lo[valid],"_",color=color,markersize=6)
                            ax.plot(x[valid],hi[valid],"_",color=color,markersize=6)
                        else:
                            ax.fill_between(x,lo,hi,where=valid,color=color,alpha=.10,linewidth=0)
                ax.set_title(f"Map {m} | rollback {mode}")
                ax.set_xlabel("Number of tasks" if protocol=="direct" else "Independent probes")
                ax.grid(axis="y",alpha=.22)
                if metric=="success_rate":ax.set_ylim(-2,102)
                else:ax.set_ylim(bottom=0)
                if len(group.task_count.unique())<=10:ax.set_xticks(sorted(group[group["map"]==m].task_count.unique()))
            ylabel=label if protocol=="direct" else label
            axes[0,0].set_ylabel(ylabel)
            handles,labels=axes[0,0].get_legend_handles_labels()
            fig.legend(handles,labels,loc="lower center",bbox_to_anchor=(.5,-.005),ncol=3,frameon=False,fontsize=8)
            note=f"n={int(group.n.min())}–{int(group.n.max())} independent seeds"+": pointwise 95% seed-bootstrap CI" if group.n.max()>1 else "SMOKE TEST: one seed; no inferential confidence interval"
            fig.text(.5,.99,note,ha="center",va="top",fontsize=8)
            fig.tight_layout(rect=(0,.14,1,.94))
            for ext in ["pdf","png"]:
                fig.savefig(out/f"{protocol}_{mode}_{metric}.{ext}",dpi=300,bbox_inches="tight")
            plt.close(fig)
    if not pairs.empty:
        for (protocol,mode),group in pairs.groupby(["protocol","rollback_mode"]):
            for metric in ["success_rate","planning_time","neutral_congestion_exposure","path_length","path_duration","wait_steps"]:
                subset=group[(group.metric==metric)&group.scope.isin(["per_load","common_success_per_load"])]
                if subset.empty:continue
                maps=sorted(subset["map"].unique())
                fig,axes=plt.subplots(1,len(maps),figsize=(4.3*len(maps),3.8),squeeze=False)
                for ax,m in zip(axes.flat,maps):
                    for rep,(name,color,marker) in STYLES.items():
                        data=subset[(subset["map"]==m)&(subset.comparator==rep)].copy()
                        if data.empty:continue
                        data["task_count"]=pd.to_numeric(data.task_count);data=data.sort_values("task_count")
                        scale=100 if metric=="success_rate" else 1
                        x=data.task_count.to_numpy(float);y=data.mean_difference.to_numpy(float)*scale
                        ax.plot(x,y,color=color,marker=marker,linewidth=1.2,label=name)
                        lo=data.ci95_low.to_numpy(float)*scale;hi=data.ci95_high.to_numpy(float)*scale
                        valid=np.isfinite(lo)&np.isfinite(hi)
                        ax.vlines(x[valid],lo[valid],hi[valid],color=color,alpha=.7)
                    ax.axhline(0,color="black",linewidth=.7,linestyle="--")
                    ax.set_title(f"Map {m} | rollback {mode}");ax.set_xlabel("Number of tasks" if protocol=="direct" else "Independent probes")
                    ax.grid(axis="y",alpha=.2)
                axes[0,0].set_ylabel("Gaussian minus comparator\n"+metric+(" (percentage points)" if metric=="success_rate" else ""))
                h,l=axes[0,0].get_legend_handles_labels();fig.legend(h,l,loc="lower center",ncol=3,frameon=False,fontsize=8)
                note="SMOKE: one seed; no inferential CI" if subset.n_pairs.max()<=1 else "Paired seed-bootstrap pointwise CI; conditional on common successes for path metrics"
                fig.text(.5,.99,note,ha="center",va="top",fontsize=7)
                fig.tight_layout(rect=(0,.15,1,.93))
                for ext in ["pdf","png"]:fig.savefig(out/f"{protocol}_{mode}_paired_{metric}.{ext}",dpi=300,bbox_inches="tight")
                plt.close(fig)
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",default="results/raw_results.csv")
    p.add_argument("--bootstrap",type=int,default=10000);p.add_argument("--seed",type=int,default=20261017)
    a=p.parse_args();plot(a.input,a.bootstrap,a.seed)
