from __future__ import annotations

import argparse
import math
import shutil
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

# -------------------------
# Visual style (aligned with R1)
# -------------------------
MAPS = ["A", "B", "C"]
COLORS = {
    "A": "#D62728",
    "B": "#4C72B0",
    "C": "#55A868",
}
MARKERS = {"A": "o", "B": "s", "C": "^"}
LOAD_STYLES = {
    "low": "-",
    "high": "--",
}
LOAD_LEVEL = {
    ("A", 50): "low",
    ("A", 70): "high",
    ("B", 250): "low",
    ("B", 280): "high",
    ("C", 150): "low",
    ("C", 200): "high",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})

# Default third metric = waits because R2 average_congestion_fixed is identically zero.
METRIC_PRESETS = {
    "waits": [
        ("success_rate", "Success rate (%)", True),
        ("planning_time", "Planning time (s)", False),
        ("average_waits", "Average waits", False),
    ],
    "pathlength": [
        ("success_rate", "Success rate (%)", True),
        ("planning_time", "Planning time (s)", False),
        ("average_path_length", "Average path length", False),
    ],
    "turns": [
        ("success_rate", "Success rate (%)", True),
        ("planning_time", "Planning time (s)", False),
        ("average_turns", "Average turns", False),
    ],
}

STUDIES = [
    {
        "name": "sigma_l_sigma_t",
        "summary_csv": "joint_spatiotemporal_sensitivity/joint_summary.csv",
        "x_var": "sigma_l",
        "x_label": r"$\sigma_l$",
        "fixed_var": "sigma_t",
        "fixed_values": [0.5, 1.0, 2.0, 4.0],
        "col_title": lambda v: rf"Temporal width $\sigma_t={fmt(v)}$",
        "output_stem": "Fig_R2_03_sigma_l_sigma_t",
    },
    {
        "name": "L_T",
        "summary_csv": "joint_spatiotemporal_sensitivity/joint_summary.csv",
        "x_var": "L",
        "x_label": r"$L$",
        "fixed_var": "T",
        "fixed_values": [0, 1, 2, 3],
        "col_title": lambda v: rf"Temporal support $T={fmt(v)}$",
        "output_stem": "Fig_R2_03_L_T",
    },
    {
        "name": "gamma_sigma_l",
        "summary_csv": "cross_parameter_interactions/cross_summary.csv",
        "x_var": "gamma",
        "x_label": r"$\gamma$",
        "fixed_var": "sigma_l",
        "fixed_values": [0.5, 1.0, 2.0, 4.0],
        "col_title": lambda v: rf"Spatial width $\sigma_l={fmt(v)}$",
        "output_stem": "Fig_R2_03_gamma_sigma_l",
    },
    {
        "name": "gamma_sigma_t",
        "summary_csv": "cross_parameter_interactions/cross_summary.csv",
        "x_var": "gamma",
        "x_label": r"$\gamma$",
        "fixed_var": "sigma_t",
        "fixed_values": [0.5, 1.0, 2.0, 4.0],
        "col_title": lambda v: rf"Temporal width $\sigma_t={fmt(v)}$",
        "output_stem": "Fig_R2_03_gamma_sigma_t",
    },
    {
        "name": "gamma_K",
        "summary_csv": "cross_parameter_interactions/cross_summary.csv",
        "x_var": "K",
        "x_label": r"$K$",
        "fixed_var": "gamma",
        "fixed_values": [2.5, 5.0, 7.5],
        "col_title": lambda v: rf"Congestion weight $\gamma={fmt(v)}$",
        "output_stem": "Fig_R2_03_gamma_K",
    },
]


def fmt(v):
    if isinstance(v, str):
        return v
    if float(v).is_integer():
        return str(int(v))
    return str(v)


def materialize_input(input_path: Path, work_dir: Path) -> Path:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_dir():
        return input_path

    if input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(work_dir)
        # Expect top-level results_R2_03/
        extracted = work_dir / "results_R2_03"
        if extracted.exists():
            return extracted
        # fallback: first directory containing csvs
        for p in work_dir.rglob("joint_summary.csv"):
            return p.parents[1]
        raise FileNotFoundError("Could not find extracted results_R2_03 directory.")

    raise ValueError(f"Unsupported input: {input_path}")


def nice_limits(values, metric_name, percent=False):
    vals = [float(v) for v in values if pd.notna(v)]
    if not vals:
        return None
    vmin, vmax = min(vals), max(vals)
    if percent:
        return (65, 100)
    if metric_name == "planning_time":
        upper = math.ceil((vmax * 1.08) / 5.0) * 5.0
        return (0, upper)
    span = vmax - vmin
    pad = max(0.05 * max(abs(vmax), 1.0), 0.12 * span, 0.1)
    lower = max(0, vmin - pad)
    upper = vmax + pad
    return (lower, upper)


def parse_cell_value(cell: str, key: str):
    parts = dict(piece.split("=") for piece in cell.split("__"))
    return parts[key]


