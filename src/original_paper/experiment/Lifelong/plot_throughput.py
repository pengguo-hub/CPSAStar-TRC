import sys
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Times New Roman"]
plt.rcParams["axes.unicode_minus"] = False

# CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "multi_algo_results.csv"
CSV_FILE = "lifelong_results/multi_algo_results_warehouse_20_40_10_2_1.csv"

ALGO_LABELS = {
    "cps_a": "CPS-A (Ours)",
    "rhcr": "RHCR",
    "guided_pibt": "GP",
    "cmpp": "CMPP",
    "pibt": "PIBT",
}

ALGO_COLORS = {
    "cps_a": "#DC2626",
    "rhcr": "#2563EB",
    "guided_pibt": "#16A34A",
    "cmpp": "#D97706",
    "pibt": "#7C3AED",
}

ALGO_MARKERS = {
    "cps_a": "o",
    "rhcr": "s",
    "guided_pibt": "^",
    "cmpp": "D",
    "pibt": "v",
}

ALGO_ORDER = ["cps_a", "rhcr", "guided_pibt", "cmpp", "pibt"]

OUT_PNG = os.path.splitext(CSV_FILE)[0] + "_3subplots.png"


def draw_metric(ax, df, algos, mean_col, std_col, title, ylabel):
    for algo in algos:
        sub = df[df["algo"] == algo].sort_values("num_agvs")
        xs = sub["num_agvs"].values
        mean = sub[mean_col].values
        std = sub[std_col].values

        label = ALGO_LABELS.get(algo, algo)
        color = ALGO_COLORS.get(algo, "#333333")
        mk = ALGO_MARKERS.get(algo, "o")

        ax.plot(
            xs, mean,
            marker=mk,
            color=color,
            linewidth=2,
            markersize=6,
            label=label
        )
        ax.fill_between(
            xs,
            mean - std,
            mean + std,
            color=color,
            alpha=0.15
        )

    ax.set_title(title, fontsize=12)
    ax.set_xlabel("Number of AGVs", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.tick_params(axis="both", labelsize=9)

    xticks = sorted(df["num_agvs"].dropna().unique())
    ax.set_xticks(xticks)
    if len(xticks) >= 2:
        x_pad = (xticks[1] - xticks[0]) * 0.25
    else:
        x_pad = 5
    ax.set_xlim(min(xticks) - x_pad, max(xticks) + x_pad)
    ax.minorticks_off()


def main():
    if not os.path.exists(CSV_FILE):
        print(f"[ERROR] 找不到文件: {CSV_FILE}")
        sys.exit(1)

    df = pd.read_csv(CSV_FILE)

    numeric_cols = [
        "num_agvs",
        "throughput_mean", "throughput_std",
        "success_mean", "success_std",
        "walltime_mean", "walltime_std",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["num_agvs"])
    algos = [a for a in ALGO_ORDER if a in df["algo"].unique()]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))

    draw_metric(
        axes[0], df, algos,
        "throughput_mean", "throughput_std",
        "Throughput", "Tasks / Timestep"
    )
    draw_metric(
        axes[1], df, algos,
        "success_mean", "success_std",
        "Success Rate", "Success Rate (%)"
    )
    draw_metric(
        axes[2], df, algos,
        "walltime_mean", "walltime_std",
        "Wall Time", "Time (s)"
    )

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="upper center",
        ncol=len(labels),
        fontsize=10,
        frameon=False,
        bbox_to_anchor=(0.5, 1.08)
    )

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT_PNG, dpi=600, bbox_inches="tight")
    print(f"图片已保存: {OUT_PNG}")


if __name__ == "__main__":
    main()