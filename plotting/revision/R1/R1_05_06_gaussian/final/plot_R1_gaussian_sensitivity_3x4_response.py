from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image
import zipfile
import shutil

# ==========================================================
# Reviewer 1 Gaussian-parameter sensitivity
# 3x4 response-letter figure
#
# This version keeps the ORIGINAL wide visual style:
#   - each panel = 4.0 x 3.0 in
#   - 3 rows x 4 columns
#   - common legend at top
#   - panels combined with PIL exactly like the earlier version
#
# The ONLY main change is file-size reduction:
#   - panel PNG: 300 dpi instead of 600 dpi
#   - final PDF: compressed RGB raster PDF at 300 dpi
#
# It also keeps:
#   - baseline-unified CSV
#   - shared y-axis limits by metric row
#   - Map A/B/C = red / soft blue / soft green
# ==========================================================

_REPO_ROOT = Path(__file__).resolve().parents[5]
ZIP_PATH = _REPO_ROOT / 'provenance/source_archives/04-result_R1_gaussian_sensitivity.zip'
WORK_DIR = _REPO_ROOT / 'outputs/plotting_tmp/R1_05_06_gaussian'
OUT_DIR = _REPO_ROOT / 'figures/revision/R1_05_06_gaussian'

HIGH_LOAD = {"A": 70, "B": 280, "C": 200}
MAPS = ["A", "B", "C"]

SWEEPS = [
    ("L", r"Spatial support $L$"),
    ("T", r"Temporal support $T$"),
    ("sigma_l", r"Spatial width $\sigma_l$"),
    ("sigma_t", r"Temporal width $\sigma_t$"),
]

MARKERS = {"A": "o", "B": "s", "C": "^"}
LINESTYLES = {"A": "-", "B": "--", "C": "-."}
COLORS = {
    "A": "#D62728",
    "B": "#4C72B0",
    "C": "#55A868",
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
})

# ---------- Prepare ----------
if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)
if OUT_DIR.exists():
    shutil.rmtree(OUT_DIR)

WORK_DIR.mkdir(parents=True)
OUT_DIR.mkdir(parents=True)
PANEL_DIR = OUT_DIR / "panels"
PANEL_DIR.mkdir()

# ---------- Extract result zip ----------
with zipfile.ZipFile(ZIP_PATH, "r") as zf:
    zf.extractall(WORK_DIR)

# Prefer the baseline-unified file.
summary_files = list(WORK_DIR.rglob("summary_results.csv"))
if not summary_files:
    raise FileNotFoundError(
        "summary_results.csv was not found in the ZIP file."
    )

df = pd.read_csv(summary_files[0])

# ---------- Render one panel ----------
def render_panel(sweep, col_title, metric, ci_metric,
                 ylabel, row_idx, col_idx, percent=False):

    sub = pd.concat([
        df[
            (df["map"] == m) &
            (df["task_count"] == HIGH_LOAD[m]) &
            (df["sweep"] == sweep)
        ]
        for m in MAPS
    ], ignore_index=True)

    # Keep the original panel dimensions.
    fig, ax = plt.subplots(figsize=(4.0, 3.0))

    for m in MAPS:
        ms = sub[sub["map"] == m].sort_values("value")

        y = ms[metric].to_numpy(dtype=float)
        err = ms[ci_metric].to_numpy(dtype=float)

        if percent:
            y = y * 100.0
            err = err * 100.0

        ax.errorbar(
            ms["value"].to_numpy(dtype=float),
            y,
            yerr=err,
            marker=MARKERS[m],
            linestyle=LINESTYLES[m],
            color=COLORS[m],
            linewidth=1.5,
            markersize=5,
            capsize=2.5,
            label=f"Map {m}",
        )

    if row_idx == 0:
        ax.set_title(col_title, pad=7)

    if col_idx == 0:
        ax.set_ylabel(ylabel)

    if row_idx == 2:
        xlabel_map = {
            "L": r"$L$",
            "T": r"$T$",
            "sigma_l": r"$\sigma_l$",
            "sigma_t": r"$\sigma_t$",
        }
        ax.set_xlabel(xlabel_map[sweep])

    # Keep the same y-axis scale within each row.
    if metric == "mean_success_rate":
        ax.set_ylim(65, 100)
    elif metric == "mean_planning_time":
        ax.set_ylim(0, 45)
    elif metric == "mean_average_congestion_fixed":
        ax.set_ylim(0.25, 0.50)

    ax.grid(True, alpha=0.25)
    ax.tick_params(direction="in")
    fig.tight_layout(pad=0.8)

    out = PANEL_DIR / f"r{row_idx}_c{col_idx}_{sweep}.png"

    # 300 dpi is enough for a response letter and cuts file size substantially.
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return out


