#!/usr/bin/env python3
"""Map-A-only pairwise interactions for omega (look-ahead congestion weight)."""
from __future__ import annotations
import argparse, json
from dataclasses import replace
from pathlib import Path
import pandas as pd
from config import Config, TASK_COUNTS
from instances import get_task_instance, write_json, canonical_hash
from experiment_core import run_trial
from evaluation import RUN_METRICS
from statistics_analysis import ci_mean, rng_for

# All values are grounded in the existing manuscript/R2-03 protocol:
# omega {10, 50, 100} are selected from the manuscript's omega candidate list;
# sigma values reuse the R1 Gaussian sweep; K values reuse the manuscript's NU-K sweep.
OMEGA_VALUES = (10.0, 50.0, 100.0)
SIGMA_VALUES = (0.5, 1.0, 2.0, 4.0)
UPDATE_INTERVAL_VALUES = (1, 10, 20, 30, 40)
MAP_NAME = "A"


def cfg_key(c):
    return canonical_hash(c.to_dict())


def build_studies(base, smoke=False):
    omegas = (10.0, 50.0) if smoke else OMEGA_VALUES
    sigmas = (1.0, 2.0) if smoke else SIGMA_VALUES
    intervals = (1, 20) if smoke else UPDATE_INTERVAL_VALUES
    studies = {"omega_sigma_l": {}, "omega_sigma_t": {}, "omega_K": {}}
    # omega x sigma_l: hold sigma_t at the formal baseline (2).
    for omega in omegas:
        for sigma_l in sigmas:
            c = replace(base, omega=float(omega), sigma_l=float(sigma_l), sigma_t=2.0)
            studies["omega_sigma_l"][f"omega={omega:g}__sigma_l={sigma_l:g}"] = c
    # omega x sigma_t: hold sigma_l at the same formal baseline (2).
    for omega in omegas:
        for sigma_t in sigmas:
            c = replace(base, omega=float(omega), sigma_l=2.0, sigma_t=float(sigma_t))
            studies["omega_sigma_t"][f"omega={omega:g}__sigma_t={sigma_t:g}"] = c
    # omega x update interval K.
    for omega in omegas:
        for k in intervals:
            c = replace(base, omega=float(omega), update_interval=int(k))
            studies["omega_K"][f"omega={omega:g}__K={k}"] = c
    return studies


def _execute_job(task_instance, config_dict):
    """Process-pool worker: each task/config pair has an isolated planner."""
    cfg = Config(**config_dict).validate()
    return run_trial(task_instance, cfg)


