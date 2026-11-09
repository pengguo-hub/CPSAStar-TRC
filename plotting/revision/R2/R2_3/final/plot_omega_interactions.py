#!/usr/bin/env python3
"""Plot Map-A omega interaction results from the experiment's own CSV files."""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

STUDIES = {
    "omega_sigma_l": {"title": r"$\omega \times \sigma_l$", "x": "omega", "y": "sigma_l",
        "x_label": r"$\omega$", "y_label": r"$\sigma_l$", "x_values": [10.0, 50.0, 100.0],
        "y_values": [0.5, 1.0, 2.0, 4.0], "baseline": {"omega": 50.0, "sigma_l": 2.0},
        "baseline_cell": "omega=50__sigma_l=2"},
    "omega_sigma_t": {"title": r"$\omega \times \sigma_t$", "x": "omega", "y": "sigma_t",
        "x_label": r"$\omega$", "y_label": r"$\sigma_t$", "x_values": [10.0, 50.0, 100.0],
        "y_values": [0.5, 1.0, 2.0, 4.0], "baseline": {"omega": 50.0, "sigma_t": 2.0},
        "baseline_cell": "omega=50__sigma_t=2"},
    "omega_K": {"title": r"$\omega \times K$", "x": "K", "y": "omega",
        "x_label": r"$K$ (field-update interval)", "y_label": r"$\omega$", "x_values": [1, 10, 20, 30, 40],
        "y_values": [10.0, 50.0, 100.0], "baseline": {"K": 20, "omega": 50.0},
        "baseline_cell": "omega=50__K=20"},
}
LOADS = {50: "Lower load (N=50)", 70: "Higher load (N=70)"}
MAP_COLOR = "#D62728"
LOW_STYLE, HIGH_STYLE = "-", "--"

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "font.size": 10, "axes.labelsize": 10,
                     "axes.titlesize": 11, "legend.fontsize": 9, "xtick.labelsize": 9,
                     "ytick.labelsize": 9, "pdf.fonttype": 42, "ps.fonttype": 42})


def parse_cell(cell):
    out = {}
    for part in str(cell).split("__"):
        k, v = part.split("=")
        out[k] = float(v)
    return out


def fmt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:g}"


def validate_results(root):
    raw_path = root / "omega_interactions_raw_results.csv"
    sum_path = root / "omega_interactions_summary.csv"
    status_path = root / "omega_interactions_completion_status.json"
    raw = pd.read_csv(raw_path)
    summary = pd.read_csv(sum_path)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("smoke") is not False:
        raise ValueError("Publication plots require a completed formal run (smoke=false).")
    if status["actual_executions"] != status["expected_actual_executions"]:
        raise ValueError("Formal execution count incomplete.")
    if set(raw["seed"].unique()) != {10000, 10001, 10002, 10003, 10004}:
        raise ValueError("Unexpected seed set.")
    if set(raw["task_count"].unique()) != {50, 70}:
        raise ValueError("Unexpected Map A task loads.")
    if set(raw["map"].unique()) != {"A"} or not raw["use_lookahead_congestion"].astype(bool).all():
        raise ValueError("This package must contain Map-A runs with look-ahead enabled only.")
    if set(raw["study"].unique()) != set(STUDIES):
        raise ValueError("Missing or unexpected omega interaction studies.")
    if raw.groupby(["map", "task_count", "seed"])["task_hash"].nunique().max() != 1:
        raise ValueError("Paired task-instance validation failed.")
    if set(summary["n"].unique()) != {5}:
        raise ValueError("Each plotted summary cell must have five seeds.")
    return raw, summary


def matrix_for(study, load, summary):
    spec = STUDIES[study]
    df = summary[(summary.study == study) & (summary.task_count == load) & (summary.metric == "success_rate")]
    matrix = np.full((len(spec["y_values"]), len(spec["x_values"])), np.nan)
    for _, row in df.iterrows():
        p = parse_cell(row.cell)
        xi = next(i for i, v in enumerate(spec["x_values"]) if float(v) == float(p[spec["x"]]))
        yi = next(i for i, v in enumerate(spec["y_values"]) if float(v) == float(p[spec["y"]]))
        matrix[yi, xi] = float(row["mean"]) * 100
    if np.isnan(matrix).any():
        raise ValueError(f"Incomplete heatmap matrix: {study}, N={load}")
    b = df[df.cell == spec["baseline_cell"]]
    if len(b) != 1:
        raise ValueError(f"Missing baseline cell: {study}")
    return matrix, float(b.iloc[0]["mean"]) * 100


