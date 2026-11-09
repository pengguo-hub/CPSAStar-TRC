#!/usr/bin/env python3
"""R2-04 compact plots for the selected high-fleet conditions.

The figure keeps one fleet size per map:
  STANDARD: 50 AGVs; FRANSEN: 200 AGVs; RING: 160 AGVs.
It reads the existing trial CSV and map/OD metadata only; it does not run experiments.
Each map panel has its own y-axis range for each metric. Every panel shows its
own tick labels so Full/Control differences remain visible within each map.

Run:
    python plot_r2_04_compact.py --out .

Required files in the same directory:
    R2_04_trial_metrics.csv
    R2_04_plot_inputs.json
"""
from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd
from scipy.stats import t

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator, FuncFormatter

MAPS = ["STANDARD", "FRANSEN", "RING"]
MODES = ["dispersed", "intermediate", "shared"]
MODE_LABELS = ["Low", "Medium", "High"]
METRICS = ["throughput", "waiting_time", "flow_time", "queue_length"]
LABELS = [
    "Throughput\n(tasks / step)",
    "Restricted waiting time\n(steps / request)",
    "Restricted flow time\n(steps / request)",
    "Mean task queue\n(unassigned requests)",
]
TITLES = ["Throughput", "Waiting time", "Flow time", "Mean task queue"]
COLORS = {"full": "#267BA5", "control": "#CD713E"}
EXPECTED_FLEETS = {"STANDARD": 50, "FRANSEN": 200, "RING": 160}


def style():
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    family = next(
        (name for name in ["Times New Roman", "Liberation Serif", "DejaVu Serif"] if name in fonts),
        "DejaVu Serif",
    )
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.65,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
        }
    )
    return family


def mean_ci(values):
    values = np.asarray(values, dtype=float)
    mean = float(values.mean())
    half_width = float(t.ppf(0.975, len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values)))
    return mean, half_width


def label_offset(mp, kind, i, x, y, w, h):
    if mp == "STANDARD":
        if kind == "O":
            return (0, 0.82 if y < 5 else -0.80)
        return (0.45, 0.80) if y == 0 else (0.35, -0.80)
    if mp == "FRANSEN":
        if kind == "O":
            return [(-0.65, 0.72), (0.85, 0.1), (0.85, 0.16), (0.85, 0.16), (0.2, 0.86), (0.2, 0.86), (0.2, 0.86), (0.2, 0.86)][i]
        return [(1.02, 0.12), (1.02, 0.12), (0.12, 0.94), (0.12, -0.72), (0.12, 0.94), (0.12, -0.72), (-1.1, 0.12), (-1.1, 0.12)][i]
    if kind == "D":
        return [(1.2, -0.35), (1.2, 0.35), (-1.2, -0.35), (-1.2, 0.35), (-0.45, 1.25), (0.45, 1.25), (-0.45, -1.25), (0.45, -1.25)][i]
    return [(0.9, 0), (0.9, 0), (-0.9, 0), (-0.9, 0), (0, 0.85), (0, 0.85), (0, -0.85), (0, -0.85)][i]


