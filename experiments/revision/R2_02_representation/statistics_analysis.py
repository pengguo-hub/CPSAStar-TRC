"""Seed is the replication unit. Mean-difference bootstrap; Wilcoxon + Holm.

Map averages first average load conditions within each seed. Secondary path-level tests use
only request IDs that succeed under both Gaussian and comparator representations.
"""
import argparse
import hashlib
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from evaluation import RUN_METRICS

GROUP=["protocol","map","task_count","representation","rollback_mode"]
CASE=["protocol","map","task_count","rollback_mode"]



def comparison_question(rep):
    if rep in {"historical_gaussian","learned_gaussian"}:
        return "information_source_with_gaussian_fixed"
    if rep in {"raw","exponential","linear","uniform"}:
        return "kernel_representation_with_exact_source_fixed"
    if rep == "no_field":
        return "value_of_soft_congestion_guidance"
    return "secondary_ablation"

def rng_for(seed,label):
    number=int.from_bytes(hashlib.sha256(str(label).encode()).digest()[:8],"little")
    return np.random.default_rng(np.random.SeedSequence([seed,number]))


def ci_mean(values,rng,reps):
    a=np.asarray(values,float);a=a[np.isfinite(a)];n=len(a)
    if not n:return dict(n=0,mean=np.nan,std=np.nan,ci95_low=np.nan,ci95_high=np.nan)
    mean=float(a.mean())
    if n<2:return dict(n=n,mean=mean,std=np.nan,ci95_low=np.nan,ci95_high=np.nan)
    boots=a[rng.integers(0,n,size=(reps,n))].mean(axis=1)
    lo,hi=np.quantile(boots,[.025,.975])
    return dict(n=n,mean=mean,std=float(a.std(ddof=1)),ci95_low=float(lo),ci95_high=float(hi))


def effect_intervals(d,rng,reps):
    names=["cohen_dz_ci95_low","cohen_dz_ci95_high","rank_biserial_ci95_low","rank_biserial_ci95_high"]
    if len(d)<2:return dict.fromkeys(names,np.nan)
    b=d[rng.integers(0,len(d),size=(reps,len(d)))];sd=b.std(axis=1,ddof=1)
    dz=np.divide(b.mean(axis=1),sd,out=np.full(reps,np.nan),where=sd>1e-12)
    dz[np.all(np.abs(b)<1e-12,axis=1)]=0
    nz=np.abs(b)>1e-12
    ranks=stats.rankdata(np.abs(b),axis=1)-np.sum(~nz,axis=1)[:,None]
    ranks=np.where(nz,ranks,0)
    den=ranks.sum(axis=1)
    rb=np.divide((ranks*np.sign(b)).sum(axis=1),den,out=np.zeros(reps),where=den>0)
    def quant(a):
        finite=a[np.isfinite(a)]
        return np.quantile(finite,[.025,.975]).tolist() if len(finite) else [np.nan,np.nan]
    return dict(zip(names,quant(dz)+quant(rb)))


def paired_result(diffs,rng,reps):
    d=np.asarray(diffs,float);d=d[np.isfinite(d)]
    result=ci_mean(d,rng,reps)
    result={"n_pairs":result.pop("n"),"mean_difference":result.pop("mean"),
            "sd_difference":result.pop("std"),**result}
    result.update(effect_intervals(d,rng,reps))
    if len(d)<2:
        result.update(p_value=np.nan,cohen_dz=np.nan,rank_biserial=np.nan)
        return result
    nonzero=d[np.abs(d)>1e-12]
    if not len(nonzero):
        p,rb=1.0,0.0
    else:
        rounded=np.round(d,12)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore",UserWarning)
            p=float(stats.wilcoxon(rounded,zero_method="wilcox",alternative="two-sided",method="auto").pvalue)
        ranks=stats.rankdata(np.abs(nonzero))
        rb=float(np.sum(ranks*np.sign(nonzero))/ranks.sum())
    sd=float(d.std(ddof=1))
    dz=float(d.mean()/sd) if sd>1e-12 else (0.0 if np.all(np.abs(d)<1e-12) else np.nan)
    result.update(p_value=p,cohen_dz=dz,rank_biserial=rb)
    return result


