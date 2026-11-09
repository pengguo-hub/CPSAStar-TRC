#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild figures/tables for the R2-02 controlled congestion-representation experiment.

All figures are generated from the included raw_results.csv and task_results.csv.
Map colors are fixed to match the R1 figure convention:
  Map A = red, Map B = blue, Map C = green.
Within a map, load level and comparator are shown by marker shape/offset, not by map color.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
DATA_DEFAULT = ROOT / "data"
FIG_DEFAULT = ROOT / "figures"
pass  # Package imports replace process-wide import-path mutation.
from statistics_analysis import analyze

MAPS = ["A", "B", "C"]
MAP_COLORS = {"A": "#D62728", "B": "#4C72B0", "C": "#55A868"}  # match R1
REP_ORDER = ["no_field", "raw", "gaussian", "exponential", "linear", "uniform", "historical_gaussian", "learned_gaussian"]
REP_LABELS = {
    "no_field": "No field", "raw": "Raw", "gaussian": "Gaussian",
    "exponential": "Exponential", "linear": "Linear", "uniform": "Uniform",
    "historical_gaussian": "Historical + G", "learned_gaussian": "Learned + G",
}
SHORT_REP_LABELS = {
    "no_field": "None", "raw": "Raw", "gaussian": "Gauss.",
    "exponential": "Exp.", "linear": "Linear", "uniform": "Uniform",
    "historical_gaussian": "Hist.+G", "learned_gaussian": "Learned+G",
}
LOAD_MARKERS = {"low": "o", "high": "s"}
SOURCE_COMPARATORS = ["historical_gaussian", "learned_gaussian"]
SOURCE_MARKERS = {"historical_gaussian": "s", "learned_gaussian": "^"}
KERNEL_COMPARATORS = ["raw", "exponential", "linear", "uniform"]
KERNEL_MARKERS = {"raw": "o", "exponential": "^", "linear": "s", "uniform": "D"}
COND_ORDER = [("A", 50), ("A", 70), ("B", 250), ("B", 280), ("C", 150), ("C", 200)]

plt.rcParams.update({
    "font.family": "DejaVu Serif", "font.size": 9.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42, "ps.fonttype": 42,
    "savefig.facecolor": "white", "figure.facecolor": "white",
})


