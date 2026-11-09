#!/usr/bin/env python3
"""Joint spatiotemporal sensitivity: sigma_l x sigma_t and L x T."""
import argparse, hashlib, json
from dataclasses import replace
from pathlib import Path
import pandas as pd
from config import Config, MAPS, TASK_COUNTS, R1_GAUSSIAN_SWEEPS
from instances import get_task_instance, write_json, canonical_hash
from experiment_core import run_trial
from evaluation import RUN_METRICS
from statistics_analysis import ci_mean, rng_for

ROOT = Path(__file__).resolve().parent

def cfg_key(c):
    return canonical_hash(c.to_dict())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('results_joint_spatiotemporal_sensitivity'))
    p.add_argument('--seeds',type=int,default=5)
    p.add_argument('--seed-start',type=int,default=10000)
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    base=Config(seed_start=a.seed_start).validate()
    seeds=[a.seed_start] if a.smoke else list(range(a.seed_start,a.seed_start+a.seeds))
    maps=list(MAPS)
    widths=(1.0,2.0) if a.smoke else R1_GAUSSIAN_SWEEPS['sigma_l']
    supports=(0,1) if a.smoke else R1_GAUSSIAN_SWEEPS['L']
    studies={"sigma_l_sigma_t":{},"L_T":{}}
    for sl in widths:
        for st in widths:
            c=replace(base,sigma_l=float(sl),sigma_t=float(st))
            studies['sigma_l_sigma_t'][f"sigma_l={sl:g}__sigma_t={st:g}"]=c
    for L in supports:
        for T in supports:
            c=replace(base,L=int(L),T=int(T))
            studies['L_T'][f"L={L}__T={T}"]=c
    unique={cfg_key(c):c for cells in studies.values() for c in cells.values()}
    load_pairs=len(maps) if a.smoke else sum(len(v) for v in TASK_COUNTS.values())
    actual=len(unique)*load_pairs*len(seeds)
    logical=sum(len(v) for v in studies.values())*load_pairs*len(seeds)
    plan={"stage":"joint_spatiotemporal_sensitivity","maps":maps,"task_counts":TASK_COUNTS,"seeds":seeds,
          "baseline":base.to_dict(),"studies":{s:{n:c.to_dict() for n,c in cells.items()} for s,cells in studies.items()},
          "unique_configs_per_map_load_seed":len(unique),"actual_executions":actual,"logical_study_rows":logical,
          "pairing":"same map/task_count/seed task list reused for every cell; CPS-A replans full batch from empty reservations"}
    print(json.dumps(plan,indent=2),flush=True)
    if a.dry_run:return
    out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True); write_json(out/'joint_manifest.json',plan)
    cache={}; logical_rows=[]; actual_done=0
    for m in maps:
        loads=(5,) if a.smoke else TASK_COUNTS[m]
        for n in loads:
            for seed in seeds:
                inst=get_task_instance(out/'shared_tasks',m,n,seed)
                local={}
                for key,c in unique.items():
                    runfile=out/'runs'/f"{m}_N{n}_seed{seed}_{key[:12]}.json"
                    if runfile.exists(): row=json.loads(runfile.read_text(encoding='utf-8'))
                    else:
                        row=run_trial(inst,c); write_json(runfile,row)
                    if row['task_hash']!=inst['task_hash']: raise AssertionError('Task pairing failed')
                    local[key]=row; actual_done+=1
                    print(f"JOINT {m} N={n} seed={seed} cfg={key[:8]} success={row['success_count']}/{n}",flush=True)
                for study,cells in studies.items():
                    for cell,c in cells.items():
                        row=dict(local[cfg_key(c)]); row.update(study=study,cell=cell)
                        logical_rows.append(row)
                pd.DataFrame(logical_rows).to_csv(out/'joint_raw_results.csv',index=False)
    df=pd.DataFrame(logical_rows); summary=[]
    for (study,m,n,cell),g in df.groupby(['study','map','task_count','cell'],sort=True):
        for metric in RUN_METRICS:
            d=dict(study=study,map=m,task_count=n,cell=cell,metric=metric)
            d.update(ci_mean(g[metric],rng_for(base.statistics_seed,(study,m,n,cell,metric)),2000 if a.smoke else base.bootstrap_replicates)); summary.append(d)
    pd.DataFrame(summary).to_csv(out/'joint_summary.csv',index=False)
    write_json(out/'joint_completion_status.json',{"actual_executions":actual_done,"expected_actual_executions":actual,"logical_rows":len(df),"expected_logical_rows":logical,"smoke":a.smoke})
if __name__=='__main__': main()
