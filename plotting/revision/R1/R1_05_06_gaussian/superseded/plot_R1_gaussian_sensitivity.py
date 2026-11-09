from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image
import zipfile, shutil

# ==========================================================
# Reviewer 1, Comments 5-6: Gaussian-parameter sensitivity
# Input: result_R1_gaussian_sensitivity.zip
# Output:
#   1) 3x4 arranged figure: success rate / planning time / AC
#   2) 2x2 success-rate-only figure
#   3) all individual panel PNGs
# ==========================================================

_REPO_ROOT = Path(__file__).resolve().parents[5]
ZIP_PATH = _REPO_ROOT / 'provenance/source_archives/04-result_R1_gaussian_sensitivity.zip'
WORK_DIR = _REPO_ROOT / 'outputs/plotting_tmp/R1_05_06_gaussian'
OUT_DIR = _REPO_ROOT / 'figures/revision/R1_05_06_gaussian/alternative'

HIGH_LOAD = {"A": 70, "B": 280, "C": 200}  # Scheme A
MAPS = ["A", "B", "C"]

SWEEPS = [
    ("L", r"Spatial support $L$"),
    ("T", r"Temporal support $T$"),
    ("sigma_l", r"Spatial width $\sigma_l$"),
    ("sigma_t", r"Temporal width $\sigma_t$"),
]

MARKERS = {"A": "o", "B": "s", "C": "^"}
LINESTYLES = {"A": "-", "B": "--", "C": "-."}
# COLORS = {"A": "red", "B": "blue", "C": "green"}
COLORS={    "A": "#D62728",
    "B": "#4C72B0",
    "C": "#55A868"}
# Paper-like typography. If Times New Roman is unavailable,
# Matplotlib will fall back to another serif font.
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

if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR)
if OUT_DIR.exists():
    shutil.rmtree(OUT_DIR)
WORK_DIR.mkdir(parents=True)
OUT_DIR.mkdir(parents=True)
PANEL_DIR = OUT_DIR / "panels"
PANEL_DIR.mkdir()

with zipfile.ZipFile(ZIP_PATH, "r") as zf:
    zf.extractall(WORK_DIR)

summary_files = list(WORK_DIR.rglob("summary_results.csv"))
if not summary_files:
    raise FileNotFoundError("summary_results.csv was not found in the ZIP file.")
df = pd.read_csv(summary_files[0])

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

    # Each chart is rendered independently. They are combined afterwards.
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
            label=f"Map {m}"
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

    # Use the same success-rate axis for all four success panels.
    if metric == "mean_success_rate":
        ax.set_ylim(65, 100)

    ax.grid(True, alpha=0.25)
    ax.tick_params(direction="in")
    fig.tight_layout(pad=0.8)

    out = PANEL_DIR / f"r{row_idx}_c{col_idx}_{sweep}.png"
    fig.savefig(out, dpi=600, bbox_inches="tight")
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
    dpi=600,
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

main_png = OUT_DIR / "Figure_R1_Gaussian_sensitivity_3x4.pdf"
canvas.save(main_png, dpi=(600, 600))

# ---------- Compact 2 x 2: success rate only ----------
success_imgs = imgs[0]

compact_w = 2 * cell_w + gap_x
compact_h = legend_h + 2 * cell_h + gap_y

compact = Image.new(
    "RGB",
    (compact_w, compact_h),
    "white",
)

legend_x = (compact_w - legend_img.width) // 2
compact.paste(legend_img, (legend_x, 0))

for i, im in enumerate(success_imgs):
    r, c = divmod(i, 2)

    x = (
        c * (cell_w + gap_x)
        + (cell_w - im.width) // 2
    )
    y = (
        legend_h
        + r * (cell_h + gap_y)
        + (cell_h - im.height) // 2
    )

    compact.paste(im, (x, y))

compact_png = OUT_DIR / "Figure_R1_Gaussian_sensitivity_success_2x2.png"
compact.save(compact_png, dpi=(600, 600))

print("Done.")
print("Main figure:", main_png)
print("Compact figure:", compact_png)
print("Individual panels:", PANEL_DIR)
