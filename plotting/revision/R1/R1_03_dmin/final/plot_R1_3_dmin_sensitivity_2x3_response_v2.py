from __future__ import annotations

from pathlib import Path
import shutil
import zipfile

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


# ==========================================================
# Reviewer 1 - Comment 3: d_min sensitivity
# 2 x 3 response-letter figure
#
# Layout:
#   Row 1 = lower traffic load
#   Row 2 = higher traffic load
#   Columns = Success rate / Average path length / Planning time
#
# Visual encoding:
#   Map A/B/C -> color + marker
#   Traffic load -> line style
#       lower load  = solid line
#       higher load = dashed line
#
# To avoid ambiguity, BOTH are used:
#   1) row labels explicitly state Lower/Higher traffic load;
#   2) line styles also distinguish the two load levels.
#
# Input:
#   result_R1_3_dmin_sensitivity.zip
#
# Output:
#   R1_3_dmin_figures_2x3_response_v2/
#       Figure_R1_3_dmin_sensitivity_2x3.png
#       Figure_R1_3_dmin_sensitivity_2x3.pdf
#       low_load_summary.csv
#       high_load_summary.csv
# ==========================================================

_REPO_ROOT = Path(__file__).resolve().parents[5]
ZIP_PATH = _REPO_ROOT / 'provenance/source_archives/07-result_R1_3_dmin_sensitivity.zip'
WORK_DIR = _REPO_ROOT / 'outputs/plotting_tmp/R1_03_dmin'
OUT_DIR = _REPO_ROOT / 'figures/revision/R1_03_dmin'

# Two traffic-load levels used in the R1.3 experiment.
LOW_LOAD = {"A": 30, "B": 150, "C": 100}
HIGH_LOAD = {"A": 70, "B": 280, "C": 200}
MAPS = ["A", "B", "C"]

# Same map visual identity as the previous Gaussian sensitivity figure.
COLORS = {
    "A": "#D62728",
    "B": "#4C72B0",
    "C": "#55A868",
}
MARKERS = {"A": "o", "B": "s", "C": "^"}

# Traffic load is encoded by line style.
LOAD_STYLES = {
    "low": "-",     # lower traffic load
    "high": "--",   # higher traffic load
}