ROWS = [
    ("mean_success_rate",
     "ci95_success_rate",
     "Success rate (%)",
     True),

    ("mean_planning_time",
     "ci95_planning_time",
     "Planning time (s)",
     False),

    ("mean_average_congestion_fixed",
     "ci95_average_congestion_fixed",
     "Average congestion (AC)",
     False),
]

panel_paths = []

for r, (metric, ci_metric, ylabel, percent) in enumerate(ROWS):
    row_paths = []

    for c, (sweep, title) in enumerate(SWEEPS):
        row_paths.append(
            render_panel(
                sweep=sweep,
                col_title=title,
                metric=metric,
                ci_metric=ci_metric,
                ylabel=ylabel,
                row_idx=r,
                col_idx=c,
                percent=percent,
            )
        )

    panel_paths.append(row_paths)

# ---------- Common legend ----------
legend_fig, legend_ax = plt.subplots(figsize=(5.5, 0.55))
legend_ax.axis("off")

for m in MAPS:
    legend_ax.plot(
        [], [],
        marker=MARKERS[m],
        linestyle=LINESTYLES[m],
        color=COLORS[m],
        linewidth=1.5,
        markersize=5,
        label=f"Map {m}",
    )

legend_ax.legend(loc="center", ncol=3, frameon=False)
legend_fig.tight_layout(pad=0)

legend_path = OUT_DIR / "legend.png"
legend_fig.savefig(
    legend_path,
    dpi=300,
    bbox_inches="tight",
    transparent=True,
)
plt.close(legend_fig)

# ---------- Combine 3 x 4 ----------
imgs = [
    [Image.open(p).convert("RGB") for p in row]
    for row in panel_paths
]
legend_img = Image.open(legend_path).convert("RGB")

cell_w = max(im.width for row in imgs for im in row)
cell_h = max(im.height for row in imgs for im in row)

# Keep original-style spacing.
gap_x = 20
gap_y = 18
legend_h = legend_img.height + 10

canvas_w = 4 * cell_w + 3 * gap_x
canvas_h = legend_h + 3 * cell_h + 2 * gap_y

canvas = Image.new("RGB", (canvas_w, canvas_h), "white")

legend_x = (canvas_w - legend_img.width) // 2
canvas.paste(legend_img, (legend_x, 0))

y0 = legend_h

for r in range(3):
    for c in range(4):
        im = imgs[r][c]

        x = (
            c * (cell_w + gap_x)
            + (cell_w - im.width) // 2
        )
        y = (
            y0
            + r * (cell_h + gap_y)
            + (cell_h - im.height) // 2
        )

        canvas.paste(im, (x, y))

# ---------- Save final outputs ----------
png_path = OUT_DIR / "Figure_R1_Gaussian_sensitivity_3x4.png"
pdf_path = OUT_DIR / "Figure_R1_Gaussian_sensitivity_3x4.pdf"

# High-quality PNG preview.
canvas.save(
    png_path,
    format="PNG",
    optimize=True,
)

# Compress PDF without changing the visible layout.
# PIL embeds this RGB canvas efficiently; 300 dpi is plenty for response letter use.
canvas.save(
    pdf_path,
    format="PDF",
    resolution=300.0,
    quality=92,
    optimize=True,
)

print("Done.")
print("PNG:", png_path)
print("PDF:", pdf_path)

# ---------- Cleanup ----------
if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)