def holm(p, family_size=None):
    a=np.asarray(p,float);answer=np.full(len(a),np.nan)
    idx=np.flatnonzero(np.isfinite(a));order=idx[np.argsort(a[idx])]
    total=max(len(a),family_size or 0)
    running=0.0
    for rank,i in enumerate(order):
        running=max(running,(total-rank)*a[i]);answer[i]=min(1.0,running)
    return answer


def analyze(input_path,reps=10000,seed=20261017):
    input_path=Path(input_path);df=pd.read_csv(input_path)
    if df.empty:raise ValueError("No raw rows")
    manifest=input_path.parent/"run_manifest.json"
    plan=json.loads(manifest.read_text()) ["plan"] if manifest.exists() else {}
    n_expected=len(plan.get("seeds",df.seed.unique()))
    expected_reps=plan.get("representations",sorted(df.representation.unique()))
    n_comparators=len(set(expected_reps)-{"gaussian"})
    expected_by_question={
        "information_source_with_gaussian_fixed": len(set(expected_reps)&{"historical_gaussian","learned_gaussian"}),
        "kernel_representation_with_exact_source_fixed": len(set(expected_reps)&{"raw","exponential","linear","uniform"}),
        "value_of_soft_congestion_guidance": int("no_field" in expected_reps),
        "secondary_ablation": len(set(expected_reps)-{"gaussian","historical_gaussian","learned_gaussian","raw","exponential","linear","uniform","no_field"}),
    }
    def expected_family(mode,scope,question):
        maps=plan.get("maps",sorted(df["map"].unique()))
        nrep=expected_by_question.get(question,0)
        if scope=="map_average":return len(maps)*nrep
        loads=plan.get("loads",{m:sorted(df[df["map"]==m].task_count.unique()) for m in maps})
        return sum(len(loads[m]) for m in maps)*nrep
    if df.duplicated(GROUP+["seed"]).any():raise ValueError("Duplicate map/load/seed/representation rows")

    summary=[]
    for key,g in df.groupby(GROUP,dropna=False,sort=True):
        for metric in RUN_METRICS:
            if metric not in g:continue
            row=dict(zip(GROUP,key));row["metric"]=metric
            row.update(ci_mean(g[metric],rng_for(seed,(key,metric)),reps))
            row["n_expected"]=n_expected
            row["complete_seeds"]=len(g)==n_expected
            row["timeout_count"]=int(g["timed_out"].sum())
            summary.append(row)
    summary_df=pd.DataFrame(summary)
    summary_df.to_csv(input_path.parent/"summary_results.csv",index=False)

    pairs=[]
    for key,g in df.groupby(CASE,sort=True):
        ga=g[g.representation=="gaussian"].set_index("seed")
        for rep in sorted(set(g.representation)-{"gaussian"}):
            other=g[g.representation==rep].set_index("seed")
            common=ga.index.intersection(other.index)
            for metric in ["success_rate","planning_time"]:
                delta=ga.loc[common,metric]-other.loc[common,metric]
                row=dict(zip(CASE,key));row.update(comparator=rep,comparison_question=comparison_question(rep),metric=metric,scope="per_load",
                    estimand="Gaussian minus comparator",n_gaussian=len(ga),n_comparator=len(other),
                    incomplete_pairs=int(len(common)!=n_expected),n_expected=n_expected)
                row.update(paired_result(delta,rng_for(seed,(key,rep,metric)),reps));pairs.append(row)

    keys=["protocol","map","rollback_mode"]
    for key,g in df.groupby(keys,sort=True):
        loads=plan.get("loads",{}).get(key[1],sorted(g.task_count.unique()))
        for rep in sorted(set(g.representation)-{"gaussian"}):
            sub=g[g.representation.isin(["gaussian",rep])]
            pivot=sub.pivot(index=["seed","task_count"],columns="representation",values="success_rate")
            if "gaussian" not in pivot or rep not in pivot:continue
            diff=(pivot["gaussian"]-pivot[rep]).dropna()
            counts=diff.groupby(level="seed").count()
            valid=counts[counts==len(loads)].index
            per_seed=diff.groupby(level="seed").mean().loc[valid]
            row=dict(zip(keys,key));row.update(task_count="all",comparator=rep,comparison_question=comparison_question(rep),metric="success_rate",
                scope="map_average",estimand="Gaussian minus comparator, equal load weighting within seed",
                n_loads=len(loads),n_excluded_incomplete_seeds=int(len(counts)-len(valid)))
            row.update(paired_result(per_seed,rng_for(seed,(key,rep,"map_average")),reps));pairs.append(row)

    task_file=input_path.parent/"task_results.csv"
    if task_file.exists():
        td=pd.read_csv(task_file)
        metrics=["path_length","path_duration","wait_steps","neutral_congestion_exposure","turns"]
        for key,g in td.groupby(CASE,sort=True):
            ga=g[(g.representation=="gaussian") & (g.success==1)]
            for rep in sorted(set(g.representation)-{"gaussian"}):
                other=g[(g.representation==rep) & (g.success==1)]
                common=ga.merge(other,on=["seed","agv_id"],suffixes=("_g","_c"),validate="one_to_one")
                for metric in metrics:
                    differences=common.assign(diff=common[metric+"_g"]-common[metric+"_c"]).groupby("seed")["diff"].mean()
                    row=dict(zip(CASE,key));row.update(comparator=rep,comparison_question=comparison_question(rep),metric=metric,scope="common_success_per_load",
                        estimand="paired common-success task mean per seed; conditional, not fleet-wide",
                        n_common_tasks=len(common))
                    row.update(paired_result(differences,rng_for(seed,(key,rep,metric,"common")),reps));pairs.append(row)

    out=pd.DataFrame(pairs)
    if not out.empty:
        out["family"]=out.apply(lambda r:f'{r.protocol}/{r.rollback_mode}/{r.scope}/{r.metric}/{r.comparison_question}',axis=1)
        out["p_holm"]=np.nan
        for _,indices in out.groupby("family").groups.items():
            first=out.loc[list(indices)[0]]
            size=expected_family(first.rollback_mode,first.scope,first.comparison_question)
            out.loc[indices,"p_holm"]=holm(out.loc[indices,"p_value"],size)
            out.loc[indices,"predeclared_family_size"]=size
        out["n_expected"]=n_expected
        out["complete_seed_pairs"]=out.n_pairs==n_expected
        out["success_difference_percentage_points"]=np.where(out.metric=="success_rate",100*out.mean_difference,np.nan)
        out["ci_type"]="pointwise percentile paired-seed bootstrap; CI not multiplicity-adjusted"
    out.to_csv(input_path.parent/"pairwise_statistics.csv",index=False)

    interactions=[]
    if {"off","on"}.issubset(set(df.rollback_mode)):
        for (protocol,map_name),g in df.groupby(["protocol","map"]):
            for rep in sorted(set(g.representation)-{"gaussian"}):
                sub=g[g.representation.isin(["gaussian",rep])]
                pivot=sub.pivot(index=["seed","task_count"],columns=["representation","rollback_mode"],values="success_rate")
                needed=[("gaussian","off"),("gaussian","on"),(rep,"off"),(rep,"on")]
                if not all(k in pivot for k in needed):continue
                usable=pivot[needed].dropna()
                expected=len(set(g.task_count))
                counts=usable.groupby(level="seed").size()
                valid=counts[counts==expected].index
                did=((usable[("gaussian","on")]-usable[(rep,"on")])
                     -(usable[("gaussian","off")]-usable[(rep,"off")])).groupby(level="seed").mean().loc[valid]
                row=dict(protocol=protocol,map=map_name,comparator=rep,comparison_question=comparison_question(rep),n_loads=expected,
                         estimand="(Gaussian-comparator)_on minus (Gaussian-comparator)_off; load mean within seed")
                row.update(paired_result(did,rng_for(seed,(protocol,map_name,rep,"rollback_interaction")),reps))
                interactions.append(row)
    interaction_df=pd.DataFrame(interactions)
    if not interaction_df.empty:
        interaction_df["p_holm"]=holm(interaction_df.p_value,len(plan.get("maps",df["map"].unique()))*n_comparators)
    interaction_df.to_csv(input_path.parent/"rollback_interactions.csv",index=False)
    return summary_df,out


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",default="results/raw_results.csv")
    p.add_argument("--bootstrap",type=int,default=10000);p.add_argument("--seed",type=int,default=20261017)
    a=p.parse_args();analyze(a.input,a.bootstrap,a.seed)
