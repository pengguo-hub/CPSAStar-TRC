"""
main.py
对应 C++ main.cpp（GUIDANCE=ON 完整版本）

命令行用法（与 C++ 二进制保持一致的参数名）：
  python main.py -m <map_file> -N <num_agents> [options]

选项：
  -m / --map            地图文件路径（必填）
  -i / --scen           场景文件路径（可选，不填则随机生成）
  -N / --num            智能体数量（必填）
  -s / --seed           随机种子（默认 0）
  -v / --verbose        日志详细程度（默认 0）
  -t / --time_limit_sec 时间限制秒数（默认 30）
  -o / --output         输出文件路径（默认 ./result.txt）
  -l / --log_short      只输出统计信息，不写路径（flag）
  -O / --objective      优化目标：0=none,1=makespan,2=sum_of_loss,3=sum_of_cost（默认 0）
  -r / --restart_rate   随机重启概率（默认 0.001）
  -g / --guid_t         引导路径预计算时间（秒，默认 30，对应论文 GUID_T=30）
  --no_guidance         禁用引导（退化为纯 LaCAM2 基线，默认启用引导）
"""

import argparse
import random
import sys
import os

# 把包目录加入搜索路径（使 main.py 可以在包外直接运行）
pass  # Package imports replace process-wide import-path mutation.

from src.original_paper.experiment.lacam2_python.lacam2 import Instance, Objective, Deadline, solve, is_feasible_solution, print_stats, make_log


def main():
    parser = argparse.ArgumentParser(prog="lacam2", description="Guided LaCAM2 MAPF solver (Python)")
    parser.add_argument("-m", "--map",            required=True,          help="地图文件路径 (.map)")
    parser.add_argument("-i", "--scen",           default="",            help="场景文件路径 (.scen)")
    parser.add_argument("-N", "--num",            required=True,          help="智能体数量")
    parser.add_argument("-s", "--seed",           default="0",           help="随机种子")
    parser.add_argument("-v", "--verbose",        default="0",           help="日志详细程度")
    parser.add_argument("-t", "--time_limit_sec", default="30",          help="时间限制（秒）")
    parser.add_argument("-o", "--output",         default="./result.txt",help="输出日志文件")
    parser.add_argument("-l", "--log_short",      action="store_true",   help="只输出统计头，不写路径")
    parser.add_argument("-O", "--objective",      default="0",
                        choices=["0", "1", "2", "3"],
                        help="优化目标: 0=none, 1=makespan, 2=sum_of_loss, 3=sum_of_cost")
    parser.add_argument("-r", "--restart_rate",   default="0.001",       help="随机重启概率")
    parser.add_argument("-g", "--guid_t",         default="30",
                        help="引导路径预计算时间（秒，论文 GUID_T=30）")
    parser.add_argument("--no_guidance",          action="store_true",
                        help="禁用引导，退化为纯 LaCAM2 基线")

    args = parser.parse_args()

    verbose        = int(args.verbose)
    time_limit_sec = int(args.time_limit_sec)
    scen_name      = args.scen
    seed           = int(args.seed)
    map_name       = args.map
    output_name    = args.output
    log_short      = args.log_short
    N              = int(args.num)
    objective      = Objective(int(args.objective))
    restart_rate   = float(args.restart_rate)
    guid_t_sec     = float(args.guid_t)
    use_guidance   = not args.no_guidance

    rng = random.Random(seed)

    # 构建实例
    if scen_name:
        ins = Instance.from_scen(scen_name, map_name, N, rng)
    else:
        ins = Instance.from_random(map_name, N, rng)

    if not ins.is_valid(verbose=1):
        sys.exit(1)

    # 求解
    # 对应 C++ main.cpp：
    #   auto deadline = Deadline(time_limit_sec * 1000)
    #   Planner(..., deadline)
    #   D.setup_guidance(ins, deadline->time_limit_ms)
    # 即 guid_t_ms = GUID_T * 1000，作为引导预算传入
    guid_t_ms = guid_t_sec * 1000.0

    deadline = Deadline(time_limit_sec * 1000)
    solution, additional_info = solve(
        ins,
        verbose=verbose - 1,
        deadline=deadline,
        rng=rng,
        objective=objective,
        restart_rate=restart_rate,
        guid_t_ms=guid_t_ms if use_guidance else 0.0,
    )
    comp_time_ms = deadline.elapsed_ms()

    # 失败检查
    if not solution:
        if verbose >= 1:
            print("failed to solve")

    # 可行性检查
    if not is_feasible_solution(ins, solution, verbose):
        if verbose >= 0:
            print("invalid solution")

    # 后处理
    print_stats(verbose, ins, solution, comp_time_ms)
    make_log(ins, solution, output_name, comp_time_ms, map_name, seed,
             additional_info, log_short)


if __name__ == "__main__":
    main()