def _ensure_dirs(fig_root: Path):
    dirs = {
        "paper": fig_root / "01_论文正文候选",
        "response": fig_root / "02_审稿回复专用",
        "supp": fig_root / "03_补充材料候选",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def _save(fig, outbase: Path):
    fig.savefig(outbase.with_suffix(".pdf"), dpi=300, bbox_inches="tight")
    fig.savefig(outbase.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def _ci_y(row, scale=1.0):
    mean = float(row["mean"]) * scale
    lo = row.get("ci95_low", np.nan)
    hi = row.get("ci95_high", np.nan)
    if pd.notna(lo) and pd.notna(hi):
        return mean, np.array([[max(0.0, mean-float(lo)*scale)], [max(0.0, float(hi)*scale-mean)]])
    return mean, None


def _map_loads(manifest):
    loads = manifest.get("plan", {}).get("loads", {})
    return {m: sorted([int(x) for x in loads.get(m, [])]) for m in MAPS}


def validate_data(raw: pd.DataFrame, validation: pd.DataFrame, manifest: dict) -> dict:
    plan = manifest.get("plan", {})
    expected = int(plan.get("seeds", [42,43,44,45,46]).__len__()) * sum(len(v) for v in plan.get("loads", {}).values()) * len(plan.get("representations", REP_ORDER)) * len(plan.get("modes", ["off"]))
    keys = ["map", "task_count", "seed"]
    checks = {
        "raw_rows": int(len(raw)),
        "expected_rows_from_manifest": expected,
        "all_runs_completed": bool((raw["run_status"] == "completed").all()),
        "timeouts": int(raw["timed_out"].sum()),
        "all_condition_seed_groups_share_task_hash": bool((raw.groupby(keys)["task_hash"].nunique() == 1).all()),
        "all_condition_seed_groups_share_order_hash": bool((raw.groupby(keys)["initial_order_hash"].nunique() == 1).all()),
        "all_condition_seed_groups_share_planner_signature": bool((raw.groupby(keys)["common_planner_signature"].nunique() == 1).all()),
        "planner_signatures_globally": int(raw["common_planner_signature"].nunique()),
        "signatures_per_map": {m: int(g["common_planner_signature"].nunique()) for m,g in raw.groupby("map")},
        "all_independent_validations_have_zero_node_conflicts": bool((validation["node_conflicts"].fillna(-1) == 0).all()),
        "all_independent_validations_have_zero_edge_conflicts": bool((validation["edge_conflicts"].fillna(-1) == 0).all()),
        "independent_seed_count": int(raw["seed"].nunique()),
        "representations": sorted(raw["representation"].unique().tolist()),
        "maps": sorted(raw["map"].unique().tolist()),
        "rollback_modes": sorted(raw["rollback_mode"].unique().tolist()),
    }
    checks["all_checks_pass"] = bool(
        checks["raw_rows"] == checks["expected_rows_from_manifest"]
        and checks["all_runs_completed"] and checks["timeouts"] == 0
        and checks["all_condition_seed_groups_share_task_hash"]
        and checks["all_condition_seed_groups_share_order_hash"]
        and checks["all_condition_seed_groups_share_planner_signature"]
        and checks["all_independent_validations_have_zero_node_conflicts"]
        and checks["all_independent_validations_have_zero_edge_conflicts"]
    )
    return checks


def create_tables(data_dir: Path, out_dir: Path, raw: pd.DataFrame, summary: pd.DataFrame, pairs: pd.DataFrame, manifest: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Full summary table: one row per map/load/representation with key metrics and CIs.
    metrics = ["success_rate", "planning_time", "neutral_congestion_exposure", "avg_wait_steps", "avg_path_duration", "gaussian_AC", "avg_path_length", "avg_turns"]
    s = summary[summary["metric"].isin(metrics)].copy()
    value_cols = ["mean", "std", "ci95_low", "ci95_high", "n"]
    pivot = s.pivot_table(index=["map", "task_count", "representation"], columns="metric", values=value_cols, aggfunc="first")
    pivot.columns = [f"{metric}_{stat}" for stat, metric in pivot.columns]
    pivot = pivot.reset_index()
    # Convert success rate to percentage points for human-readable reporting.
    for c in ["success_rate_mean", "success_rate_std", "success_rate_ci95_low", "success_rate_ci95_high"]:
        if c in pivot: pivot[c] = pivot[c] * 100.0
    pivot = pivot.rename(columns={
        "success_rate_mean": "success_rate_mean_pct",
        "success_rate_std": "success_rate_sd_pct",
        "success_rate_ci95_low": "success_rate_ci95_low_pct",
        "success_rate_ci95_high": "success_rate_ci95_high_pct",
        "planning_time_mean": "planning_time_mean_s",
        "planning_time_std": "planning_time_sd_s",
        "planning_time_ci95_low": "planning_time_ci95_low_s",
        "planning_time_ci95_high": "planning_time_ci95_high_s",
        "avg_path_duration_mean": "avg_path_duration_mean_steps",
        "avg_wait_steps_mean": "avg_wait_steps_mean",
    })
    pivot.to_csv(out_dir / "Table_R2_02_summary_by_condition.csv", index=False)

    # Paired effects: Gaussian minus comparator. Exposure is on common successful tasks.
    keep = pairs[
        ((pairs["metric"] == "success_rate") & (pairs["scope"] == "per_load"))
        | ((pairs["metric"] == "neutral_congestion_exposure") & (pairs["scope"] == "common_success_per_load"))
    ].copy()
    keep["effect_interpretation"] = np.where(
        keep["metric"] == "success_rate",
        "Positive means Gaussian has higher success rate (percentage points after conversion)",
        "Negative means Gaussian has lower neutral congestion exposure; conditional on common successful tasks",
    )
    keep["mean_difference_pct_points"] = np.where(keep["metric"] == "success_rate", keep["mean_difference"] * 100, np.nan)
    keep["ci95_low_pct_points"] = np.where(keep["metric"] == "success_rate", keep["ci95_low"] * 100, np.nan)
    keep["ci95_high_pct_points"] = np.where(keep["metric"] == "success_rate", keep["ci95_high"] * 100, np.nan)
    keep.to_csv(out_dir / "Table_R2_02_primary_paired_effects.csv", index=False)
    pairs.to_csv(out_dir / "Table_R2_02_all_paired_statistics.csv", index=False)

    # Map-level descriptive means: equal weighting of the two task-load conditions.
    map_level = pivot.groupby(["map", "representation"], as_index=False).agg(
        success_rate_mean_pct=("success_rate_mean_pct", "mean"),
        planning_time_mean_s=("planning_time_mean_s", "mean"),
        neutral_congestion_exposure_mean=("neutral_congestion_exposure_mean", "mean"),
        avg_wait_steps_mean=("avg_wait_steps_mean", "mean"),
        avg_path_duration_mean_steps=("avg_path_duration_mean_steps", "mean"),
    )
    map_level.to_csv(out_dir / "Table_R2_02_map_level_descriptive_means.csv", index=False)

    # Compact kernel calibration table, copied from the archived run's calibration report.
    cal = json.loads((data_dir / "kernel_calibration.json").read_text(encoding="utf-8"))
    rows = []
    for name, vals in cal.get("kernels", {}).items():
        rows.append({
            "kernel": name,
            "spatial_second_moment": vals.get("spatial_second_moment"),
            "temporal_second_moment": vals.get("temporal_second_moment"),
            "L1_distance_from_gaussian": vals.get("l1_from_gaussian"),
            "calibration_note": ("Reference kernel" if name == "gaussian" else
                                 "Same finite support and matched discrete second moments" if name in {"exponential", "linear"} else
                                 "Same support and mass; second moment is not matched"),
        })
    pd.DataFrame(rows).to_csv(out_dir / "Table_R2_02_kernel_calibration.csv", index=False)


def plot_main_absolute(summary: pd.DataFrame, outbase: Path, loads_by_map):
    fig, axes = plt.subplots(2, 3, figsize=(16.8, 7.6), squeeze=False)
    metrics = [
        ("success_rate", "Planning success rate (%)", 100.0, (0, 100)),
        ("neutral_congestion_exposure", "Neutral occupancy exposure", 1.0, (0, 0.42)),
    ]
    x = np.arange(len(REP_ORDER), dtype=float)
    for col, m in enumerate(MAPS):
        color = MAP_COLORS[m]
        loads = loads_by_map[m]
        low, high = loads[0], loads[-1]
        for row, (metric, ylabel, scale, ylim) in enumerate(metrics):
            ax = axes[row, col]
            sub = summary[(summary["map"] == m) & (summary["metric"] == metric)]
            for load, marker, offset in [(low, "o", -0.13), (high, "s", 0.13)]:
                for i, rep in enumerate(REP_ORDER):
                    z = sub[(sub["task_count"] == load) & (sub["representation"] == rep)]
                    if z.empty: continue
                    r = z.iloc[0]
                    y = float(r["mean"]) * scale
                    lo, hi = float(r["ci95_low"]) * scale, float(r["ci95_high"]) * scale
                    ax.errorbar(i + offset, y, yerr=np.array([[max(0, y-lo)], [max(0, hi-y)]]),
                                fmt=marker, color=color, ecolor=color, markersize=4.8,
                                markerfacecolor=color, markeredgecolor="white", markeredgewidth=0.5,
                                elinewidth=1.0, capsize=2.2, alpha=0.95)
            ax.set_title(f"Map {m}  ({low}/{high} tasks)", color=color, fontweight="bold")
            ax.set_xticks(x, [SHORT_REP_LABELS[r] for r in REP_ORDER], rotation=28, ha="right")
            ax.grid(axis="y", alpha=0.23)
            ax.set_ylim(*ylim)
            if col == 0: ax.set_ylabel(ylabel)
            if row == 0: ax.set_xlabel("")
            else: ax.set_xlabel("Congestion representation")
    load_handles = [
        Line2D([0],[0],marker="o",color="#333333",linestyle="None",markersize=6,label="Lower load"),
        Line2D([0],[0],marker="s",color="#333333",linestyle="None",markersize=6,label="Higher load"),
    ]
    map_handles = [Line2D([0],[0],color=MAP_COLORS[m],lw=3,label=f"Map {m}") for m in MAPS]
    fig.legend(handles=load_handles + map_handles, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.5, -0.015))
    fig.suptitle("Direct controlled comparison of congestion representations", y=1.015, fontsize=13, fontweight="bold")
    fig.text(0.5, -0.055,
             "Points are means over 5 matched seeds; bars are pointwise 95% seed-bootstrap CIs. "
             "Exposure is evaluated using the same post-hoc local raw-occupancy measure and is conditional on successful paths.",
             ha="center", va="top", fontsize=8)
    fig.tight_layout(rect=(0, 0.07, 1, 0.98))
    _save(fig, outbase)


def plot_paired_effects(pairs: pd.DataFrame, outbase: Path, family: str):
    if family == "source":
        comparators = SOURCE_COMPARATORS
        labels = {"historical_gaussian": "Historical + same Gaussian", "learned_gaussian": "Learned + same Gaussian"}
        markers = SOURCE_MARKERS
        scopes = {"success_rate": "per_load", "neutral_congestion_exposure": "common_success_per_load"}
        title = "Information-source isolation: exact reservations vs indirect fields"
        stem = "A"
    else:
        comparators = KERNEL_COMPARATORS
        labels = {"raw": "Raw occupancy", "exponential": "Exponential", "linear": "Linear", "uniform": "Uniform"}
        markers = KERNEL_MARKERS
        scopes = {"success_rate": "per_load", "neutral_congestion_exposure": "common_success_per_load"}
        title = "Kernel isolation: Gaussian vs alternative representations"
        stem = "B"
    fig, axes = plt.subplots(2, 1, figsize=(13.8, 7.7), squeeze=False)
    conditions = COND_ORDER
    xbase = np.arange(len(conditions), dtype=float)
    offsets = np.linspace(-0.23, 0.23, len(comparators)) if len(comparators) > 2 else np.array([-0.12, 0.12])
    plot_specs = [
        ("success_rate", "Gaussian − comparator: success rate (percentage points)", 100.0,
         "Positive favours Gaussian"),
        ("neutral_congestion_exposure", "Gaussian − comparator: neutral congestion exposure",
         1.0, "Negative means lower exposure under Gaussian"),
    ]
    for row, (metric, ylabel, scale, subtitle) in enumerate(plot_specs):
        ax = axes[row, 0]
        scope = scopes[metric]
        data = pairs[(pairs["metric"] == metric) & (pairs["scope"] == scope)].copy()
        data["task_count_num"] = pd.to_numeric(data["task_count"], errors="coerce")
        for ci, (m, n) in enumerate(conditions):
            for j, comp in enumerate(comparators):
                z = data[(data["map"] == m) & (data["task_count_num"] == n) & (data["comparator"] == comp)]
                if z.empty: continue
                r = z.iloc[0]
                y = float(r["mean_difference"]) * scale
                lo = float(r["ci95_low"]) * scale
                hi = float(r["ci95_high"]) * scale
                color = MAP_COLORS[m]
                ax.errorbar(ci + offsets[j], y, yerr=np.array([[max(0, y-lo)], [max(0, hi-y)]]),
                            fmt=markers[comp], color=color, ecolor=color, markersize=5.4,
                            markerfacecolor=color, markeredgecolor="white", markeredgewidth=0.5,
                            capsize=2.4, elinewidth=1.0, linestyle="None")
        ax.axhline(0, color="#333333", linewidth=0.9, linestyle="--")
        for sep in [1.5, 3.5]: ax.axvline(sep, color="#999999", linewidth=0.7, linestyle=":")
        ax.set_xticks(xbase, [f"{m}\n{n}" for m,n in conditions])
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.22)
        ax.text(0.01, 0.97, subtitle, transform=ax.transAxes, va="top", ha="left", fontsize=8.5,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=2))
        if metric == "success_rate":
            ax.set_ylim(-8.5, 8.5) if family == "source" else ax.set_ylim(-4.0, 4.0)
        else:
            # Same y scale across the six conditions so map-level patterns remain comparable.
            all_lo = pd.to_numeric(data[data.comparator.isin(comparators)]["ci95_low"], errors="coerce").min()
            all_hi = pd.to_numeric(data[data.comparator.isin(comparators)]["ci95_high"], errors="coerce").max()
            pad = max(0.002, (all_hi-all_lo)*0.12)
            ax.set_ylim(float(all_lo)-pad, float(all_hi)+pad)
    map_handles = [Line2D([0],[0],color=MAP_COLORS[m],lw=3,label=f"Map {m}") for m in MAPS]
    comp_handles = [Line2D([0],[0],marker=markers[c],color="#444444",linestyle="None",
                           markerfacecolor="white",markeredgewidth=1.1,markersize=6,label=labels[c]) for c in comparators]
    fig.legend(handles=map_handles+comp_handles, loc="lower center", ncol=min(7, len(map_handles)+len(comp_handles)),
               frameon=False, bbox_to_anchor=(0.5, -0.012), fontsize=8)
    fig.suptitle(title, y=1.01, fontsize=12.5, fontweight="bold")
    fig.text(0.5, -0.065,
             "Paired differences use the same five seeds for each condition. Error bars are pointwise 95% paired-seed bootstrap CIs, not multiplicity-adjusted. "
             "Exposure comparisons are restricted to task IDs successful under both methods. Holm-adjusted p-values are provided in the CSV table.",
             ha="center", va="top", fontsize=7.8)
    fig.tight_layout(rect=(0, 0.08, 1, 0.97))
    _save(fig, outbase)


