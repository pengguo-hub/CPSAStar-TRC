from pathlib import Path
import zipfile
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_REPO_ROOT = Path(__file__).resolve().parents[5]
ZIP_PATH = _REPO_ROOT / 'provenance/source_archives/06-result_R1_9_R_sensitivity.zip'
OUT_DIR = _REPO_ROOT / 'figures/revision/R1_09_retry_limit'
OUT_DIR.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(ZIP_PATH, "r") as zf:
    summary_name = [n for n in zf.namelist() if n.endswith("summary_results.csv")][0]
    df = pd.read_csv(zf.open(summary_name))

COLORS = {
    "A": "#D62728",
    "B": "#4C72B0",
    "C": "#55A868",
}
MAPS = ["A", "B", "C"]
LOADS = {
    "A": [50, 70],
    "B": [250, 280],
    "C": [150, 200],
}
MARKERS = ["o", "s"]
LINESTYLES = ["-", "--"]

plt.rcParams.update({
    "font.family": "Times New Roman",
    "mathtext.fontset": "stix",
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

fig, axes = plt.subplots(2, 3, figsize=(9.0, 5.2), sharex="col")

for col, m in enumerate(MAPS):
    for idx, load in enumerate(LOADS[m]):
        sub = df[(df["map"] == m) & (df["task_count"] == load)].sort_values("R")
        x = sub["R"].to_numpy()

        axes[0, col].errorbar(
            x, sub["success_mean"].to_numpy() * 100,
            yerr=sub["success_ci95"].to_numpy() * 100,
            marker=MARKERS[idx], linestyle=LINESTYLES[idx],
            color=COLORS[m], linewidth=1.5, markersize=4.5,
            capsize=2.2, label=f"{load} tasks"
        )
        axes[1, col].errorbar(
            x, sub["planning_time_mean"].to_numpy(),
            yerr=sub["planning_time_ci95"].to_numpy(),
            marker=MARKERS[idx], linestyle=LINESTYLES[idx],
            color=COLORS[m], linewidth=1.5, markersize=4.5,
            capsize=2.2, label=f"{load} tasks"
        )

    axes[0, col].set_title(f"Map {m}",pad=24)
    axes[1, col].set_xlabel(r"Retry limit $R$")
    for row in range(2):
        axes[row, col].grid(True, alpha=0.22, linewidth=0.6)
        axes[row, col].tick_params(direction="in")
        axes[row, col].axvline(5, color="0.55", linestyle=":", linewidth=1.0)
    axes[0, col].legend(
        frameon=False,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=2,
        columnspacing=1.2,
        handlelength=1.8,
    )

axes[0, 0].set_ylabel("Success rate (%)")
axes[1, 0].set_ylabel("Planning time (s)")
fig.tight_layout(w_pad=1.0, h_pad=1.0)

fig.savefig(OUT_DIR / "Figure_R1_9_new_load_success_time_2x3.png",
            dpi=400, bbox_inches="tight")
fig.savefig(OUT_DIR / "Figure_R1_9_new_load_success_time_2x3.pdf",
            bbox_inches="tight")
plt.close(fig)
