#!/usr/bin/env python3
"""Recreate the R2-05 compact figure from the updated 70-trial ZIP.

The layout follows the supplied plot_r2_05_compact.py reference:
five experimental columns, map schematics in the top row, blue mean/error-bar
plots beneath. The figure contains only the two requested performance rows.
No simulations are run.
"""
from __future__ import annotations
import argparse, json, math, zipfile, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.gridspec import GridSpec
from matplotlib import font_manager

METRICS = {
    "throughput": "tasks/step",
    "planning_seconds": "s per 500-step run",
    "traffic_encounter_rate": "fraction",
    "waiting_time": "steps",
    "flow_time": "steps",
    "queue_length": "tasks",
    "arrived": "tasks",
    "completed": "tasks",
    "unfinished": "tasks",
    "actual_arrival_rate": "tasks/step",
}
PLOT_METRICS = ["throughput", "planning_seconds"]
COLORS = {"line": "#267BA5", "shelf": "#AEB4BA", "shelf_edge": "#777F87",
          "station": "#9345BA", "station_edge": "#7B379E"}

def configure_font():
    available = {f.name for f in font_manager.fontManager.ttflist}
    if "Times New Roman" in available:
        family = "Times New Roman"
    elif "Liberation Serif" in available:
        family = "Liberation Serif"
        warnings.warn("Times New Roman is not installed; using Liberation Serif for this render. "
                      "The script will use Times New Roman automatically where installed.")
    else:
        family = "DejaVu Sans"
        warnings.warn("Times New Roman is not installed; using DejaVu Sans for this render.")
    plt.rcParams.update({
        "font.family": family, "font.size": 8.5, "axes.titlesize": 9.0,
        "axes.labelsize": 12, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.spines.top": False, "axes.spines.right": False,
    })
    return family

def standard_map():
    shelves = set()
    for x in range(1, 14, 2):
        for y in list(range(1, 5)) + list(range(6, 10)):
            shelves.add((x, y))
    stations = {(15, y) for y in range(3, 8)}
    return 16, 11, shelves, stations

def fransen_map():
    shelves = {(x, y) for y in (2, 5, 8, 11, 14, 17)
               for x in (2, 5, 8, 11, 14, 17)}
    stations = {(0, 5), (0, 14), (5, 0), (5, 19),
                (14, 0), (14, 19), (19, 5), (19, 14)}
    return 20, 20, shelves, stations

def tile_map(base_map, tiles):
    bw, bh, bs, bt = base_map
    shelves, stations = set(), set()
    for ty in range(tiles):
        for tx in range(tiles):
            dx, dy = tx*bw, ty*bh
            shelves.update((x+dx, y+dy) for x,y in bs)
            stations.update((x+dx, y+dy) for x,y in bt)
    return bw*tiles, bh*tiles, shelves, stations

