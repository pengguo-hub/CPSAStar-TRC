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


def congestion_effect_summary_full(data, metric, map_name, contrast):
    """Seed-paired signed relative changes for Full only.

    H_vs_M compares High with Medium; H_vs_L compares High with Low.
    Positive and negative values retain the natural direction of each metric.
    """
    fleet = EXPECTED_FLEETS[map_name]
    q = data[
        (data["map"] == map_name)
        & (data["fleet"].astype(int) == fleet)
        & (data["variant"] == "full")
    ]
    wide = (
        q.pivot(index="seed", columns="od_mode", values=metric)
        .reindex(columns=MODES)
        .sort_index()
    )
    if wide.shape != (5, 3) or wide.isna().any().any():
        raise ValueError(
            f"Expected 5 complete Full seeds for {map_name}, {metric}; "
            f"got shape {wide.shape}."
        )

    low = wide["dispersed"].to_numpy(dtype=float)
    medium = wide["intermediate"].to_numpy(dtype=float)
    high = wide["shared"].to_numpy(dtype=float)

    if contrast == "H_vs_M":
        baseline = medium
    elif contrast == "H_vs_L":
        baseline = low
    else:
        raise ValueError(f"Unknown contrast: {contrast}")

    if np.any(baseline == 0):
        raise ValueError(f"Zero baseline encountered for {map_name}, {metric}, {contrast}.")

    # Use the same signed relative-change formula for all four metrics.
    # Negative throughput changes indicate fewer tasks completed;
    # positive time/queue changes indicate larger costs.
    changes = 100.0 * (high - baseline) / baseline

    mean, ci = mean_ci(changes)
    return {
        "mean": mean,
        "low": mean - ci,
        "high": mean + ci,
        "n": len(changes),
    }


def plot_congestion_exposure_effects_full(data, out, dpi):
    """Forest plot of H-vs-M and H-vs-L relative changes for Full only."""
    groups = [(mp, f"{EXPECTED_FLEETS[mp]} AGVs") for mp in MAPS]
    contrasts = [
        ("H_vs_M", "High vs Medium", "o", "#267BA5", -0.12),
        ("H_vs_L", "High vs Low", "D", "#0B4F6C", 0.12),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(11.4, 3.35), sharey=True)
    fig.subplots_adjust(
        left=0.14, right=0.99, bottom=0.22, top=0.79, wspace=0.24
    )

    for col, metric in enumerate(METRICS):
        ax = axes[col]
        records = []
        for map_name, _ in groups:
            for contrast, _, _, _, _ in contrasts:
                records.append(
                    congestion_effect_summary_full(data, metric, map_name, contrast)
                )

        x_low = min([0.0] + [record["low"] for record in records])
        x_high = max([0.0] + [record["high"] for record in records])
        span = max(x_high - x_low, 0.5)
        ax.set_xlim(x_low - 0.12 * span, x_high + 0.55 * span)
        ax.axvline(0, color="#8D969E", lw=0.7, ls="--", zorder=1)

        for y, (map_name, _) in enumerate(groups):
            for contrast, _, marker, color, offset in contrasts:
                record = congestion_effect_summary_full(
                    data, metric, map_name, contrast
                )
                mean = record["mean"]
                ax.errorbar(
                    mean,
                    y + offset,
                    xerr=[[mean - record["low"]], [record["high"] - mean]],
                    fmt=marker,
                    ms=4.2,
                    color=color,
                    mfc=color,
                    capsize=2.4,
                    lw=0.9,
                    zorder=3,
                )
                ax.text(
                    0.98,
                    y + offset,
                    f"{mean:+.2f}%",
                    transform=ax.get_yaxis_transform(),
                    ha="right",
                    va="center",
                    fontsize=7.7,
                    color=color,
                )

        ax.set_yticks(range(len(groups)), [label for _, label in groups])
        ax.set_ylim(len(groups) - 0.45, -0.65)
        ax.grid(axis="y", color="#E7EBEE", lw=0.4, zorder=0)
        ax.tick_params(length=2.4)
        ax.set_title(TITLES[col], fontsize=10, pad=10)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, pos: f"{value:g}"))
        ax.set_xlabel("Relative change (%)", fontsize=8.1)

    legend = [
        Line2D(
            [], [], color="#267BA5", marker="o", ls="",
            label="High vs Medium (Full)",
        ),
        Line2D(
            [], [], color="#0B4F6C", marker="D", ls="",
            label="High vs Low (Full)",
        ),
    ]
    fig.legend(
        handles=legend,
        loc="upper center",
        bbox_to_anchor=(0.52, 0.995),
        ncol=2,
        frameon=False,
        columnspacing=2.0,
    )

    for ext in ["png", "pdf"]:
        fig.savefig(
            out / f"R2_04_congestion_exposure_effects_full.{ext}",
            dpi=dpi,
            bbox_inches="tight",
        )
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
    plot_congestion_exposure_effects_full(selected, args.out, args.dpi)
    print(f"Saved high-fleet R2-04 figures to {args.out}; font: {family}; plotted trials: {len(selected)}")


if __name__ == "__main__":
    main()