def build_panel_frame(summary_df: pd.DataFrame, study_name: str, metric: str, x_var: str, fixed_var: str):
    sub = summary_df[(summary_df["study"] == study_name) & (summary_df["metric"] == metric)].copy()
    sub["x_value"] = sub["cell"].apply(lambda c: float(parse_cell_value(c, x_var)))
    sub["fixed_value"] = sub["cell"].apply(lambda c: float(parse_cell_value(c, fixed_var)))
    sub["load_level"] = sub.apply(lambda r: LOAD_LEVEL[(r["map"], int(r["task_count"]))], axis=1)
    return sub


def draw_figure(result_root: Path, out_dir: Path, study_spec: dict, rows: list[tuple[str, str, bool]]):
    summary = pd.read_csv(result_root / study_spec["summary_csv"])
    nrows = len(rows)
    ncols = len(study_spec["fixed_values"])
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(4.0 * ncols, 3.0 * nrows + 0.65), squeeze=False)

    # row-wise y limits, shared within each row/figure
    row_limits = {}
    for metric_name, _, percent in rows:
        sub = build_panel_frame(summary, study_spec["name"], metric_name, study_spec["x_var"], study_spec["fixed_var"])
        yvals = sub["mean"].to_numpy(dtype=float)
        if percent:
            yvals = yvals * 100.0
        row_limits[metric_name] = nice_limits(yvals, metric_name, percent=percent)

    for r, (metric_name, y_label, percent) in enumerate(rows):
        sub = build_panel_frame(summary, study_spec["name"], metric_name, study_spec["x_var"], study_spec["fixed_var"])
        for c, fixed_value in enumerate(study_spec["fixed_values"]):
            ax = axes[r][c]
            panel = sub[sub["fixed_value"] == float(fixed_value)].copy()

            for map_name in MAPS:
                for load_level in ["low", "high"]:
                    ss = panel[(panel["map"] == map_name) & (panel["load_level"] == load_level)].sort_values("x_value")
                    if ss.empty:
                        continue
                    x = ss["x_value"].to_numpy(dtype=float)
                    y = ss["mean"].to_numpy(dtype=float)
                    lower = ss["ci95_low"].to_numpy(dtype=float)
                    upper = ss["ci95_high"].to_numpy(dtype=float)
                    if percent:
                        y = y * 100.0
                        lower = lower * 100.0
                        upper = upper * 100.0
                    yerr = [y - lower, upper - y]
                    ax.errorbar(
                        x,
                        y,
                        yerr=yerr,
                        marker=MARKERS[map_name],
                        linestyle=LOAD_STYLES[load_level],
                        color=COLORS[map_name],
                        linewidth=1.5,
                        markersize=5,
                        capsize=2.5,
                    )

            if r == 0:
                ax.set_title(study_spec["col_title"](fixed_value), pad=7)
            if c == 0:
                ax.set_ylabel(y_label)
            if r == nrows - 1:
                ax.set_xlabel(study_spec["x_label"])

            ax.set_xticks(sorted(panel["x_value"].unique()))
            ax.set_xticklabels([fmt(v) for v in sorted(panel["x_value"].unique())])
            lims = row_limits[metric_name]
            if lims is not None:
                ax.set_ylim(*lims)
            ax.grid(True, alpha=0.25)
            ax.tick_params(direction="in")

    # common legend
    map_handles = [
        Line2D([0], [0], color=COLORS[m], marker=MARKERS[m], linestyle='-', linewidth=1.5, markersize=5, label=f"Map {m}")
        for m in MAPS
    ]
    load_handles = [
        Line2D([0], [0], color='black', linestyle=LOAD_STYLES[level], linewidth=1.5, label=("Lower traffic load" if level == 'low' else "Higher traffic load"))
        for level in ["low", "high"]
    ]
    fig.legend(
        handles=map_handles + load_handles,
        loc="upper center",
        ncol=5,
        frameon=False,
        bbox_to_anchor=(0.5, 1.01),
    )
    fig.tight_layout(rect=[0, 0, 1, 0.965])

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = study_spec["output_stem"] + ("_pathlength" if rows[-1][0] == "average_path_length" else "")
    png_path = out_dir / f"{stem}.png"
    pdf_path = out_dir / f"{stem}.pdf"
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return png_path, pdf_path


def main():
    ap = argparse.ArgumentParser(description="Plot R2-03 response-style figures from results_R2_03.zip or extracted directory.")
    ap.add_argument("--input", required=True, help="Path to results_R2_03.zip or extracted results_R2_03 directory")
    ap.add_argument("--output", required=True, help="Output directory for figure files")
    ap.add_argument("--third-metric", choices=["waits", "pathlength", "turns"], default="waits",
                    help="Third row metric. Default: waits. Use pathlength if you prefer a more geometric metric.")
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    work_dir = out_dir / "_tmp_extract"

    result_root = materialize_input(input_path, work_dir)
    rows = METRIC_PRESETS[args.third_metric]

    generated = []
    for spec in STUDIES:
        generated.extend(draw_figure(result_root, out_dir, spec, rows))

    # cleanup temp extract if we extracted from zip
    if input_path.is_file() and work_dir.exists():
        shutil.rmtree(work_dir)

    print("Generated files:")
    for p in generated:
        print(p)


if __name__ == "__main__":
    main()
