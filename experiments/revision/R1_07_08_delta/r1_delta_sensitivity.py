#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R1.7 / R1.8: sensitivity analysis of the lifelong temporal aggregation length delta.

This script reuses the existing lifelong CPS-A* implementation and the same custom-map
experimental settings as Lifelong/test_ourmap.py. It does NOT alter the CPS-A* algorithm.
For each run, delta is set on the already-created ConflictFieldUpdater before planning starts.

Default paper-mode experiment:
    maps        : STANDARD, FRANSEN, RING  (paper Maps A, B, C)
    high-load N : 90, 250, 200 AGVs, respectively
    delta       : 1, 2, 3, 4, 5 time steps
    horizon     : 500
    runs        : 5 paired seeds per setting
    tasks       : MAX_TASKS=100, REPEAT=30 (same as test_ourmap.py)

Outputs are written to Lifelong/r1_delta_results/<timestamp>/:
    raw_results.csv
    summary_results.csv
    delta_sensitivity.png
    run.log

Examples:
    python r1_delta_sensitivity.py
    python r1_delta_sensitivity.py --quick
    python r1_delta_sensitivity.py --deltas 1 2 3 4 5 6 --n-runs 10
    python r1_delta_sensitivity.py --maps STANDARD RING --agv STANDARD=90 RING=200
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# -----------------------------------------------------------------------------
# Robust imports: make the extracted experiment folder runnable on its own.
# -----------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
CPS_DIR = HERE / "CPS_A_lifelong"
pass  # Package imports replace process-wide import-path mutation.
pass  # Package imports replace process-wide import-path mutation.

from experiments.revision.R1_07_08_delta.custom_benchmark_loader import CustomBenchmarkLoader  # noqa: E402
from experiments.revision.R1_07_08_delta.CPS_A_lifelong.path_planner_lifelong import LifelongPlanner as CPS_A  # noqa: E402


# -----------------------------------------------------------------------------
# Settings inherited from Lifelong/test_ourmap.py
# -----------------------------------------------------------------------------
DEFAULT_DELTAS = [1, 2, 3, 4, 5]
DEFAULT_MAPS = ["STANDARD", "FRANSEN", "RING"]
# Highest fleet sizes used by the existing custom-map lifelong benchmark.
DEFAULT_AGVS = {
    "STANDARD": 90,
    "FRANSEN": 250,
    "RING": 200,
}

MAX_TASKS = 100
REPEAT = 30
MAX_TIME = 500
N_RUNS = 5
SEED_BASE = 39
SPEED = 1.0

FORBID_OUTBOUND_INIT = False
PICKUP_STRATEGY = None
PICKUP_REGION = None


def parse_key_value_pairs(items: Iterable[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"Invalid --agv value '{item}'. Expected MAP=NUMBER, e.g. STANDARD=90"
            )
        k, v = item.split("=", 1)
        k = k.strip().upper()
        result[k] = int(v)
    return result


def build_inputs(map_name: str, num_agvs: int, seed: int):
    """Use exactly the same custom-map loader pattern as test_ourmap.py."""
    loader = CustomBenchmarkLoader(map_name)
    return loader.load_all(
        num_agvs=num_agvs,
        speed=SPEED,
        seed=seed,
        max_tasks=MAX_TASKS,
        repeat=REPEAT,
        forbid_outbound_init=FORBID_OUTBOUND_INIT,
        pickup_strategy=PICKUP_STRATEGY,
        pickup_region=PICKUP_REGION,
    )


def run_one(
    map_name: str,
    num_agvs: int,
    delta: int,
    seed: int,
    max_time: int,
    verbose: bool,
    log_handle,
) -> dict:
    """Run one lifelong CPS-A* trial for a given delta.

    Important: no original planner source is edited here. The original updater defaults to
    delta=3. We override only the instance attribute *before* run_lifelong() starts, when all
    congestion dictionaries are still empty. SegmentPlanner holds the same updater object,
    so its waiting-congestion lookup and the dynamic-priority lookup automatically use the
    selected delta as well.
    """

    # Keep the normal console readable; full original planner prints are kept in run.log.
    stream = sys.stdout if verbose else log_handle
    with contextlib.redirect_stdout(stream):
        grid, agv_info, initial_positions, task_queue = build_inputs(
            map_name, num_agvs, seed
        )
        initial_task_queue_size = len(task_queue)

        planner = CPS_A(
            grid,
            agv_info,
            initial_positions,
            task_queue,
            use_priority_replan=True,
        )

        # R1.7 / R1.8 experimental variable.
        # Current original code default is delta=3 in ConflictFieldUpdater.__init__().
        planner.conflict_updater.delta = int(delta)

        wall_start = time.perf_counter()
        completed, total_assigned = planner.run_lifelong(max_time=max_time)
        wall_elapsed = time.perf_counter() - wall_start

    pure_planning_time = wall_elapsed - planner.total_assignment_time
    throughput = planner.get_throughput()
    completed_count = len(completed)
    success_rate = (
        completed_count / total_assigned * 100.0 if total_assigned > 0 else 0.0
    )

    return {
        "map_name": map_name,
        "num_agvs": num_agvs,
        "delta": int(delta),
        "seed": seed,
        "max_time": max_time,
        "initial_task_queue": initial_task_queue_size,
        "completed_tasks": completed_count,
        "total_assigned_tasks": total_assigned,
        "simulation_time": float(planner.current_time),
        "throughput": float(throughput),
        "success_rate": float(success_rate),
        "wall_time": float(wall_elapsed),
        "pure_planning_time": float(pure_planning_time),
    }


def mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), 0.0
    return statistics.mean(values), statistics.stdev(values)


