import re
import matplotlib.pyplot as plt

def parse_multi_round_log(log_path):
    """
    从 multi_round_results.log 中解析出 multi_round_results 字典
    """
    results = {}
    current_N = None

    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if line.startswith("Test_Size ="):
            # 提取 N
            match = re.search(r"Test_Size = (\d+)", line)
            if match:
                current_N = int(match.group(1))
                results[current_N] = {}
        elif "Base Planner:" in line:
            continue
        elif "平均路径拥堵覆盖率:" in line and current_N is not None:
            # 示例: 平均路径拥堵覆盖率: 45.67% ± 2.34%
            match = re.search(r"平均路径拥堵覆盖率:\s*([\d.]+)%\s*±\s*([\d.]+)%", line)
            if match:
                base_mean = float(match.group(1)) / 100.0  # 转回小数
                base_std = float(match.group(2)) / 100.0
                results[current_N]['base_mean'] = base_mean
                results[current_N]['base_std'] = base_std
        elif "Conflict Planner:" in line:
            continue
        elif "平均路径拥堵覆盖率:" in line and "Conflict Planner" not in line:
            # 注意：上面已经处理过 Base 的，这里再出现就是 Conflict 的（因为顺序固定）
            # 但实际上更安全的做法是看上下文。我们改用状态机或更精确匹配。
            pass  # 我们换一种方式

    # 更健壮的方式：逐块解析
    results = {}
    block_lines = []
    in_block = False

    for line in lines:
        line = line.strip()
        if line.startswith("Test_Size ="):
            if block_lines:
                # 处理上一个 block
                _parse_block(block_lines, results)
                block_lines = []
            block_lines.append(line)
            in_block = True
        elif line.startswith("-" * 50):
            if block_lines:
                _parse_block(block_lines, results)
                block_lines = []
            in_block = False
        elif in_block and line:
            block_lines.append(line)

    # 最后一个 block
    if block_lines:
        _parse_block(block_lines, results)

    return results

def _parse_block(lines, results):
    """解析一个 Test_Size 块"""
    N = None
    base_mean = base_std = conflict_mean = conflict_std = None

    for line in lines:
        if line.startswith("Test_Size ="):
            N = int(line.split("=")[1].strip())
        elif "Base Planner:" in line:
            continue
        elif "Conflict Planner:" in line:
            continue
        elif "平均路径拥堵覆盖率:" in line:
            # 需要知道当前是在 Base 还是 Conflict 下
            # 我们通过前一行判断？或者记录状态
            pass

    # 更简单：按顺序提取两行“平均路径拥堵覆盖率”
    coverage_lines = [l for l in lines if "平均路径拥堵覆盖率:" in l]
    if len(coverage_lines) >= 2:
        base_line = coverage_lines[0]
        conflict_line = coverage_lines[1]

        base_match = re.search(r"([\d.]+)%\s*±\s*([\d.]+)%", base_line)
        conflict_match = re.search(r"([\d.]+)%\s*±\s*([\d.]+)%", conflict_line)

        if base_match and conflict_match:
            base_mean = float(base_match.group(1)) / 100.0
            base_std = float(base_match.group(2)) / 100.0
            conflict_mean = float(conflict_match.group(1)) / 100.0
            conflict_std = float(conflict_match.group(2)) / 100.0

            results[N] = {
                'base_mean': base_mean,
                'base_std': base_std,
                'conflict_mean': conflict_mean,
                'conflict_std': conflict_std,
            }

def plot_multi_round_congestion_from_data(multi_round_results, save_path="./replotted_congestion.png"):
    """
    复用原函数逻辑，但接受已解析的数据
    """
    # 1. 设置全局中文字体，这里以 SimHei (黑体) 为例
    plt.rcParams['font.sans-serif'] = ['Times New Roman']

    # 2. 解决负号 '-' 显示为方块的问题
    plt.rcParams['axes.unicode_minus'] = False

    Ns = sorted(multi_round_results.keys())
    base_means = [100 * multi_round_results[N]['base_mean'] for N in Ns]
    base_stds = [100 * multi_round_results[N]['base_std'] for N in Ns]
    conf_means = [100 * multi_round_results[N]['conflict_mean'] for N in Ns]
    conf_stds = [100 * multi_round_results[N]['conflict_std'] for N in Ns]

    plt.figure(figsize=(12, 7))
    plt.errorbar(Ns, base_means, yerr=base_stds, fmt='o-', capsize=4,
                 label="CA*", color="#ECB525")
    plt.errorbar(Ns, conf_means, yerr=conf_stds, fmt='s-', capsize=4,
                 label="CPS-A*", color="#E53713")

    for i, n in enumerate(Ns):
        plt.text(n, base_means[i] + base_stds[i] + 0.85,
                 f'σ={base_stds[i]:.1f}%',
                 ha='center', fontsize=12, color='#ECB525', fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor='#ECB525'))

        plt.text(n, conf_means[i] - conf_stds[i] - 1.30,
                 f'σ={conf_stds[i]:.1f}%',
                 ha='center', fontsize=12, color='#E53713', fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor='#E53713'))

    plt.xlabel("Number of test tasks",fontsize=22,labelpad=10)
    plt.ylabel("Average congestion coverage (%)",fontsize=22, labelpad=10)
    # plt.title("MAP C with 100 fixed background tasks",fontsize=16, pad=10)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.legend(fontsize=14, frameon=True, fancybox=True, framealpha=0.9, loc='upper right')
    plt.xticks(Ns, fontsize=20)
    plt.yticks(fontsize=20)
    y_min = min(conf_means) - max(conf_stds) - 2
    y_max = max(base_means) + max(base_stds) + 2
    plt.ylim(y_min, y_max)
    plt.tight_layout()
    plt.savefig(save_path, dpi=600)
    plt.close()
    print(f"✅ Replotted figure saved to: {save_path}")

# ==============================
# 主程序
# ==============================
if __name__ == "__main__":
    log_file = "congestion_avoidance_base_327/FRANSEN_multi_round_results.log"  # 替换为你的实际路径
    data = parse_multi_round_log(log_file)
    plot_multi_round_congestion_from_data(data, save_path="FRANSEN_replotted_from_log.png")