def plot_runtime(summary: pd.DataFrame, outbase: Path, loads_by_map):
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4), squeeze=False)
    x = np.arange(len(REP_ORDER), dtype=float)
    for col, m in enumerate(MAPS):
        ax = axes[0, col]; color = MAP_COLORS[m]
        low, high = loads_by_map[m][0], loads_by_map[m][-1]
        sub = summary[(summary["map"] == m) & (summary["metric"] == "planning_time")]
        for load, marker, offset in [(low,"o",-0.13),(high,"s",0.13)]:
            for i, rep in enumerate(REP_ORDER):
                z = sub[(sub.task_count==load)&(sub.representation==rep)]
                if z.empty: continue
                r=z.iloc[0]; y=float(r["mean"]); lo=float(r["ci95_low"]); hi=float(r["ci95_high"])
                ax.errorbar(i+offset,y,yerr=[[max(0,y-lo)],[max(0,hi-y)]],fmt=marker,color=color,ecolor=color,
                            markersize=4.8,markeredgecolor="white",markeredgewidth=.5,capsize=2,elinewidth=1)
        ax.set_title(f"Map {m} ({low}/{high} tasks)", color=color, fontweight="bold")
        ax.set_xticks(x,[SHORT_REP_LABELS[r] for r in REP_ORDER],rotation=28,ha="right")
        ax.grid(axis="y",alpha=.22);ax.set_ylim(bottom=0)
        if col==0:ax.set_ylabel("Total planning wall time (s)")
        ax.set_xlabel("Congestion representation")
    handles=[Line2D([0],[0],marker="o",color="#333333",linestyle="None",label="Lower load"),
             Line2D([0],[0],marker="s",color="#333333",linestyle="None",label="Higher load")]
    fig.legend(handles=handles,loc="lower center",ncol=2,frameon=False,bbox_to_anchor=(.5,-.02))
    fig.suptitle("Planning-time cost of the controlled representations",y=1.02,fontsize=12.5,fontweight="bold")
    fig.text(.5,-.075,"Planning time includes field initialization and search/update time. Points are means over five seeds; bars are pointwise 95% bootstrap CIs.",ha="center",va="top",fontsize=8)
    fig.tight_layout(rect=(0,.08,1,.96));_save(fig,outbase)