def draw_map(ax, map_data, title, compact=False, tick_target=5, show_tick_labels=True, label_od=False):
    width, height, shelves, stations = map_data
    ax.set_facecolor("white")
    ax.set_xlim(0, width); ax.set_ylim(0, height)
    ax.set_aspect("equal", adjustable="box")
    grid_step = 5 if compact else 1
    for x in range(0, width+1, grid_step):
        ax.axvline(x, color="#B8BEC5" if x%5==0 else "#E6E9EC",
                   linewidth=0.48 if x%5==0 else 0.25, alpha=.9, zorder=0)
    for y in range(0, height+1, grid_step):
        ax.axhline(y, color="#B8BEC5" if y%5==0 else "#E6E9EC",
                   linewidth=0.48 if y%5==0 else 0.25, alpha=.9, zorder=0)
    if width % grid_step:
        ax.axvline(width, color="#B8BEC5", linewidth=.48, alpha=.9, zorder=0)
    if height % grid_step:
        ax.axhline(height, color="#B8BEC5", linewidth=.48, alpha=.9, zorder=0)
    if compact:
        by_x = {}
        for x,y in shelves: by_x.setdefault(x, set()).add(y)
        for x, ys in by_x.items():
            ys = sorted(ys); start = prev = ys[0]
            for y in ys[1:]:
                if y == prev+1: prev = y
                else:
                    ax.add_patch(Rectangle((x,start),1,prev-start+1,
                        facecolor=COLORS["shelf"],alpha=.78,edgecolor=COLORS["shelf_edge"],
                        linewidth=.22,zorder=2))
                    start = prev = y
            ax.add_patch(Rectangle((x,start),1,prev-start+1,
                facecolor=COLORS["shelf"],alpha=.78,edgecolor=COLORS["shelf_edge"],
                linewidth=.22,zorder=2))
    else:
        for x,y in sorted(shelves):
            ax.add_patch(Rectangle((x,y),1,1,facecolor="gray",alpha=.6,
                                   edgecolor="black",linewidth=.45,zorder=2))
    for x,y in sorted(stations):
        ax.add_patch(Rectangle((x,y),1,1,facecolor=COLORS["station"],alpha=.6,
                               edgecolor=COLORS["station_edge"],linewidth=.45 if compact else .65,zorder=3))
    if label_od:
        # Coordinates are taken from the saved FRANSEN workload JSONs.
        # O1-O8 are pickup/origin cells; D1-D8 are perimeter drop-off cells.
        origins = {
            "O1": (5, 7), "O2": (14, 7), "O3": (5, 12), "O4": (14, 12),
            "O5": (7, 5), "O6": (12, 5), "O7": (7, 14), "O8": (12, 14),
        }
        destinations = {
            "D1": (0, 5), "D2": (0, 14), "D3": (5, 0), "D4": (5, 19),
            "D5": (14, 0), "D6": (14, 19), "D7": (19, 5), "D8": (19, 14),
        }
        origin_offsets = {
            "O1": (-0.15, 0.72), "O2": (0.88, -0.08),
            "O3": (0.78, 0.15), "O4": (0.88, 0.18),
            "O5": (0.18, 0.86), "O6": (0.18, 0.86),
            "O7": (0.18, 0.86), "O8": (0.18, 0.86),
        }
        dest_offsets = {
            "D1": (1.02, 0.12), "D2": (1.02, 0.12),
            "D3": (0.12, 0.94), "D4": (0.12, -0.70),
            "D5": (0.12, 0.94), "D6": (0.12, -0.70),
            "D7": (-1.10, 0.12), "D8": (-1.10, 0.12),
        }
        # Pickup cells: blue circles. Drop-off/workstation cells: purple squares.
        for label, (x, y) in origins.items():
            cx, cy = x + 0.5, y + 0.5
            ax.scatter([cx], [cy], s=22, marker="o", color="#176B9B",
                       edgecolors="white", linewidths=0.7, zorder=6)
            dx, dy = origin_offsets[label]
            ax.annotate(label, (cx, cy), xytext=(cx + dx, cy + dy),
                        textcoords="data", fontsize=6.2, color="#145A80",
                        fontweight="bold", ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.10", fc="white", ec="none", alpha=0.92),
                        zorder=7)
        for label, (x, y) in destinations.items():
            cx, cy = x + 0.5, y + 0.5
            ax.scatter([cx], [cy], s=23, marker="s", color="#9345BA",
                       edgecolors="white", linewidths=0.7, zorder=6)
            dx, dy = dest_offsets[label]
            ax.annotate(label, (cx, cy), xytext=(cx + dx, cy + dy),
                        textcoords="data", fontsize=6.2, color="#7B379E",
                        fontweight="bold", ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.10", fc="white", ec="none", alpha=0.92),
                        zorder=7)
    xstep=max(5,int(math.ceil(width/tick_target/5))*5)
    ystep=max(5,int(math.ceil(height/tick_target/5))*5)
    ax.set_xticks(list(range(0,width+1,xstep))); ax.set_yticks(list(range(0,height+1,ystep)))
    if not show_tick_labels:
        ax.set_xticklabels([]); ax.set_yticklabels([])
    ax.tick_params(axis="both",length=0,pad=2)
    ax.set_title(title,pad=4,fontsize=8.5)
    ax.set_axisbelow(True)

