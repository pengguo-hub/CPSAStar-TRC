#!/usr/bin/env python3
"""Direct one-shot congestion-representation comparison for Reviewer 2 Comment 2."""
import argparse
import importlib.metadata
import json
import platform
import random
import sys
import time
from dataclasses import replace
from pathlib import Path
import pandas as pd
from config import Config, MAPS, REPRESENTATIONS, PRIMARY_REPRESENTATIONS, KERNEL_FAMILY, SOURCE_FAMILY
from instances import (get_instance,build_grid,parsed_tasks,agv_info,initial_order,
                       canonical_hash,write_json,seed_all)
from controlled_search import Budget
from controlled_planner import ControlledPlanner
from field_strategies import kernel_diagnostics
from evaluation import evaluate
from statistics_analysis import analyze

ROOT=Path(__file__).resolve().parent


def source_digest():
    files={str(p.relative_to(ROOT)):__import__("hashlib").sha256(p.read_bytes()).hexdigest()
           for p in [*ROOT.glob("*.py"),*(ROOT/"vendor").rglob("*.py"),*(ROOT/"tests").rglob("*.py")] if "__pycache__" not in p.parts}
    return canonical_hash(files)


def trial(instance,n,representation,mode,config,reference_dir=None):
    seed_all(instance["seed"])
    tasks=instance["tasks"][:n]
    grid=build_grid(instance["map"])
    budget=Budget(config.timeout)
    field_context=dict(reference_dir=str(reference_dir) if reference_dir is not None else None,
                       map=instance["map"],task_count=n,tasks=tasks,seed=instance["seed"])
    planner=ControlledPlanner(grid,agv_info(tasks,config),representation,config,budget,map_name=instance["map"],field_context=field_context)
    field_time=budget.elapsed
    planner.batch_plan(parsed_tasks(tasks),rollback=mode=="on")
    elapsed=budget.elapsed
    records={aid:dict(path=info["path"],times=info["times"])
             for aid,info in planner.agv_tasks.items() if info.get("path")}
    metrics,task_rows,validation=evaluate(grid,tasks,records,config)
    row=dict(protocol="direct",map=instance["map"],task_count=n,seed=instance["seed"],task_seed=instance["task_seed"],
             representation=representation,rollback_mode=mode,planning_time=elapsed,
             field_initialization_time=field_time,search_and_update_time=elapsed-field_time,
             task_hash=canonical_hash(tasks),initial_order_hash=canonical_hash(initial_order(tasks)),
             timed_out=int(planner.timeout),run_status="timeout_partial" if planner.timeout else "completed",
             rollback_count=planner.rollback_count,blocker_guard_count=planner.blocker_guard_count,
             failed_search_count=planner.failed_search_count,expanded_states=planner.segment_planner.expansions,
             parameters=json.dumps(config.to_dict(),sort_keys=True),
             common_planner_signature=canonical_hash(dict(alpha=config.alpha,gamma=config.gamma,omega=config.omega,
                 fixed_turn_penalty=0.5,max_wait=config.max_wait,update_interval=config.update_interval,
                 retry_limit=config.retry_limit,map_lookahead=(instance["map"]=="A"),rollback_mode=mode,
                 hard_reservation_constraints="shared TicketManager node+reverse-edge",search="ControlledSegmentPlanner")),
             representation_family=("source" if representation in SOURCE_FAMILY else ("kernel" if representation in KERNEL_FAMILY else "control")),
             soft_information_source=("exact_committed_reservations" if representation in set(KERNEL_FAMILY) else
                 ("independent_historical_occupancy" if representation=="historical_gaussian" else
                  ("learned_prediction_from_current_tasks" if representation=="learned_gaussian" else "none"))),
             soft_kernel=("none" if representation in ("no_field","raw") else
                          ("gaussian" if representation in ("gaussian","historical_gaussian","learned_gaussian") else representation)),
             **metrics)
    metadata={k:row[k] for k in ["protocol","map","task_count","seed","representation","rollback_mode"]}
    task_rows=[dict(metadata,**r) for r in task_rows]
    row["timeout_scope"]="batch_including_field_init"
    return dict(row=row,task_rows=task_rows,paths=records,attempt_order=planner.attempt_trace,
                field_updates=planner.field_trace,validation=validation,field_source_metadata=getattr(planner.conflict_updater,"source_metadata",None))