def plot_secondary(summary: pd.DataFrame, outbase: Path, loads_by_map):
    fig, axes = plt.subplots(2,3,figsize=(16.2,7.4),squeeze=False)
    specs=[("avg_wait_steps","Mean waiting steps (successful tasks only)",(0,5.5)),
           ("avg_path_duration","Mean path duration (steps; successful tasks only)",(0,50))]
    x=np.arange(len(REP_ORDER),dtype=float)
    for row,(metric,label,ylim) in enumerate(specs):
        for col,m in enumerate(MAPS):
            ax=axes[row,col];color=MAP_COLORS[m];low,high=loads_by_map[m][0],loads_by_map[m][-1]
            sub=summary[(summary["map"]==m)&(summary["metric"]==metric)]
            for load,marker,offset in [(low,"o",-.13),(high,"s",.13)]:
                for i,rep in enumerate(REP_ORDER):
                    z=sub[(sub.task_count==load)&(sub.representation==rep)]
                    if z.empty:continue
                    r=z.iloc[0];y=float(r["mean"]);lo=float(r["ci95_low"]);hi=float(r["ci95_high"])
                    ax.errorbar(i+offset,y,yerr=[[max(0,y-lo)],[max(0,hi-y)]],fmt=marker,color=color,ecolor=color,
                                markersize=4.4,markeredgecolor="white",markeredgewidth=.5,capsize=2,elinewidth=.9)
            ax.set_title(f"Map {m} ({low}/{high} tasks)",color=color,fontweight="bold")
            ax.set_xticks(x,[SHORT_REP_LABELS[r] for r in REP_ORDER],rotation=28,ha="right")
            ax.set_ylim(*ylim);ax.grid(axis="y",alpha=.22)
            if col==0:ax.set_ylabel(label)
            if row==1:ax.set_xlabel("Congestion representation")
    handles=[Line2D([0],[0],marker="o",color="#333333",linestyle="None",label="Lower load"),
             Line2D([0],[0],marker="s",color="#333333",linestyle="None",label="Higher load")]
    fig.legend(handles=handles,loc="lower center",ncol=2,frameon=False,bbox_to_anchor=(.5,-.015))
    fig.suptitle("Secondary route-efficiency diagnostics",y=1.015,fontsize=12.5,fontweight="bold")
    fig.text(.5,-.07,"Waiting steps and path duration are averaged only over successfully planned tasks; interpret alongside success rate to avoid survivor bias.",ha="center",va="top",fontsize=8)
    fig.tight_layout(rect=(0,.07,1,.97));_save(fig,outbase)