def ci_stats(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n == 0:
        return dict(n=0, mean=np.nan, std=np.nan, ci_low=np.nan, ci_high=np.nan)
    mean = float(a.mean())
    if n == 1:
        return dict(n=1, mean=mean, std=np.nan, ci_low=np.nan, ci_high=np.nan)
    sd = float(a.std(ddof=1))
    half = float(student_t.ppf(.975, n-1) * sd / np.sqrt(n))
    return dict(n=n, mean=mean, std=sd, ci_low=mean-half, ci_high=mean+half)

def read_results_zip(zip_path):
    rows=[]
    with zipfile.ZipFile(zip_path) as z:
        bad=z.testzip()
        if bad is not None: raise ValueError(f"ZIP integrity failed at {bad}")
        manifest=json.loads(z.read("results_formal/manifest.json"))
        spec=manifest["spec"]
        if len(manifest["trials"]) != 70:
            raise ValueError(f"Expected 70 manifest trials, found {len(manifest['trials'])}")
        case_specs={c["name"]:c for c in spec["cases"]}
        for trial in manifest["trials"]:
            if len(trial.get("attempts", [])) != 1:
                raise ValueError(f"Unexpected attempt count: {trial['key']}")
            attempt=trial["attempts"][0]
            base="results_formal/"
            result_path=base+attempt["directory"]+"/result.json"
            workload_path=base+trial["workload"]
            payload=json.loads(z.read(result_path))
            row=dict(payload["row"])
            workload=json.loads(z.read(workload_path))
            case=trial["case"]; seed=int(trial["seed"]); cs=case_specs[case]
            if payload.get("error") is not None:
                raise ValueError(f"Trial error in {trial['key']}: {payload['error']}")
            if trial["state"] != "completed" or attempt["state"] != "completed" or row.get("status") != "completed":
                raise ValueError(f"Incomplete trial: {trial['key']}")
            if row.get("observed_time") != 500 or row.get("horizon") != 500 or not row.get("complete_horizon"):
                raise ValueError(f"Trial did not complete 500 steps: {trial['key']}")
            if not row.get("ledger_valid"):
                raise ValueError(f"Invalid ledger: {trial['key']}")
            if row.get("fleet") != cs["fleet"] or row.get("mode") != cs["mode"] or row.get("arrival_rate") != cs["arrival_rate"]:
                raise ValueError(f"Manifest/result configuration mismatch: {trial['key']}")
            if len(workload.get("requests", [])) != row.get("arrived"):
                raise ValueError(f"Request count does not match arrivals: {trial['key']}")
            if case.startswith("B_traffic_"):
                if row["fleet"] != 200 or len(workload["requests"]) != 3000:
                    raise ValueError(f"Unexpected FRANSEN N/task count: {trial['key']}")
                if {r["release"] for r in workload["requests"]} != {0}:
                    raise ValueError(f"FRANSEN tasks not all released at t=0: {trial['key']}")
            selected={k:row.get(k) for k in [
                "throughput","planning_seconds","traffic_encounter_rate","waiting_time","flow_time",
                "queue_length","arrived","completed","unfinished","actual_arrival_rate",
                "trial_wall_seconds","complete_horizon","ledger_valid","workload_hash","execution_hash"
            ]}
            selected.update({
                "case":case,"seed":seed,"map":row.get("map"),"width":row.get("width"),
                "height":row.get("height"),"fleet":row.get("fleet"),"mode":row.get("mode"),
                "arrival_rate":row.get("arrival_rate"),"horizon":row.get("horizon"),
                "observed_time":row.get("observed_time"),"manifest_state":trial["state"],
                "n_requests":len(workload["requests"]),
                "release_times":"all t=0" if case.startswith("B_traffic_") or row["mode"]=="backlogged" else "Poisson",
                "data_status":"valid_complete"
            })
            rows.append(selected)
    df=pd.DataFrame(rows).sort_values(["case","seed"]).reset_index(drop=True)
    if df.duplicated(["case","seed"]).any(): raise ValueError("Duplicate case/seed records")
    counts=df.groupby("case").size()
    if len(counts) != 14 or not (counts == 5).all():
        raise ValueError(f"Expected 14 conditions × 5 seeds; got {counts.to_dict()}")
    return df, manifest

def summarize(df):
    rows=[]
    for case,g in df.groupby("case",sort=False):
        first=g.iloc[0]
        for metric,unit in METRICS.items():
            vals=pd.to_numeric(g[metric],errors="coerce").dropna().to_numpy() if metric in g else np.array([])
            stats=ci_stats(vals)
            status="valid_complete" if stats["n"]==5 else ("not_applicable" if stats["n"]==0 else "incomplete")
            rows.append({
                "case":case,"map":first["map"],"width":first["width"],"height":first["height"],
                "fleet":first["fleet"],"mode":first["mode"],"arrival_rate":first["arrival_rate"],
                "metric":metric,"unit":unit,**stats,"data_status":status,
                "ci_method":"two-sided 95% Student-t across five independent seeds; ddof=1"
            })
    return pd.DataFrame(rows)

COLUMNS = [
    ("(a) Varying fleet size","16×11",
     ["A_fleet10","A_fleet30","A_fleet50"],["10","30","50"],
     "Number of AGVs",""),
    ("(b) Varying task arrival rate λ","16×11",
     ["A_rate0.25","A_open_base","A_rate1.0","A_rate2.0"],["0.25","0.5","1.0","2.0"],
     "λ (tasks/step)","30 AGVs"),
    ("(c) Varying map size","tiled maps",
     ["A_open_base","A_map2_fixed","A_map3_fixed"],["16×11","32×22","48×33"],
     "Map dimensions","30 AGVs; λ = 0.5 (tasks/step)"),
    ("(d) Scaling map,fleet and λ ","tiled maps",
     ["A_open_base","A_map2_density","A_map3_density"],
     ["16×11\n30 AGVs\nλ = 0.5","32×22\n120 AGVs\nλ = 2.0","48×33\n270 AGVs\nλ = 4.5"],
     "Map / fleet / total arrival rate",""),
    ("(e) Varying congestion potential level","20×20",
     ["B_traffic_dispersed","B_traffic_intermediate","B_traffic_shared"],
     ["Low","Medium","High"],"Congestion potential level",
     "200 AGVs"),
]

def plot(summary, outdir):
    configure_font()
    fig=plt.figure(figsize=(17.8,7.65),facecolor="white")
    gs=GridSpec(3,5,figure=fig,height_ratios=[1.02,1.15,1.15],
        left=.060,right=.992,top=.965,bottom=.115,wspace=.32,hspace=.48,
        width_ratios=[1,1,1.12,1.04,1.16])
    for c,(title,mtitle,cases,labels,xlabel,subtext) in enumerate(COLUMNS):
        if c in (2,3):
            sub=gs[0,c].subgridspec(1,3,wspace=.16)
            for i,k in enumerate((1,2,3)):
                ax=fig.add_subplot(sub[0,i])
                draw_map(ax,tile_map(standard_map(),k),f"{16*k}×{11*k}",
                         show_tick_labels=False,compact=k>1)
                ax.set_title(f"{16*k}×{11*k}",fontsize=8,pad=3)
        else:
            ax=fig.add_subplot(gs[0,c])
            draw_map(ax, fransen_map() if c==4 else standard_map(),
                     "20×20 · O = pickup, D = drop-off" if c==4 else mtitle,
                     label_od=(c==4))
        x=np.arange(len(cases))
        for r,(metric,ylabel,scale) in enumerate([
            ("throughput","Throughput",1.0),
            ("planning_seconds","Planning time(s)",1.0)
        ]):
            ax=fig.add_subplot(gs[r+1,c])
            lookup=summary[summary.metric==metric].set_index("case")
            data=lookup.loc[cases]
            if not ((data["n"]==5).all() and (data["data_status"]=="valid_complete").all()):
                raise ValueError(f"Invalid/missing summary rows for {metric}: {cases}")
            y=data["mean"].to_numpy()*scale
            low=data["ci_low"].to_numpy()*scale; high=data["ci_high"].to_numpy()*scale
            color=COLORS["line"]
            ax.errorbar(x,y,yerr=np.vstack([y-low,high-y]),fmt="o-",color=color,
                ecolor=color,elinewidth=1.25,capsize=3,markersize=4.8,
                markeredgecolor="white",markeredgewidth=.7,linewidth=1.4,zorder=4)
            ax.set_xlim(-.38,len(cases)-.62)
            ax.set_xticks(x)
            shortlabels=[v.split("\n")[0] for v in labels] if r==0 else labels
            ax.set_xticklabels(shortlabels,fontsize=7.5 if c==4 else 8)
            ax.grid(axis="y",color="#D8DEE5",linewidth=.65,alpha=.85)
            ax.set_axisbelow(True)
            limits=([1.25,1.1,.55,4.8,3.10] if r==0 else [10,3.5,1.8,21,37.5])
            ax.set_ylim(0,limits[c])
            from matplotlib.ticker import MaxNLocator
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4,min_n_ticks=4))
            if c==0: ax.set_ylabel(ylabel,labelpad=7)
            if r==0:
                ax.set_title(title,loc="left",pad=23,fontweight="bold",fontsize=9.3)
                ax.text(0,1.045,subtext,transform=ax.transAxes,ha="left",va="bottom",
                        fontsize=7.4,color="#444444")
            if r==1: ax.set_xlabel(xlabel,labelpad=7)
            for i,v in enumerate(y):
                label=f"{v:.3f}" if r==0 else f"{v:.2f}"
                ax.annotate(label,(i,high[i]),xytext=(0,5),textcoords="offset points",
                            ha="center",va="bottom",fontsize=7.2,color="#244354")
    # Global title/subtitle and bottom footnotes are omitted for a cleaner journal figure.
    outdir.mkdir(parents=True,exist_ok=True)
    for ext in ("png","pdf"):
        fig.savefig(outdir/f"R2_05_compact_results.{ext}",dpi=450,facecolor="white",bbox_inches="tight")
    plt.close(fig)