plt.rcParams.update({
    "font.family": "Times New Roman",
    "mathtext.fontset": "stix",
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


METRICS = [
    {
        "mean": "success_mean",
        "ci": "success_std",
        "ylabel": "Success rate (%)",
        "title": "Success rate",
        "percent": True,
    },
    {
        "mean": "average_path_length_mean",
        "ci": "average_path_length_std",
        "ylabel": "Average path length",
        "title": "Average path length",
        "percent": False,
    },
    {
        "mean": "planning_time_mean",
        "ci": "planning_time_std",
        "ylabel": "Planning time (s)",
        "title": "Planning time",
        "percent": False,
    },
]


def prepare_directories() -> None:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    WORK_DIR.mkdir(parents=True)
    OUT_DIR.mkdir(parents=True)


def load_summary() -> pd.DataFrame:
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            f"{ZIP_PATH} was not found. Put this plotting script in the same "
            "directory as result_R1_3_dmin_sensitivity.zip."
        )

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        zf.extractall(WORK_DIR)

    summary_files = sorted(WORK_DIR.rglob("summary_results.csv"))
    if not summary_files:
        raise FileNotFoundError(
            "summary_results.csv was not found in result_R1_3_dmin_sensitivity.zip."
        )

    summary_path = summary_files[-1]
    print("Using summary:", summary_path)
    df = pd.read_csv(summary_path)

    required = {
        "map",
        "task_count",
        "d_min",
        "success_mean",
        "success_ci95",
        "average_path_length_mean",
        "average_path_length_ci95",
        "planning_time_mean",
        "planning_time_ci95",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            "summary_results.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )

    return df


def render_panel(
    ax,
    df: pd.DataFrame,
    metric_info: dict,
    load_name: str,
    load_config: dict,
    row_idx:int
) -> None:
    mean_col = metric_info["mean"]
    ci_col = metric_info["ci"]

    for m in MAPS:
        sub = df[
            (df["map"] == m)
            & (df["task_count"] == load_config[m])
        ].sort_values("d_min")

        if sub.empty:
            raise ValueError(
                f"No data found for Map {m} at {load_name} load "
                f"(task_count={load_config[m]})."
            )

        x = sub["d_min"].to_numpy(dtype=float)
        y = sub[mean_col].to_numpy(dtype=float)
        err = sub[ci_col].to_numpy(dtype=float)

        if metric_info["percent"]:
            y = y * 100.0
            err = err * 100.0

        ax.errorbar(
            x,
            y,
            yerr=err,
            marker=MARKERS[m],
            linestyle=LOAD_STYLES[load_name],
            color=COLORS[m],
            linewidth=1.5,
            markersize=5,
            capsize=2.5,
            elinewidth=1.0,
            label=f"Map {m}",
        )
    if row_idx==0:
        ax.set_title(metric_info["title"], pad=7)
    if row_idx==1:
        ax.set_xlabel(r"$d_{\min}$")
    ax.set_ylabel(metric_info["ylabel"])
    ax.set_xticks([1, 2, 3])
    ax.grid(True, alpha=0.25)
    ax.tick_params(direction="in")

    # Use a fixed 0--100% range for both success-rate panels.
    if metric_info["percent"]:
        ax.set_ylim(0, 100)


def build_figure(df: pd.DataFrame) -> tuple[Path, Path]:
    fig, axes = plt.subplots(
        nrows=2,
        ncols=3,
        figsize=(12.0, 7.0),
        sharex=True,
    )

    load_rows = [
        ("low", LOW_LOAD),
        ("high", HIGH_LOAD),
    ]

    for row_idx, (load_name, load_config) in enumerate(load_rows):
        for col_idx, metric_info in enumerate(METRICS):
            render_panel(
                ax=axes[row_idx, col_idx],
                df=df,
                metric_info=metric_info,
                load_name=load_name,
                load_config=load_config,
                row_idx=row_idx,
            )

    # ------------------------------------------------------
    # Legend 1: Map identity = color + marker
    # Use a neutral solid line here; line style itself is explained
    # separately by the traffic-load legend below.
    # ------------------------------------------------------
    map_handles = [
        Line2D(
            [0], [0],
            color=COLORS[m],
            marker=MARKERS[m],
            linestyle="-",
            linewidth=1.5,
            markersize=5,
            label=f"Map {m}",
        )
        for m in MAPS
    ]

    # ------------------------------------------------------
    # Legend 2: Traffic load = line style
    # ------------------------------------------------------
    load_handles = [
        Line2D(
            [0], [0],
            color="black",
            linestyle=LOAD_STYLES["low"],
            linewidth=1.5,
            label="Lower traffic load",
        ),
        Line2D(
            [0], [0],
            color="black",
            linestyle=LOAD_STYLES["high"],
            linewidth=1.5,
            label="Higher traffic load",
        ),
    ]

    # Two compact legends at the top.
    legend_maps = fig.legend(
        handles=map_handles,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.39, 0.995),
    )
    fig.add_artist(legend_maps)

    fig.legend(
        handles=load_handles,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.73, 0.995),
    )

    # Explicit row labels make the 2 x 3 layout self-explanatory.
    fig.text(
        0.018,
        0.69,
        "Lower traffic load",
        rotation=90,
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
    )
    fig.text(
        0.018,
        0.29,
        "Higher traffic load",
        rotation=90,
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
    )

    # Also show the actual task counts for each row.
    fig.text(
        0.038,
        0.69,
         f"A: {LOW_LOAD['A']}, B: {LOW_LOAD['B']}, C: {LOW_LOAD['C']} tasks",
        rotation=90,
        ha="center",
        va="center",
        fontsize=8.5,
    )
    fig.text(
        0.038,
        0.29,
         f"A: {HIGH_LOAD['A']}, B: {HIGH_LOAD['B']}, C: {HIGH_LOAD['C']} tasks",
        rotation=90,
        ha="center",
        va="center",
        fontsize=8.5,
    )

    fig.subplots_adjust(
        left=0.095,
        right=0.995,
        bottom=0.09,
        top=0.91,
        wspace=0.28,
        hspace=0.10,
    )

    png_path = OUT_DIR / "Figure_R1_3_dmin_sensitivity_2x3.png"
    pdf_path = OUT_DIR / "Figure_R1_3_dmin_sensitivity_2x3.pdf"

    fig.savefig(
        png_path,
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    fig.savefig(
        pdf_path,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)

    return png_path, pdf_path


def export_load_summaries(df: pd.DataFrame) -> None:
    rows = {
        "low": [],
        "high": [],
    }

    for m in MAPS:
        for load_name, load_config in [
            ("low", LOW_LOAD),
            ("high", HIGH_LOAD),
        ]:
            sub = df[
                (df["map"] == m)
                & (df["task_count"] == load_config[m])
            ].sort_values("d_min").copy()

            if sub.empty:
                continue

            sub.insert(0, "load", load_name)
            rows[load_name].append(sub)

    for load_name in ["low", "high"]:
        if rows[load_name]:
            pd.concat(rows[load_name], ignore_index=True).to_csv(
                OUT_DIR / f"{load_name}_load_summary.csv",
                index=False,
            )


def main() -> None:
    prepare_directories()
    df = load_summary()
    export_load_summaries(df)
    png_path, pdf_path = build_figure(df)

    print("Done.")
    print("Figure PNG:", png_path)
    print("Figure PDF:", pdf_path)
    print("Output directory:", OUT_DIR)


if __name__ == "__main__":
    main()