def export_results(output):
    files=sorted((output/"runs").glob("*.json"))
    runs=[json.loads(p.read_text(encoding="utf-8")) for p in files]
    rows=[r["row"] for r in runs]
    if not rows:return
    raw=pd.DataFrame(rows)
    keys=["protocol","map","task_count","seed"]
    for _,g in raw.groupby(keys):
        for col in ["task_hash","initial_order_hash","common_planner_signature"]:
            if g[col].nunique()!=1:raise AssertionError(f"Paired control mismatch: {col}")
    raw.to_csv(output/"raw_results.csv",index=False)
    pd.DataFrame([t for r in runs for t in r["task_rows"]]).to_csv(output/"task_results.csv",index=False)


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke",action="store_true",help="Map A, 1 seed, 20 direct tasks; all representations")
    p.add_argument("--seeds",type=int,default=None,help="Number of independent matched test seeds (default 5 for formal runs)")
    p.add_argument("--seed-start",type=int,default=None)
    p.add_argument("--seed-list",type=int,nargs="+")
    p.add_argument("--maps",choices=list(MAPS),nargs="+")
    p.add_argument("--loads",type=int,nargs="+",help="Override task loads for every selected map")
    p.add_argument("--representations",choices=REPRESENTATIONS,nargs="+",default=list(PRIMARY_REPRESENTATIONS))
    p.add_argument("--suite",choices=["primary","confirmation","both"],default="primary")
    p.add_argument("--config",type=Path,help="JSON object of Config fields; no implicit tuning")
    p.add_argument("--timeout",type=float)
    p.add_argument("--output",type=Path)
    p.add_argument("--instances",type=Path,help="Shared matched task-instance cache; max load must match")
    p.add_argument("--references",type=Path,help="Prepared historical/learned artifacts from prepare_reference_artifacts.py")
    p.add_argument("--no-plots",action="store_true")
    p.add_argument("--no-analysis",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    if not __debug__:p.error("Do not use Python -O; safety assertions must stay enabled")
    config=Config(**json.loads(a.config.read_text(encoding="utf-8"))) if a.config else Config()
    if a.timeout is not None:config=replace(config,timeout=a.timeout)
    config.validate()
    if a.seed_list and (a.seeds is not None or a.seed_start is not None):p.error("Use seed-list OR seeds/seed-start")
    start=a.seed_start if a.seed_start is not None else config.test_seed_start
    count=a.seeds if a.seeds is not None else (1 if a.smoke else 5)
    seeds=a.seed_list or list(range(start,start+count))
    if not seeds or len(set(seeds))!=len(seeds) or min(seeds)<0:p.error("Seeds must be unique nonnegative integers")
    maps=a.maps or (["A"] if a.smoke else list(MAPS))
    if len(set(maps))!=len(maps) or len(set(a.representations))!=len(a.representations):p.error("Duplicate maps/representations")
    loads={m:sorted(set(a.loads or ([20] if a.smoke else MAPS[m]["loads"]))) for m in maps}
    if any(min(v)<1 for v in loads.values()):p.error("Loads must be positive")
    modes=["off"] if a.suite=="primary" else (["on"] if a.suite=="confirmation" else ["off","on"])
    output=(a.output or ROOT/("smoke_results" if a.smoke else "results")).resolve()
    needs_refs=any(r in {"historical_gaussian","learned_gaussian"} for r in a.representations)
    reference_dir=(a.references or ROOT/("reference_smoke" if a.smoke else "reference_artifacts")).resolve() if needs_refs else None
    if needs_refs and not reference_dir.exists() and not a.dry_run:
        p.error(f"Reference artifacts are required but missing: {reference_dir}. Run prepare_reference_artifacts.py first.")
    if needs_refs and reference_dir is not None and reference_dir.exists():
        prep_manifest = reference_dir / "preparation_manifest.json"
        if not prep_manifest.exists():
            p.error(f"Reference preparation manifest is missing: {prep_manifest}")
        prep = json.loads(prep_manifest.read_text(encoding="utf-8"))
        calibration_seeds = {int(x) for x in prep.get("calibration_seeds", [])}
        overlap = calibration_seeds & set(seeds)
        if overlap:
            p.error(f"Calibration/reference seeds overlap the selected formal test seeds: {sorted(overlap)}")
    plan=dict(config=config.to_dict(),seeds=seeds,maps=maps,loads=loads,representations=a.representations,
              modes=modes,protocol="direct",smoke=a.smoke,source_digest=source_digest(),
              reference_dir=str(reference_dir) if reference_dir else None,
              isolation_design=dict(kernel_family=list(KERNEL_FAMILY),source_family=list(SOURCE_FAMILY),
                 source_family_kernel="identical Gaussian",kernel_family_source="identical exact committed reservations"))
    jobs=sum(len(v) for v in loads.values())*len(seeds)*len(a.representations)*len(modes)
    print(json.dumps(dict(output=str(output),direct_instances=len(maps)*len(seeds),trial_runs=jobs,
                          sum_of_planning_budgets_hours=jobs*config.timeout/3600,plan=plan),indent=2),flush=True)
    if a.dry_run:return
    output.mkdir(parents=True,exist_ok=True);(output/"runs").mkdir(exist_ok=True)
    manifest=output/"run_manifest.json"
    if manifest.exists():
        existing=json.loads(manifest.read_text(encoding="utf-8"))
        if existing["plan"]!=plan:raise ValueError("Output contains a different protocol/config/source. Use a new output directory.")
    else:
        write_json(manifest,dict(plan=plan,created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                 environment=dict(python=sys.version,platform=platform.platform(),
                     packages={x:importlib.metadata.version(x) for x in ["numpy","scipy","pandas","matplotlib","torch"]}),
                 statistics_unit="independent map/seed direct task draw; paired across representations"))
    write_json(output/"kernel_calibration.json",kernel_diagnostics(config))
    done=0
    for m in maps:
        for seed in seeds:
            instance=get_instance(a.instances or output/"instances",m,seed,max(loads[m]),config)
            if a.instances:write_json(output/"instances"/f"{m}_seed_{seed}.json",instance)
            print(f"Direct instance {m}/{seed}: max_tasks={max(loads[m])}",flush=True)
            for mode in modes:
                for n in loads[m]:
                    reps=list(a.representations)
                    random.Random(f"execution/{seed}/{m}/{n}/{mode}").shuffle(reps)
                    for rep in reps:
                        path=output/"runs"/f"direct_{m}_{seed}_{n}_{mode}_{rep}.json"
                        if path.exists():done+=1;continue
                        result=trial(instance,n,rep,mode,config,reference_dir=reference_dir)
                        write_json(path,result);done+=1
                        r=result["row"]
                        print(f"[{done}/{jobs}] {m} seed={seed} n={n} {mode} {rep}: {r['success_count']}/{n}, {r['planning_time']:.3f}s {r['run_status']}",flush=True)
            export_results(output)
    export_results(output)
    write_json(output/"completion_status.json",dict(expected=jobs,completed=len(list((output/"runs").glob("*.json"))),all_jobs_complete=done==jobs,independent_seed_count=len(seeds),smoke=a.smoke))
    if not a.no_analysis and a.no_plots:
        analyze(output/"raw_results.csv",config.bootstrap_replicates,config.statistics_seed)
    if not a.no_plots:
        from plot_representation_results import plot
        plot(output/"raw_results.csv",config.bootstrap_replicates,config.statistics_seed)
    print(f"Complete: {output/'raw_results.csv'}",flush=True)

if __name__=="__main__":
    cli()