def main():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("results_omega_interactions"))
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--seed-start", type=int, default=10000)
    p.add_argument("--workers", type=int, default=4, help="Parallel independent planner runs; default 4")
    p.add_argument("--smoke", action="store_true", help="Small engineering check; not formal evidence")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.seeds < 1:
        p.error("--seeds must be >= 1")
    if args.workers < 1:
        p.error("--workers must be >= 1")
    base = Config(seed_start=args.seed_start).validate()
    seeds = [args.seed_start] if args.smoke else list(range(args.seed_start, args.seed_start + args.seeds))
    studies = build_studies(base, args.smoke)
    unique = {cfg_key(c): c for cells in studies.values() for c in cells.values()}
    loads = (5,) if args.smoke else TASK_COUNTS[MAP_NAME]
    map_load_seed_n = len(loads) * len(seeds)
    actual_expected = len(unique) * map_load_seed_n
    logical_expected = sum(len(cells) for cells in studies.values()) * map_load_seed_n
    plan = {
        "experiment": "omega pairwise interactions (Map A only)",
        "map": MAP_NAME,
        "task_counts": list(loads),
        "seeds": seeds,
        "baseline": base.to_dict(),
        "lookahead_enabled": True,
        "omega_candidates": list((10.0, 50.0) if args.smoke else OMEGA_VALUES),
        "sigma_candidates": list((1.0, 2.0) if args.smoke else SIGMA_VALUES),
        "K_candidates": list((1, 20) if args.smoke else UPDATE_INTERVAL_VALUES),
        "studies": {name: {cell: cfg.to_dict() for cell, cfg in cells.items()} for name, cells in studies.items()},
        "unique_configs_per_map_load_seed": len(unique),
        "map_load_seed_combinations": map_load_seed_n,
        "expected_actual_executions": actual_expected,
        "expected_logical_rows": logical_expected,
        "workers": args.workers,
        "pairing": "For each Map-A load and seed, identical cached task instances are reused across all parameter configurations; each run starts from empty reservations and plans the complete one-shot task batch.",
        "note": "Smoke mode is engineering validation only, not formal experimental evidence."
    }
    print(json.dumps(plan, indent=2), flush=True)
    if args.dry_run:
        return

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "omega_interactions_manifest.json", plan)
    task_instances = {}
    result_cache = {}
    jobs = []
    for task_count in loads:
        for seed in seeds:
            inst = get_task_instance(out / "shared_tasks", MAP_NAME, task_count, seed)
            task_instances[(task_count, seed)] = inst
            for key, cfg in unique.items():
                runfile = out / "runs" / f"A_N{task_count}_seed{seed}_{key[:12]}.json"
                if runfile.exists():
                    row = json.loads(runfile.read_text(encoding="utf-8"))
                    if row["task_hash"] != inst["task_hash"]:
                        raise AssertionError(f"Cached task hash mismatch in {runfile}")
                    result_cache[(task_count, seed, key)] = row
                else:
                    jobs.append((task_count, seed, key, cfg, inst, runfile))

    print(f"Unique configs={len(unique)}; expected actual executions={actual_expected}; pending uncached runs={len(jobs)}; workers={args.workers}", flush=True)
    completed_new = 0
    if jobs:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            future_map = {
                pool.submit(_execute_job, inst, cfg.to_dict()): (task_count, seed, key, cfg, inst, runfile)
                for task_count, seed, key, cfg, inst, runfile in jobs
            }
            for future in as_completed(future_map):
                task_count, seed, key, cfg, inst, runfile = future_map[future]
                row = future.result()
                if row["task_hash"] != inst["task_hash"]:
                    raise AssertionError("Paired-task hash mismatch")
                if not row["use_lookahead_congestion"]:
                    raise AssertionError("Map A must enable the look-ahead congestion term")
                write_json(runfile, row)
                result_cache[(task_count, seed, key)] = row
                completed_new += 1
                print(f"OMEGA A N={task_count} seed={seed} cfg={key[:8]} omega={cfg.omega:g} K={cfg.update_interval} success={row['success_count']}/{task_count} [{completed_new}/{len(jobs)} new]", flush=True)

    logical_rows = []
    for task_count in loads:
        for seed in seeds:
            inst = task_instances[(task_count, seed)]
            for study, cells in studies.items():
                for cell, cfg in cells.items():
                    row = dict(result_cache[(task_count, seed, cfg_key(cfg))])
                    if row["task_hash"] != inst["task_hash"]:
                        raise AssertionError("Task pairing failed")
                    row.update(study=study, cell=cell)
                    logical_rows.append(row)
    raw = pd.DataFrame(logical_rows)
    nunique = raw.groupby(["map", "task_count", "seed"])["task_hash"].nunique()
    if int(nunique.max()) != 1:
        raise AssertionError("Task instances are not paired within map/load/seed")
    raw.to_csv(out / "omega_interactions_raw_results.csv", index=False)
    summary = []
    for (study, task_count, cell), group in raw.groupby(["study", "task_count", "cell"], sort=True):
        for metric in RUN_METRICS:
            d = dict(study=study, map=MAP_NAME, task_count=int(task_count), cell=cell, metric=metric)
            d.update(ci_mean(group[metric], rng_for(base.statistics_seed, (study, MAP_NAME, task_count, cell, metric)),
                             2000 if args.smoke else base.bootstrap_replicates))
            summary.append(d)
    pd.DataFrame(summary).to_csv(out / "omega_interactions_summary.csv", index=False)
    status = {
        "actual_executions": len(result_cache),
        "expected_actual_executions": actual_expected,
        "newly_executed_this_invocation": completed_new,
        "logical_rows": len(raw),
        "expected_logical_rows": logical_expected,
        "unique_task_hashes_per_map_load_seed": int(nunique.max()),
        "all_runs_use_map_a_lookahead": bool(raw["use_lookahead_congestion"].all()),
        "smoke": bool(args.smoke),
        "seeds": seeds,
        "task_counts": list(loads),
    }
    write_json(out / "omega_interactions_completion_status.json", status)
    if len(result_cache) != actual_expected or len(raw) != logical_expected:
        raise AssertionError(f"Incomplete experiment: {status}")
    print("COMPLETED", json.dumps(status), flush=True)

if __name__ == "__main__":
    main()