def plot_gaussian_ac(summary: pd.DataFrame, outbase: Path, loads_by_map):
    fig,axes=plt.subplots(1,3,figsize=(15.5,4.4),squeeze=False);x=np.arange(len(REP_ORDER),dtype=float)
    for col,m in enumerate(MAPS):
        ax=axes[0,col];color=MAP_COLORS[m];low,high=loads_by_map[m][0],loads_by_map[m][-1]
        sub=summary[(summary["map"]==m)&(summary["metric"]=="gaussian_AC")]
        for load,marker,offset in [(low,"o",-.13),(high,"s",.13)]:
            for i,rep in enumerate(REP_ORDER):
                z=sub[(sub.task_count==load)&(sub.representation==rep)]
                if z.empty:continue
                r=z.iloc[0];y=float(r["mean"]);lo=float(r["ci95_low"]);hi=float(r["ci95_high"])
                ax.errorbar(i+offset,y,yerr=[[max(0,y-lo)],[max(0,hi-y)]],fmt=marker,color=color,ecolor=color,
                            markersize=4.8,markeredgecolor="white",markeredgewidth=.5,capsize=2,elinewidth=1)
        ax.set_title(f"Map {m} ({low}/{high} tasks)",color=color,fontweight="bold")
        ax.set_xticks(x,[SHORT_REP_LABELS[r] for r in REP_ORDER],rotation=28,ha="right")
        ax.set_ylim(bottom=0);ax.grid(axis="y",alpha=.22)
        if col==0:ax.set_ylabel("Post-hoc fixed-Gaussian AC")
        ax.set_xlabel("Congestion representation")
    handles=[Line2D([0],[0],marker="o",color="#333333",linestyle="None",label="Lower load"),
             Line2D([0],[0],marker="s",color="#333333",linestyle="None",label="Higher load")]
    fig.legend(handles=handles,loc="lower center",ncol=2,frameon=False,bbox_to_anchor=(.5,-.02))
    fig.suptitle("Supplementary congestion-exposure diagnostic",y=1.02,fontsize=12.5,fontweight="bold")
    fig.text(.5,-.075,"AC is recomputed post hoc using the same Gaussian evaluator for all methods; it is secondary and is not the decision field used by every method.",ha="center",va="top",fontsize=8)
    fig.tight_layout(rect=(0,.08,1,.96));_save(fig,outbase)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=DATA_DEFAULT,help="Folder containing raw_results.csv, task_results.csv, run_manifest.json, kernel_calibration.json, run_validation.csv")
    parser.add_argument("--output-dir",type=Path,default=FIG_DEFAULT,help="Output folder for figure sets")
    parser.add_argument("--bootstrap",type=int,default=10000,help="Number of bootstrap resamples used for CIs/statistics")
    parser.add_argument("--seed",type=int,default=20261017,help="Seed for reproducible bootstrap resampling")
    a=parser.parse_args()
    data_dir=a.data_dir.resolve();out_root=a.output_dir.resolve()
    raw_path=data_dir/"raw_results.csv"
    if not raw_path.exists():raise FileNotFoundError(f"Missing {raw_path}")
    for needed in ["task_results.csv","run_manifest.json","kernel_calibration.json","run_validation.csv"]:
        if not (data_dir/needed).exists():raise FileNotFoundError(f"Missing {data_dir/needed}")
    raw=pd.read_csv(raw_path)
    manifest=json.loads((data_dir/"run_manifest.json").read_text(encoding="utf-8"))
    validation=pd.read_csv(data_dir/"run_validation.csv")
    checks=validate_data(raw,validation,manifest)
    (out_root.parent/"validation_summary.json").write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding="utf-8")
    if not checks["all_checks_pass"]:
        print("WARNING: one or more data-integrity checks failed; inspect validation_summary.json",file=sys.stderr)
    # Generate the reproducible summary and paired statistics beside raw_results.csv.
    summary,_=analyze(raw_path,a.bootstrap,a.seed)
    summary=pd.read_csv(data_dir/"summary_results.csv")
    pairs=pd.read_csv(data_dir/"pairwise_statistics.csv")
    dirs=_ensure_dirs(out_root)
    create_tables(data_dir,out_root.parent/"tables",raw,summary,pairs,manifest)
    plot_main_absolute(summary,dirs["paper"] / "Fig_R2_02_main_success_exposure",_map_loads(manifest))
    plot_paired_effects(pairs,dirs["response"] / "Fig_R2_02A_information_source_effects","source")
    plot_paired_effects(pairs,dirs["response"] / "Fig_R2_02B_kernel_effects","kernel")
    plot_runtime(summary,dirs["supp"] / "Fig_R2_02C_planning_time",_map_loads(manifest))
    plot_secondary(summary,dirs["supp"] / "Fig_R2_02D_wait_duration",_map_loads(manifest))
    plot_gaussian_ac(summary,dirs["supp"] / "Fig_R2_02E_fixed_gaussian_AC",_map_loads(manifest))
    print(f"Data checks: {'PASS' if checks['all_checks_pass'] else 'CHECK WARNINGS'}")
    print(f"Figures written to: {out_root}")
    print(f"Tables written to: {out_root.parent/'tables'}")

if __name__=="__main__":
    main()