def plot_arrival_rate_diagnostics(summary, outdir):
    """Create an additional figure for queueing effects across arrival rates.

    The existing five-column scalability figure is intentionally unchanged.
    Each point is the mean across five independent seeds; error bars are
    two-sided 95% Student-t confidence intervals across seeds.
    """
    configure_font()

    cases = ["A_rate0.25", "A_open_base", "A_rate1.0", "A_rate2.0"]
    labels = ["0.25", "0.5", "1.0", "2.0"]
    panels = [
        ("queue_length", "Mean queue length", "Tasks"),
        ("waiting_time", "Mean waiting time", "Steps"),
        ("unfinished", "Unfinished tasks at step 500", "Tasks"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.35), facecolor="white")
    fig.subplots_adjust(left=0.075, right=0.99, top=0.83, bottom=0.22, wspace=0.34)

    for ax, (metric, title, ylabel) in zip(axes, panels):
        lookup = summary[summary["metric"] == metric].set_index("case")
        missing = [case for case in cases if case not in lookup.index]
        if missing:
            raise ValueError(f"Missing {metric} summaries for cases: {missing}")

        data = lookup.loc[cases]
        if not ((data["n"] == 5).all() and
                (data["data_status"] == "valid_complete").all()):
            raise ValueError(
                f"Expected five valid complete seeds for {metric}; "
                f"got n={data['n'].tolist()}, "
                f"status={data['data_status'].tolist()}"
            )

        x = np.arange(len(cases))
        y = data["mean"].to_numpy(dtype=float)
        low = data["ci_low"].to_numpy(dtype=float)
        high = data["ci_high"].to_numpy(dtype=float)
        color = COLORS["line"]

        ax.errorbar(
            x, y, yerr=np.vstack([y - low, high - y]),
            fmt="o-", color=color, ecolor=color,
            elinewidth=1.25, capsize=3, markersize=5,
            markeredgecolor="white", markeredgewidth=0.7,
            linewidth=1.4, zorder=4
        )
        ax.set_title(title, loc="left", pad=8, fontweight="bold", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_xlabel("Arrival rate, λ (tasks/step)", labelpad=7)
        ax.set_ylabel(ylabel, labelpad=6)
        ax.grid(axis="y", color="#D8DEE5", linewidth=0.65, alpha=0.85)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Keep the lower bound at zero for interpretable comparisons.
        ax.set_ylim(bottom=0)

    fig.savefig(
        outdir / "R2_05_arrival_rate_queueing_metrics.png",
        dpi=450, facecolor="white", bbox_inches="tight"
    )
    fig.savefig(
        outdir / "R2_05_arrival_rate_queueing_metrics.pdf",
        facecolor="white", bbox_inches="tight"
    )
    plt.close(fig)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-zip",type=Path,default=Path("R2_5_results_formal.zip"))
    parser.add_argument("--output",type=Path,default=Path("R2_05_updated_analysis"))
    args=parser.parse_args()
    df,manifest=read_results_zip(args.results_zip)
    summary=summarize(df)
    args.output.mkdir(parents=True,exist_ok=True)
    df.to_csv(args.output/"R2_05_trial_audit_without_completion_fraction.csv",index=False,encoding="utf-8-sig")
    summary.to_csv(args.output/"R2_05_summary_without_completion_fraction.csv",index=False,encoding="utf-8-sig")
    plot(summary,args.output)
    plot_arrival_rate_diagnostics(summary,args.output)
    print(f"Read {len(df)} valid trials from {args.results_zip}; no simulations run.")
    print(f"Wrote figure, summary and audit to {args.output.resolve()}")

if __name__=="__main__":
    main()