def draw_heatmap(ax, study, summary, vmax=6.0):
    spec = STUDIES[study]
    matrix, baseline = matrix_for(study, 70, summary)
    delta = matrix - baseline
    im = ax.imshow(delta, cmap="RdBu", vmin=-vmax, vmax=vmax, aspect="auto", origin="upper")
    ax.set_xticks(np.arange(len(spec["x_values"])), [fmt(v) for v in spec["x_values"]])
    ax.set_yticks(np.arange(len(spec["y_values"])), [fmt(v) for v in spec["y_values"]])
    ax.set_xlabel(spec["x_label"])
    ax.set_ylabel(spec["y_label"])
    ax.set_title(spec["title"], pad=8)
    for yi in range(delta.shape[0]):
        for xi in range(delta.shape[1]):
            val = delta[yi, xi]
            ax.text(xi, yi, f"{val:+.1f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(val) >= 3.3 else "black")
    bx = next(i for i, v in enumerate(spec["x_values"]) if float(v) == float(spec["baseline"][spec["x"]]))
    by = next(i for i, v in enumerate(spec["y_values"]) if float(v) == float(spec["baseline"][spec["y"]]))
    ax.add_patch(Rectangle((bx - .5, by - .5), 1, 1, fill=False, edgecolor="black", linewidth=2.0))
    for spine in ax.spines.values():
        spine.set_edgecolor(MAP_COLOR); spine.set_linewidth(1.3)
    return im, baseline


def plot_response(outdir, summary):
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.5), squeeze=False)
    axes = axes[0]
    im = None
    baseline_ref = None
    for ax, study in zip(axes, STUDIES):
        im, baseline = draw_heatmap(ax, study, summary)
        if baseline_ref is None:
            baseline_ref = baseline
        elif not np.isclose(baseline_ref, baseline):
            raise ValueError(
                f"Inconsistent high-load baseline across omega studies: "
                f"{baseline_ref:.6f}% vs {baseline:.6f}%"
            )

    # Match the earlier R2-03 response figure: show the Map/load/baseline
    # once at the left of the heatmap row.  The value is read from the
    # formal summary CSV rather than hard-coded.
    axes[0].text(
        -0.25, 0.50,
        f"Map A\nN=70\nBaseline={baseline_ref:.1f}%",
        transform=axes[0].transAxes,
        ha="right", va="center",
        color=MAP_COLOR, fontweight="bold", fontsize=9.5,
    )

    # Extra left margin is reserved for the baseline annotation.
    fig.subplots_adjust(left=0.12, right=0.90, bottom=0.16, top=0.88, wspace=0.38)
    cax = fig.add_axes([0.925, 0.20, 0.014, 0.62])
    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label("Success-rate change from baseline (percentage points)")
    fig.text(0.50, 0.012, "Black outline = formal baseline; high-load case shown.", ha="center", fontsize=9)
    paths=[]
    for ext, dpi in [("png", 300), ("pdf", 300)]:
        p = outdir / f"Figure_R2_03_Response_Omega_Interactions.{ext}"
        fig.savefig(p, dpi=dpi, bbox_inches="tight"); paths.append(p)
    plt.close(fig)
    return paths