def summarize(raw_rows: List[dict]) -> List[dict]:
    grouped: Dict[Tuple[str, int, int], List[dict]] = {}
    for row in raw_rows:
        key = (row["map_name"], row["num_agvs"], row["delta"])
        grouped.setdefault(key, []).append(row)

    summary_rows: List[dict] = []
    for (map_name, num_agvs, delta), rows in sorted(grouped.items()):
        th_m, th_s = mean_std([r["throughput"] for r in rows])
        sr_m, sr_s = mean_std([r["success_rate"] for r in rows])
        pt_m, pt_s = mean_std([r["pure_planning_time"] for r in rows])
        wt_m, wt_s = mean_std([r["wall_time"] for r in rows])
        comp_m, comp_s = mean_std([r["completed_tasks"] for r in rows])

        summary_rows.append(
            {
                "map_name": map_name,
                "num_agvs": num_agvs,
                "delta": delta,
                "n_runs": len(rows),
                "throughput_mean": th_m,
                "throughput_std": th_s,
                "success_mean": sr_m,
                "success_std": sr_s,
                "planning_time_mean": pt_m,
                "planning_time_std": pt_s,
                "wall_time_mean": wt_m,
                "wall_time_std": wt_s,
                "completed_mean": comp_m,
                "completed_std": comp_s,
            }
        )
    return summary_rows


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_summary(summary_rows: List[dict], out_png: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[WARN] matplotlib unavailable, skip plot: {e}")
        return

    maps = []
    for r in summary_rows:
        if r["map_name"] not in maps:
            maps.append(r["map_name"])

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    metrics = [
        ("throughput_mean", "throughput_std", "Throughput", "Completed tasks / time step"),
        ("success_mean", "success_std", "Task completion success rate", "Success rate (%)"),
        ("planning_time_mean", "planning_time_std", "Planning time", "Pure planning time (s)"),
    ]

    for ax, (mean_col, std_col, title, ylabel) in zip(axes, metrics):
        for map_name in maps:
            rows = [r for r in summary_rows if r["map_name"] == map_name]
            rows.sort(key=lambda x: x["delta"])
            xs = [r["delta"] for r in rows]
            ys = [r[mean_col] for r in rows]
            es = [r[std_col] for r in rows]
            label = f"{map_name} (N={rows[0]['num_agvs']})"
            ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3, label=label)
        ax.set_xlabel(r"Temporal aggregation length $\delta$ (time steps)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.set_xticks(sorted({r["delta"] for r in summary_rows}))

    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


def print_summary(summary_rows: List[dict]) -> None:
    print("\n" + "=" * 98)
    print("R1.7 / R1.8 delta sensitivity summary")
    print("=" * 98)
    hdr = (
        f"{'Map':<10} {'AGVs':>5} {'delta':>5} "
        f"{'Throughput(mean±std)':>24} {'Success%(mean±std)':>24} {'PlanTime(s)':>18}"
    )
    print(hdr)
    print("-" * 98)
    for r in summary_rows:
        print(
            f"{r['map_name']:<10} {r['num_agvs']:>5d} {r['delta']:>5d} "
            f"{r['throughput_mean']:>10.4f}±{r['throughput_std']:<8.4f} "
            f"{r['success_mean']:>10.2f}±{r['success_std']:<8.2f} "
            f"{r['planning_time_mean']:>9.2f}±{r['planning_time_std']:<6.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="R1.7/R1.8 lifelong CPS-A* temporal-slot delta sensitivity experiment"
    )
    parser.add_argument("--deltas", nargs="+", type=int, default=DEFAULT_DELTAS)
    parser.add_argument("--maps", nargs="+", default=DEFAULT_MAPS)
    parser.add_argument(
        "--agv",
        nargs="*",
        default=[],
        metavar="MAP=N",
        help="Override AGV counts, e.g. --agv STANDARD=90 FRANSEN=250 RING=200",
    )
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    parser.add_argument("--max-time", type=int, default=MAX_TIME)
    parser.add_argument("--seed-base", type=int, default=SEED_BASE)
    parser.add_argument("--quick", action="store_true", help="Small smoke test for code verification")
    parser.add_argument("--verbose", action="store_true", help="Show original planner cycle logs")
    args = parser.parse_args()

    maps = [m.upper() for m in args.maps]
    invalid_maps = [m for m in maps if m not in DEFAULT_AGVS]
    if invalid_maps:
        raise SystemExit(f"Unsupported custom map(s): {invalid_maps}; choose from {list(DEFAULT_AGVS)}")

    agv_counts = dict(DEFAULT_AGVS)
    agv_counts.update(parse_key_value_pairs(args.agv))

    deltas = sorted(set(args.deltas))
    if any(d <= 0 for d in deltas):
        raise SystemExit("All delta values must be positive integers.")

    n_runs = args.n_runs
    max_time = args.max_time

    if args.quick:
        # Fast smoke test only; do NOT use these quick results in the paper.
        maps = ["STANDARD"]
        agv_counts["STANDARD"] = 10
        deltas = [1, 3, 5]
        n_runs = 1
        max_time = 60
        print("[QUICK MODE] Smoke test only: STANDARD, 10 AGVs, delta={1,3,5}, 60 time steps.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = HERE / "r1_delta_results" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = out_dir / "raw_results.csv"
    summary_csv = out_dir / "summary_results.csv"
    fig_png = out_dir / "delta_sensitivity.png"
    log_path = out_dir / "run.log"

    print("R1.7/R1.8 settings")
    print(f"  maps       : {maps}")
    print(f"  AGVs       : { {m: agv_counts[m] for m in maps} }")
    print(f"  deltas     : {deltas}")
    print(f"  n_runs     : {n_runs}")
    print(f"  max_time   : {max_time}")
    print(f"  seed_base  : {args.seed_base}")
    print(f"  output     : {out_dir}")
    print("  paired seed design: the same seed/run is reused for every delta on a given map")

    raw_rows: List[dict] = []
    total_jobs = len(maps) * len(deltas) * n_runs
    job_idx = 0

    with log_path.open("w", encoding="utf-8") as log_handle:
        for map_name in maps:
            num_agvs = agv_counts[map_name]
            for run_idx in range(n_runs):
                seed = args.seed_base + run_idx
                # Keep the seed fixed while delta changes -> paired comparison.
                for delta in deltas:
                    job_idx += 1
                    print(
                        f"[{job_idx:>3}/{total_jobs}] map={map_name:<8} N={num_agvs:<4} "
                        f"seed={seed:<3} delta={delta} ... ",
                        end="",
                        flush=True,
                    )
                    try:
                        row = run_one(
                            map_name=map_name,
                            num_agvs=num_agvs,
                            delta=delta,
                            seed=seed,
                            max_time=max_time,
                            verbose=args.verbose,
                            log_handle=log_handle,
                        )
                        raw_rows.append(row)
                        # Save after every trial to protect long experiments.
                        write_csv(raw_csv, raw_rows)
                        print(
                            f"done | th={row['throughput']:.4f}, "
                            f"succ={row['success_rate']:.2f}%, "
                            f"plan={row['pure_planning_time']:.2f}s"
                        )
                    except Exception as exc:
                        print(f"FAILED: {type(exc).__name__}: {exc}")
                        log_handle.write(
                            f"\n[FAILED] map={map_name} N={num_agvs} seed={seed} delta={delta}\n"
                            f"{type(exc).__name__}: {exc}\n"
                        )
                        log_handle.flush()

    if not raw_rows:
        raise SystemExit("No successful runs. Check run.log for details.")

    summary_rows = summarize(raw_rows)
    write_csv(summary_csv, summary_rows)
    plot_summary(summary_rows, fig_png)
    print_summary(summary_rows)

    print("\nSaved:")
    print(f"  raw     : {raw_csv}")
    print(f"  summary : {summary_csv}")
    print(f"  figure  : {fig_png}")
    print(f"  log     : {log_path}")
    print("\nNote: delta=3 is the original ConflictFieldUpdater default and should be marked as the baseline.")


if __name__ == "__main__":
    main()
