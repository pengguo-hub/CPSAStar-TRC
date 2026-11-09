"""
plot_throughput_ourmaps.py

参考 plot_throughput.py 的写法，读取自定义 benchmark CSV，
分别为 STANDARD / FRANSEN / RING 画吞吐量折线图（含 ±1 std 误差带）。

重要：
- 颜色不再按 CSV 中算法出现顺序分配
- 颜色与 marker 按算法名固定映射
- 与 MovingAI 版本保持一致：
    cps_a       -> 红色  + 圆点
    rhcr        -> 蓝色  + 方块
    guided_pibt -> 绿色  + 三角
    cmpp_acmts  -> 橙色  + 菱形

用法：
python plot_throughput_ourmaps.py your_results.csv

或者直接修改下面的 CSV_FILE。
"""

import sys
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# 1. 设置全局中文字体，这里以 SimHei (黑体) 为例
plt.rcParams['font.sans-serif'] = ['Times New Roman']
# 2. 解决负号 '-' 显示为方块的问题
plt.rcParams['axes.unicode_minus'] = False
# ===================== 配置 =====================
# CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "multi_algo_custom_results.csv"
CSV_FILE = "lifelong_results/test_ourmaps_results_20260421_225013.csv"

ALGO_LABELS = {
    "cps_a": "CPS-A (Ours)",
    "rhcr": "RHCR",
    "guided_pibt": "GP",
    "cmpp": "CMPP",
    "pibt": "PIBT",
}

ALGO_COLORS = {
    "cps_a": "#DC2626", #红
    "rhcr": "#2563EB", # 蓝
    "guided_pibt": "#16A34A", # 绿
    "cmpp": "#D97706", # 橙
    "pibt": "#7C3AED", # 紫
}

ALGO_MARKERS = {
    "cps_a": "o",
    "rhcr": "s",
    "guided_pibt": "^",
    "cmpp": "D",
    "pibt": "v",
}

ALGO_ORDER = ["cps_a", "rhcr", "guided_pibt", "cmpp", "pibt"]

MAPS = ["STANDARD", "FRANSEN", "RING"]
# ===============================================


def plot_one_map(df, map_name):
    sub_map = df[df["map_name"] == map_name].copy()
    if sub_map.empty:
        print(f"[WARN] 地图 {map_name} 没有数据，跳过")
        return

    algos = [a for a in ALGO_ORDER if a in sub_map["algo"].unique()]

    fig, ax = plt.subplots(figsize=(4, 4))

    for algo in algos:
        sub = sub_map[sub_map["algo"] == algo].sort_values("num_agvs")

        xs = sub["num_agvs"].values
        mean = sub["throughput_mean"].values
        std = sub["throughput_std"].values

        label = ALGO_LABELS.get(algo, algo)
        color = ALGO_COLORS.get(algo, "#333333")
        mk = ALGO_MARKERS.get(algo, "o")

        ax.plot(
            xs,
            mean,
            marker=mk,
            color=color,
            linewidth=2,
            markersize=6,
            label=label,
        )

        ax.fill_between(
            xs,
            mean - std,
            mean + std,
            color=color,
            alpha=0.15,
        )

    # ax.legend(
    #     loc="upper center",
    #     bbox_to_anchor=(0.5, 1.18),
    #     ncol=len(algos),
    #     fontsize=10,
    #     framealpha=0.9,
    # )
    # ax.set_title(f"{map_name} Throughput", fontsize=13, fontweight="bold")
    # ax.set_xlabel("Number of AGVs", fontsize=11)
    # ax.set_ylabel("Throughput", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.4)
    # ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    if map_name == "STANDARD":
        xticks =[10, 30, 50, 70, 90]
        x_left = 5
        x_right = 95
    elif map_name == "FRANSEN":
        xticks = [50, 100, 150, 200, 250]
        x_left = 45
        x_right = 255
    elif map_name == "RING":
        xticks = [40, 80, 120, 160, 200]
        x_left = 35
        x_right = 205
    else:
        xticks = sorted(sub_map["num_agvs"].dropna().unique())
        x_left = min(xticks) - 5 if len(xticks) > 0 else 0

    ax.set_xticks(xticks)
    ax.set_xlim(x_left, x_right)
    ax.minorticks_off()
    ax.tick_params(axis="both", labelsize=10)
    ax.set_ylim(bottom=-0.1)

    # fig.tight_layout(rect=[0, 0, 1, 0.93])

    out_png = f"{map_name.lower()}.png"
    fig.savefig(out_png, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"图片已保存: {out_png}")



def main():
    if not os.path.exists(CSV_FILE):
        print(f"[ERROR] 找不到文件: {CSV_FILE}")
        sys.exit(1)

    df = pd.read_csv(CSV_FILE)

    required_cols = ["map_name", "num_agvs", "algo", "throughput_mean", "throughput_std"]
    for c in required_cols:
        if c not in df.columns:
            print(f"[ERROR] CSV 缺少列: {c}")
            sys.exit(1)

    df["throughput_mean"] = pd.to_numeric(df["throughput_mean"], errors="coerce")
    df["throughput_std"] = pd.to_numeric(df["throughput_std"], errors="coerce")
    df = df.dropna(subset=["throughput_mean"])

    for map_name in MAPS:
        plot_one_map(df, map_name)


if __name__ == "__main__":
    main()
