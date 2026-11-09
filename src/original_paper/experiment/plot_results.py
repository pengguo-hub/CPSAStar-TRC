"""
画图脚本：读取 test_new.py 生成的 JSON 日志，画带误差阴影的折线图。

使用方式：
    python plot_results.py

配置区在脚本顶部，修改 LOG_DIR、MAP_KEYS、TASK_COUNTS_LIST 即可。
"""
from pathlib import Path as _RepositoryPath
_REPO_ROOT = _RepositoryPath(__file__).resolve().parents[2]

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
import matplotlib.ticker as ticker

# ============================================================
# 用户配置区
# ============================================================
LOG_DIR          = str(_REPO_ROOT / 'results/original_paper/one_shot')
MAP_KEYS         = ['STANDARD']           # 要画的地图，每种地图输出一张图
TASK_COUNTS_LIST = list(range(10, 101, 10))  # 横轴档位，要和实验一致
SAVE_DIR         = str(_REPO_ROOT / 'figures/original_paper/one_shot')

# 1. 设置全局中文字体，这里以 SimHei (黑体) 为例
plt.rcParams['font.sans-serif'] = ['Times New Roman']

# 2. 解决负号 '-' 显示为方块的问题
plt.rcParams['axes.unicode_minus'] = False

# 算法显示名称映射（可选，用于图例更好看）
DISPLAY_NAMES = {
    "CPS-A*":            "CPS-A*(Ours)",
    # # "CPS_PBS":           "CPS-PBS(Ours)",
    # "ST-A*":             "CA*",
    "CA*":             "CA*",
    # "CA":                "CA*",
    "PBS":               "PBS",
    "CBS":               "CBS",
    "MCCP":              "MCCP",
    # "Fransen":           "Fransen",
    "LaCAM2_Guided":     "GP",
    "Q_Learning":        "Improved Q-learning",
}

# 算法颜色和线型（你的算法用红色加粗实线，其他用细虚线）
# STYLES = {
#     "CPS-A*":           dict(color="#E53713", lw=1, ls="-",  marker="o", ms=3, zorder=10),
#     # "CPS-A*":            dict(color="#3C54DC", lw=1, ls="-",  marker="s", ms=3, zorder=10),
#     "CA*":             dict(color="#ECB525", lw=1, ls="-", marker="d", ms=3, zorder=5),
#     # "CA":               dict(color="#7F8C8D", lw=1, ls="-",  marker="P", ms=3, zorder=10),
#     "MCCP":              dict(color="#0D842F", lw=1, ls="-", marker="^", ms=3, zorder=5),
#     "PBS":               dict(color="#6CCB93", lw=1, ls="-", marker="D", ms=3, zorder=5),
#     "CBS":               dict(color="#a65283", lw=1, ls="-", marker="v", ms=3, zorder=5),
#     "LaCAM2_Guided":     dict(color="#F3A37F", lw=1, ls="-", marker="p", ms=3, zorder=5),
#     # "Q_Learning":        dict(color="#8388A5", lw=1, ls="-", marker="*", ms=3, zorder=5),
# }
STYLES = {
    "CPS-A*":           dict(color="#E53713", lw=1, ls="-",  marker="o", ms=3, zorder=10),
    # "CPS-A*":            dict(color="#3C54DC", lw=1, ls="-",  marker="s", ms=3, zorder=10),
    # "ST-A*":             dict(color="#ECB525", lw=1, ls="-", marker="d", ms=3, zorder=5),
    "CA*":             dict(color="#ECB525", lw=1, ls="-", marker="d", ms=3, zorder=5),
    # "CA":               dict(color="#7F8C8D", lw=1, ls="-",  marker="P", ms=3, zorder=10),
    "MCCP":              dict(color="#0D842F", lw=1, ls="-", marker="^", ms=3, zorder=5),
    "PBS":               dict(color="#3C54DC", lw=1, ls="-", marker="D", ms=3, zorder=5),
    "CBS":               dict(color="#a65283", lw=1, ls="-", marker="v", ms=3, zorder=5),
    "LaCAM2_Guided":     dict(color="#F3A37F", lw=1, ls="-", marker="p", ms=3, zorder=5),
    "Q_Learning":        dict(color="#8388A5", lw=1, ls="-", marker="*", ms=3, zorder=5),
}
#legend 排列顺序
LEGEND_ORDER = [
        "CPS-A*",      # 第1个
        # "CPS-A*",       # 第2个
        "MCCP",         # 第3个
        # "CA",          # 第4个
        "CA*",        # 第5个
        "PBS",          # ...
        "CBS",
        "LaCAM2_Guided",
        "Q_Learning"
    ]