def draw_map(ax, mp, info, letter, fleet):
    grid = np.asarray(info["grid"])
    height, width = grid.shape
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_aspect("equal")
    ax.set_anchor("N")

    for x in range(width + 1):
        ax.axvline(x, color="#BCC3C9" if x % 5 == 0 else "#E5E8EB", lw=0.42 if x % 5 == 0 else 0.23, zorder=0)
    for y in range(height + 1):
        ax.axhline(y, color="#BCC3C9" if y % 5 == 0 else "#E5E8EB", lw=0.42 if y % 5 == 0 else 0.23, zorder=0)
    for y, x in zip(*np.where(grid != 0)):
        ax.add_patch(
            Rectangle(
                (x, y), 1, 1,
                facecolor="#ADB4BA", edgecolor="#6E777F", lw=0.35, zorder=1,
            )
        )

    for kind, key, color, marker in [
        ("O", "origins", "#176B9B", "o"),
        ("D", "destinations", "#9345BA", "s"),
    ]:
        for i, (x, y) in enumerate(info[key]):
            cx, cy = x + 0.5, y + 0.5
            ax.scatter(cx, cy, s=23, marker=marker, color=color, edgecolors="white", linewidths=0.65, zorder=4)
            dx, dy = label_offset(mp, kind, i, x, y, width, height)
            ax.annotate(
                f"{kind}{i + 1}", (cx, cy), xytext=(cx + dx, cy + dy), textcoords="data",
                fontsize=6.7, fontweight="bold", ha="center", va="center", color=color,
                bbox=dict(boxstyle="round,pad=.09", fc="white", ec="none", alpha=0.94), zorder=5,
            )

    ax.set_xticks(sorted(set(list(range(0, width + 1, 5)) + [width])))
    ax.set_yticks(sorted(set(list(range(0, height + 1, 5)) + [height])))
    ax.tick_params(length=0, pad=2, labelsize=7)
    ax.spines[["top", "right"]].set_visible(True)
    ax.set_title(f"({letter}) {width} × {height}   |   {fleet} AGVs", fontweight="bold", pad=8)


def metric_tick_formatter(metric):
    if metric == "throughput":
        return FuncFormatter(lambda value, pos: f"{value:.2f}")
    if metric == "queue_length":
        return FuncFormatter(lambda value, pos: f"{value:.0f}")
    return FuncFormatter(lambda value, pos: f"{value:.1f}")


def panel_metric_limits(data, metric, map_name):
    """Return a map-specific y-range for one metric panel.

    Each STANDARD/FRANSEN/RING panel is scaled independently. Limits include
    every plotted arm mean and its 95% t interval for the selected fleet and
    all three OD modes, with a modest margin. This makes within-map differences
    legible without clipping confidence intervals.
    """
    fleet = EXPECTED_FLEETS[map_name]
    bounds = []
    for mode in MODES:
        for arm in ("full", "control"):
            q = data[
                (data["map"] == map_name)
                & (data["fleet"].astype(int) == fleet)
                & (data["od_mode"] == mode)
                & (data["variant"] == arm)
            ]
            if len(q) != 5:
                raise ValueError(
                    f"Expected 5 seeds for {map_name}, {metric}, {mode}, {arm}; found {len(q)}."
                )
            mean, ci = mean_ci(q[metric].to_numpy())
            bounds.extend([mean - ci, mean + ci])

    lower, upper = float(min(bounds)), float(max(bounds))
    span = max(upper - lower, 1e-9)
    magnitude = max(abs(lower), abs(upper), 1.0)
    # Use proportional padding around each panel's own data range. The small
    # magnitude-based floor avoids degenerate limits when a panel is very stable.
    pad = max(0.12 * span, 0.008 * magnitude)
    return max(0.0, lower - pad), upper + pad


def apply_panel_y_axis(ax, limits, metric):
    """Apply this panel's independent scale and show its own tick labels."""
    ax.set_ylim(*limits)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=4))
    ax.yaxis.set_major_formatter(metric_tick_formatter(metric))
    ax.tick_params(axis="y", labelleft=True, labelsize=7.2, pad=2)