def plot_supplementary_one(outdir, study, summary):
    spec = STUDIES[study]
    df = summary[summary.study == study].copy()
    coords = df["cell"].map(parse_cell)
    df["x_value"] = [p[spec["x"]] for p in coords]
    df["y_value"] = [p[spec["y"]] for p in coords]
    rows = [("success_rate", "Success rate (%)", True),
            ("planning_time", "Planning time (s)", False),
            ("average_path_length", "Average path length", False)]
    ncols = len(spec["y_values"])
    fig, axes = plt.subplots(3, ncols, figsize=(3.35*ncols, 9.0), squeeze=False)
    for r, (metric, ylabel, pct) in enumerate(rows):
        metric_df = df[df.metric == metric]
        if pct:
            allvals = metric_df["mean"].to_numpy(float)*100
            ylim = (65, 100) if allvals.min() >= 65 else (max(0, allvals.min()-3), min(100, allvals.max()+3))
        elif metric == "planning_time":
            ylim = (0, max(1, float(metric_df["ci95_high"].max())*1.10))
        else:
            lo = float(metric_df["ci95_low"].min()); hi=float(metric_df["ci95_high"].max())
            pad=max((hi-lo)*0.08, abs(hi)*0.02, 0.1); ylim=(max(0,lo-pad),hi+pad)
        for c, fixed_y in enumerate(spec["y_values"]):
            ax=axes[r,c]
            panel=metric_df[np.isclose(metric_df["y_value"].astype(float), float(fixed_y))]
            for load in (50,70):
                s=panel[panel.task_count == load].sort_values("x_value")
                x=s["x_value"].to_numpy(float)
                y=s["mean"].to_numpy(float)
                low=s["ci95_low"].to_numpy(float); high=s["ci95_high"].to_numpy(float)
                if pct: y,low,high=y*100,low*100,high*100
                ax.errorbar(x,y,yerr=[np.maximum(0,y-low),np.maximum(0,high-y)],color=MAP_COLOR,
                            marker="o",linestyle=LOW_STYLE if load==50 else HIGH_STYLE,
                            linewidth=1.5,markersize=4.5,capsize=2.3,label=LOADS[load])
            if r == 0: ax.set_title(rf"{spec['y_label']} = {fmt(fixed_y)}", pad=7)
            if c == 0: ax.set_ylabel(ylabel)
            if r == 2: ax.set_xlabel(spec["x_label"])
            ax.set_xticks(spec["x_values"], [fmt(v) for v in spec["x_values"]])
            ax.set_ylim(*ylim); ax.grid(True, alpha=.25); ax.tick_params(direction="in")
    handles=[Line2D([0],[0],color=MAP_COLOR,marker="o",linestyle=LOW_STYLE,label="Lower load (N=50)"),
             Line2D([0],[0],color=MAP_COLOR,marker="o",linestyle=HIGH_STYLE,label="Higher load (N=70)")]
    fig.legend(handles=handles,loc="upper center",ncol=2,frameon=False,bbox_to_anchor=(.5,1.005))
    fig.tight_layout(rect=[0,0,1,.965])
    stem=f"Figure_Supp_R2_03_{study}"
    paths=[]
    for ext in ("png","pdf"):
        p=outdir/f"{stem}.{ext}"; fig.savefig(p,dpi=300,bbox_inches="tight"); paths.append(p)
    plt.close(fig)
    return paths


def write_analysis(outdir, summary):
    lines=["# Omega interaction analysis (Map A only)", "",
           "All numerical values below are calculated from `omega_interactions_summary.csv`; no values are manually entered.",
           "Formal seeds: 10000--10004. Loads: N=50 and N=70. The heatmap uses N=70.", "",
           "## High-load success-rate changes relative to baseline", "",
           "| Interaction | Mean SR range across cells | Delta range vs baseline |", "|---|---:|---:|"]
    for study, spec in STUDIES.items():
        d=summary[(summary.study==study)&(summary.task_count==70)&(summary.metric=="success_rate")].copy()
        baseline=float(d[d.cell==spec["baseline_cell"]]["mean"].iloc[0])*100
        means=d["mean"].to_numpy(float)*100
        delta=means-baseline
        lines.append(f"| `{study}` | {means.min():.1f}--{means.max():.1f}% | {delta.min():+.1f} to {delta.max():+.1f} pp |")
    lines += ["", "## Interpretation guidance", "",
              "- Positive delta means the tested setting has a higher mean success rate than the formal baseline; negative delta means lower.",
              "- The black box in the heatmap marks the baseline cell (omega=50 and sigma_l=2, sigma_t=2, or K=20 as appropriate).",
              "- These are five-seed descriptive means with bootstrap 95% confidence intervals in the supplementary plots. Do not describe differences as statistically significant without a paired inferential test.",
              "- This experiment is restricted to Map A because the R1-aligned implementation enables the omega-weighted look-ahead congestion term only on Map A. Maps B and C use Manhattan distance only in h(s).",
              "- The omega candidates (10, 50, 100) are selected from the manuscript's declared omega candidate list; sigma candidates reuse the R1 Gaussian sweep; K candidates reuse the manuscript's update-interval ablation values.",
              ""]
    (outdir/"ANALYSIS_OMEGA_INTERACTIONS.md").write_text("\n".join(lines),encoding="utf-8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=Path("results_omega_interactions"))
    ap.add_argument("--output",type=Path,default=Path("omega_interaction_figures"))
    args=ap.parse_args()
    root=args.input.resolve(); out=args.output.resolve()
    raw,summary=validate_results(root)
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    (out/"01_response_letter").mkdir(); (out/"03_supplementary").mkdir()
    generated=plot_response(out/"01_response_letter",summary)
    for study in STUDIES:
        generated += plot_supplementary_one(out/"03_supplementary",study,summary)
    write_analysis(out,summary)
    print("Generated:")
    for p in generated: print(p)
    print(out/"ANALYSIS_OMEGA_INTERACTIONS.md")

if __name__ == "__main__": main()