DEFAULT_STYLE = dict(color="#333333", lw=1.5, ls=":", marker="o", ms=4, zorder=5)
# ============================================================


def load_log(log_dir, map_key, task_count):
    """加载一个 JSON 日志文件，返回 dict 或 None"""
    path = os.path.join(log_dir, f"{map_key}_{task_count}tasks.json")
    if not os.path.exists(path):
        print(f"  ⚠️  找不到文件: {path}，跳过 task_count={task_count}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def gather_data(log_dir, map_key, task_counts_list, metric):
    """
    收集某个地图、某个指标在所有任务量上的均值和标准差。
    返回:
        planners: list[str]  算法名列表（取第一个存在的日志的算法）
        xs:       list[int]  实际存在数据的任务量
        means:    dict[planner -> list[float]]
        stds:     dict[planner -> list[float]]
    """
    # 先找到所有算法名
    planners = None
    for tc in task_counts_list:
        data = load_log(log_dir, map_key, tc)
        if data is not None:
            planners = list(data["results"].keys())
            break
    if planners is None:
        return [], [], {}, {}

    xs = []
    means = {p: [] for p in planners}
    stds  = {p: [] for p in planners}

    for tc in task_counts_list:
        data = load_log(log_dir, map_key, tc)
        if data is None:
            continue
        xs.append(tc)
        for p in planners:
            if p not in data["results"]:
                means[p].append(np.nan)
                stds[p].append(0)
                continue
            seed_data = data["results"][p]
            vals = [v[metric] for v in seed_data.values() if metric in v]
            if vals:
                means[p].append(float(np.mean(vals)))
                stds[p].append(float(np.std(vals)))
            else:
                means[p].append(np.nan)
                stds[p].append(0)

    return planners, xs, means, stds


def plot_map(log_dir, map_key, task_counts_list, save_dir):
    """为一种地图画上下双图（成功率 + 规划耗时），保存为 PNG"""

    planners, xs, means_sr, stds_sr = gather_data(log_dir, map_key, task_counts_list, "success_rate")
    _,        _,  means_pt, stds_pt = gather_data(log_dir, map_key, task_counts_list, "planning_time")

    if not xs:
        print(f"  ❌ {map_key} 没有找到任何数据，跳过。")
        return

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(5, 6), sharex=True,
        gridspec_kw={"hspace": 0.06}
    )

    legend_handles = []
    legend_labels = []

    for p in LEGEND_ORDER:
        if p not in STYLES or p not in means_sr:
            continue
        style = STYLES.get(p, DEFAULT_STYLE).copy()
        label = DISPLAY_NAMES.get(p, p)
        color = style.pop("color")
        zorder = style.pop("zorder")
        alpha_fill = 0.18

        # 成功率图
        m = np.array(means_sr[p])
        s = np.array(stds_sr[p])
        # ax1.plot(xs, m, color=color, label=label, zorder=zorder, **style)
        # ax1.fill_between(xs, m - s, m + s, color=color, alpha=alpha_fill, zorder=zorder - 1)
        line_obj = ax1.plot(xs, m, color=color, label=label, zorder=zorder, **style)[0]

        # 规划耗时图（重新 pop style，因为上面已经 pop 过一次，需要重新取）
        style2 = STYLES.get(p, DEFAULT_STYLE).copy()
        style2.pop("color")
        style2.pop("zorder")
        m2 = np.array(means_pt[p])
        s2 = np.array(stds_pt[p])
        ax2.plot(xs, m2, color=color, zorder=zorder, **style2)
        # ax2.fill_between(xs, np.maximum(m2 - s2, 0), m2 + s2, color=color, alpha=alpha_fill, zorder=zorder - 1)

        if p in LEGEND_ORDER:
            legend_handles.append(line_obj)
            legend_labels.append(label)

    # ---- 上图：成功率 ----
    ax1.set_ylabel("Success Rate", fontsize=14)
    ax1.set_ylim(-0.05, 1.05)
    ticks = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]  # 这里定义你想要的刻度值
    ax1.yaxis.set_major_locator(ticker.FixedLocator(ticks))
    ax1.yaxis.set_major_formatter(ticker.FixedFormatter([f"{x:.1f}" for x in ticks]))
    num_planners = len(planners)
    ncol_val = 8  # <--- 这里控制一行显示几个，建议设为 5 或 4

    # ax1.legend(
    #     legend_handles,  # <--- 传入手动排序的句柄
    #     legend_labels,  # <--- 传入手动排序的标签
    #     loc="upper center",
    #     bbox_to_anchor=(0.5, 1.35),
    #     ncol=ncol_val,  # <--- 关键修改：固定列数，自动换行
    #     fontsize=9,
    #     frameon=True,
    #     handlelength=2.5,
    #     columnspacing=1.0,  # 列之间的间距
    #     handletextpad=0.5  # 标记和文字之间的间距
    # )
    # ax1.set_title(f"Map {MAP_KEYS}", fontsize=10, pad=6)

    # ---- 下图：规划耗时 ----
    ax2.set_ylabel("Planning Time (s)", fontsize=14)
    ax2.set_yscale("log")
    ax2.set_ylim(0.006, 300)
    # 使用 FixedLocator 和 FixedFormatter 强制锁定
    ticks = [0.006,0.06,0.6,6,60,260]#STANDARD
    # ticks = [0.6, 6, 60, 120]
    ax2.yaxis.set_major_locator(ticker.FixedLocator(ticks))
    ax2.yaxis.set_major_formatter(ticker.FixedFormatter([f"{x:g}" for x in ticks]))
    # 关闭次刻度线（去掉那些杂乱的小线）
    ax2.minorticks_off()

    ax2.set_xlabel("Number of Tasks", fontsize=14, labelpad=8)

    # ax2.grid(axis="y", linestyle="--", alpha=0.4)
    # ax2.grid(axis="x", linestyle="--", alpha=0.2)

    # 1. 设置刻度线的位置：从 100 到 300，每隔 10 画一条线（包括短线和长线）
    # 这样保证了每个数据点都有对应的刻度线，可读性高
    ax2.set_xticks(xs)
    # 2. 设置刻度线的标签：只保留 50 的倍数对应的标签，其他位置留空
    # 结果类似：['100', '', '', '', '', '150', '', '', '', '', '200', ...]
    # labels = [str(x) if x % 50 == 0 else '' for x in xs]
    # ax2.set_xticklabels(labels, fontsize=9)
    ax2.set_xticklabels([str(x) for x in xs], fontsize=9)

    # 两个子图共用同一个图例（已在 ax1 里）调整ylabel的间距
    ax1.yaxis.set_label_coords(-0.10, 0.5)
    ax2.yaxis.set_label_coords(-0.10, 0.5)
    # plt.tight_layout()

    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f"comparison_{map_key}.pdf")
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    print(f"  ✅ 图已保存: {save_path}")
    # plt.show()


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    for map_key in MAP_KEYS:
        print(f"\n📊 正在画地图 {map_key} 的对比图...")
        plot_map(LOG_DIR, map_key, TASK_COUNTS_LIST, SAVE_DIR)
    print("\n🎉 全部图表生成完毕！")