def validate_and_filter(data):
    required = {
        "case", "seed", "status", "fleet", "map", "od_mode", "variant", "workload_hash",
        *METRICS,
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Trial CSV is missing required columns: {sorted(missing)}")
    if len(data) != 180:
        raise ValueError(f"Expected the complete 180-trial table; found {len(data)} rows.")
    if not data["status"].eq("completed").all():
        raise ValueError("The trial table contains non-completed records; do not silently plot partial data.")
    if set(data["seed"].astype(int)) != {39, 40, 41, 42, 43}:
        raise ValueError("Unexpected formal seed set; expected seeds 39–43.")
    if data.duplicated(["case", "seed", "variant"]).any():
        raise ValueError("Duplicate trial keys detected.")
    for _, group in data.groupby(["case", "seed"]):
        if len(group) != 2 or set(group["variant"]) != {"full", "control"}:
            raise ValueError("A case/seed does not contain exactly one Full and one Control trial.")
        if group["workload_hash"].nunique() != 1:
            raise ValueError("Full and Control do not share the same workload hash for a case/seed.")

    selected = data[
        data.apply(lambda row: int(row["fleet"]) == EXPECTED_FLEETS.get(row["map"], -1), axis=1)
    ].copy()
    if len(selected) != 90:
        raise ValueError(f"Expected 90 selected high-fleet records; found {len(selected)}.")
    for mp in MAPS:
        q = selected[selected["map"] == mp]
        if set(q["fleet"].astype(int)) != {EXPECTED_FLEETS[mp]} or len(q) != 30:
            raise ValueError(f"Unexpected selected fleet/trial count for {mp}.")
        if set(q["od_mode"]) != set(MODES):
            raise ValueError(f"Missing OD modes for {mp}.")
    return selected


def paired_effect_summary(data, metric, scope, map_name=None):
    selected = data if scope == "global" else data[data["map"] == map_name]
    wide = selected.pivot_table(
        index=["map", "fleet", "od_mode", "seed"],
        columns="variant", values=metric, aggfunc="first",
    ).reset_index()
    if not {"full", "control"}.issubset(wide.columns):
        raise ValueError(f"Cannot form paired Full/Control values for {metric}.")
    wide["delta"] = wide["full"] - wide["control"]
    # The independent unit is the seed: average the three OD modes within each seed.
    by_seed = wide.groupby("seed")[["delta", "control"]].mean().sort_index()
    mean_delta, ci_delta = mean_ci(by_seed["delta"].to_numpy())
    control_mean = float(by_seed["control"].mean())
    relative = 100.0 * mean_delta / control_mean if control_mean else np.nan
    return {
        "mean": mean_delta,
        "low": mean_delta - ci_delta,
        "high": mean_delta + ci_delta,
        "relative_percent": relative,
        "n": len(by_seed),
    }


def plot_main(data, cfg, out, dpi):
    fig = plt.figure(figsize=(13.0, 10.0))
    gs = fig.add_gridspec(
        5, 3,
        left=0.082, right=0.992, bottom=0.055, top=0.94,
        height_ratios=[2.05, 1, 1, 1, 1],
        hspace=0.25, wspace=0.20,
    )
    legend = [
        Line2D([], [], color=COLORS["full"], marker="o", ms=4, lw=1.2, label="Full"),
        Line2D([], [], color=COLORS["control"], marker="s", mfc="white", ms=4, lw=1.2, ls="--", label="Control"),
        Line2D([], [], color="#176B9B", marker="o", ms=4, ls="", label="Pickup O"),
        Line2D([], [], color="#9345BA", marker="s", ms=4, ls="", label="Drop-off D"),
    ]
    fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.55, 0.998), ncol=4, frameon=False, columnspacing=2)

    for col, mp in enumerate(MAPS):
        fleet = EXPECTED_FLEETS[mp]
        draw_map(fig.add_subplot(gs[0, col]), mp, cfg["maps"][mp], chr(97 + col), fleet)

    for row, metric in enumerate(METRICS):
        for col, mp in enumerate(MAPS):
            ax = fig.add_subplot(gs[row + 1, col])
            ax.set_axisbelow(True)
            ax.grid(axis="y", color="#DEE3E7", lw=0.5)
            fleet = EXPECTED_FLEETS[mp]
            for arm, offset in [("full", -0.055), ("control", 0.055)]:
                means, errors = [], []
                for mode, x in zip(MODES, range(3)):
                    q = data[
                        (data["map"] == mp)
                        & (data["fleet"].astype(int) == fleet)
                        & (data["od_mode"] == mode)
                        & (data["variant"] == arm)
                    ]
                    if len(q) != 5:
                        raise ValueError(f"Expected 5 seeds for {mp}, N={fleet}, {mode}, {arm}; found {len(q)}.")
                    mean, ci = mean_ci(q[metric].to_numpy())
                    means.append(mean)
                    errors.append(ci)
                ax.errorbar(
                    np.arange(3) + offset, means, yerr=errors,
                    color=COLORS[arm], fmt="o-" if arm == "full" else "s--",
                    mfc=COLORS[arm] if arm == "full" else "white",
                    ms=3.8, lw=1.1, elinewidth=0.75, capsize=2.2, capthick=0.75, zorder=4,
                )

            ax.set_xlim(-0.45, 2.45)
            ax.set_xticks([0, 1, 2], MODE_LABELS)
            ax.tick_params(length=2.4, width=0.6, pad=2)
            panel_limits = panel_metric_limits(data, metric, mp)
            apply_panel_y_axis(ax, panel_limits, metric)
            ax.text(0.025, 0.94, f"({chr(100 + row * 3 + col)})", transform=ax.transAxes,
                    va="top", color="#505A62", fontsize=8)
            if col == 0:
                ax.set_ylabel(LABELS[row], labelpad=9)
            if row < 3:
                ax.tick_params(labelbottom=False)
            else:
                ax.set_xlabel("Congestion exposure level", labelpad=4)

    for ext in ["png", "pdf"]:
        fig.savefig(out / f"R2_04_compact_results.{ext}", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_paired_effects(data, out, dpi):
    groups = [
        ("map", mp, f"{EXPECTED_FLEETS[mp]} AGVs")
        for mp in MAPS
    ]
    fig, axes = plt.subplots(1, 4, figsize=(11.4, 3.2), sharey=True)
    fig.subplots_adjust(left=0.13, right=0.985, bottom=0.19, top=0.93, wspace=0.22)

    for col, metric in enumerate(METRICS):
        ax = axes[col]
        records = [paired_effect_summary(data, metric, scope, mp) for scope, mp, _ in groups]
        low = min([0.0] + [r["low"] for r in records])
        high = max([0.0] + [r["high"] for r in records])
        span = max(high - low, 1e-9)
        ax.set_xlim(low - 0.12 * span, high + 0.45 * span)
        ax.axvline(0, color="#8D969E", lw=0.7, ls="--")
        for yy, record in enumerate(records):
            mean = record["mean"]
            ax.errorbar(
                mean, yy,
                xerr=[[mean - record["low"]], [record["high"] - mean]],
                fmt="o", ms=4, color=COLORS["full"], capsize=2.4, lw=0.85,
            )
            ax.text(0.98, yy, f"{record['relative_percent']:+.2f}%", transform=ax.get_yaxis_transform(),
                    ha="right", va="center", fontsize=8, color="#234D66")
        ax.set_yticks(range(len(groups)), [label for _, _, label in groups])
        ax.set_ylim(len(groups) - 0.45, -0.65)
        ax.grid(axis="y", color="#E7EBEE", lw=0.4)
        ax.tick_params(length=2.4)
        ax.set_title(TITLES[col], fontsize=10, pad=10)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, pos: f"{value:g}"))
        units = ["tasks / step", "steps / request", "steps / request", "requests"][col]
        ax.set_xlabel(f"Full − Control ({units})", fontsize=8.1)

    for ext in ["png", "pdf"]:
        fig.savefig(out / f"R2_04_paired_effects.{ext}", dpi=dpi, bbox_inches="tight")
    plt.close(fig)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path(__file__).resolve().parent
    parser.add_argument("--data", type=Path, default=home / "R2_04_trial_metrics.csv")
    parser.add_argument("--inputs", type=Path, default=home / "R2_04_plot_inputs.json")
    parser.add_argument("--out", type=Path, default=home)
    parser.add_argument("--dpi", type=int, default=600)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    family = style()
    raw = pd.read_csv(args.data)
    selected = validate_and_filter(raw)
    cfg = json.loads(args.inputs.read_text(encoding="utf-8"))
    if cfg.get("fleets") != EXPECTED_FLEETS:
        raise ValueError(f"Map/fleet configuration must be exactly {EXPECTED_FLEETS}.")
    plot_main(selected, cfg, args.out, args.dpi)
    plot_paired_effects(selected, args.out, args.dpi)
    print(f"Saved high-fleet R2-04 figures to {args.out}; font: {family}; plotted trials: {len(selected)}")


if __name__ == "__main__":
    main()
