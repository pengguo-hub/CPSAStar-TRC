"""
lifelong_runner.py
==================
对接 BenchmarkLoader 的高层入口。
封装 SharedEnv + MAPFPlanner + CompetitionSystem 的初始化，
提供与你现有测试脚本（test_lifelong-2.py）风格一致的接口。

使用方式：
    from guided_pibt.lifelong_runner import GuidedPIBTRunner

    loader = BenchmarkLoader(MAP_FILE, SCEN_FILE)
    grid, agv_info, init_pos, task_queue = loader.load_all(num_agvs=100, ...)

    runner = GuidedPIBTRunner(
        grid, agv_info, init_pos, task_queue,
        R_init=100,         # 每 timestep lazy-init 上限（论文 GP-R100）
        refine_iters=10,    # 每 timestep LNS 迭代次数（GP-Re10）
        guidance=True,      # False = 退化为纯 PIBT baseline
    )
    completed, stats = runner.run(max_timesteps=3200)

    print(f"完成任务: {stats['tasks_completed']}")
    print(f"吞吐量: {stats['throughput']:.4f} 任务/时间步")
    print(f"平均完成时间: {stats['avg_task_time']:.1f}")
"""

from __future__ import annotations

import os
import sys
from collections import deque
from typing import Dict, List, Optional, Deque, Tuple

# 确保 workspace 根目录在 sys.path（让 traffic_mapf 包可以被 import）
_WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE not in sys.path:
    pass  # Package imports replace process-wide import-path mutation.

# 需要先把 flow/traj_lns 等文件放在 traffic_mapf/ 包下，或者用以下 shim
# （见文末 _setup_traffic_mapf_package()）
_setup_done = False


def _setup_traffic_mapf_package():
    """
    你现有的 flow.py / traj_lns.py / search.py 等文件在 workspace 根目录，
    但它们用的是 from .xxx import ... 相对 import，需要作为包来使用。

    这里在 workspace 根目录自动创建 traffic_mapf/ 软链接或复制，
    使 'import traffic_mapf.flow' 可以正常工作。

    如果你已经手动将这些文件整理进了 traffic_mapf/ 目录，可以删除此函数。
    """
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    tm_dir = os.path.join(_WORKSPACE, "traffic_mapf")
    if os.path.isdir(tm_dir):
        # 已存在，直接用
        return

    # traffic_mapf 不存在：创建包目录，把根目录的文件软链进去
    os.makedirs(tm_dir, exist_ok=True)

    _TM_FILES = [
        "flow.py", "traj_lns.py", "search.py", "heuristics.py",
        "search_node.py", "heap.py", "utils.py", "types.py",
    ]

    init_content = '"""traffic_mapf package (auto-generated shim)"""\n'
    with open(os.path.join(tm_dir, "__init__.py"), "w") as f:
        f.write(init_content)

    for fname in _TM_FILES:
        src = os.path.join(_WORKSPACE, fname)
        dst = os.path.join(tm_dir, fname)
        if os.path.exists(src) and not os.path.exists(dst):
            # 写一个转发模块（不复制，避免双重维护）
            # 直接复制文件内容（最简单可靠）
            import shutil
            shutil.copy2(src, dst)

    # 修正 traffic_mapf 包内文件的相对 import（将 from .xxx 重写为包内引用）
    # 注意：由于文件是直接复制的，内部的 from .xxx import 已经正确（包内相对 import）
    # 无需额外修改。


# 在导入其他模块前先 setup
_setup_traffic_mapf_package()

from .shared_env import SharedEnv
from .mapf_planner import MAPFPlanner
from .competition_system import CompetitionSystem, TaskRecord


# ===========================================================================
# GuidedPIBTRunner
# ===========================================================================

class GuidedPIBTRunner:
    """
    Lifelong Guided-PIBT 的统一入口，与 BenchmarkLoader 接口对齐。

    参数：
      grid              : BenchmarkLoader.load_map() 返回的 GridMap
      agv_info          : {agv_id: {'speed': float}}（速度字段不影响本算法，保留接口兼容）
      initial_positions : {agv_id: (x, y)}
      task_queue        : deque of ((pickup_x,pickup_y),(dropoff_x,dropoff_y))
      R_init            : 每 timestep 最多 lazy-init 几条 guide path（默认100=GP-R100）
      refine_iters      : GUIDANCE_LNS 宏的值，即 LNS 迭代次数上限；
                          实际迭代由 time_limit_s*0.8 控制；10 对应 GP-Re10
      guidance          : True=Guided PIBT；False=纯 PIBT baseline（对照实验用）
      time_limit_s      : 每步规划时间预算（秒），对应 C++ plan_time_limit（默认 1s）
    """

    def __init__(
        self,
        grid,
        agv_info: Dict,
        initial_positions: Dict,
        task_queue: Deque,
        R_init: int = 100,
        refine_iters: int = 10,
        guidance: bool = True,
    ):
        # ---- 构建 SharedEnv ----
        self.env = SharedEnv()
        self.env.load_from_gridmap(grid)
        self.env.init_agents(initial_positions)

        # ---- 构建 MAPFPlanner ----
        self.planner = MAPFPlanner(
            env=self.env,
            R_init=R_init,
            refine_iters=refine_iters,
            guidance=guidance,
            time_limit_s=1.0,   # C++ plan_time_limit 默认 1 秒
        )

        # ---- 构建 CompetitionSystem ----
        self.system = CompetitionSystem(
            env=self.env,
            planner=self.planner,
            task_queue=task_queue,
        )

        # 保存配置（用于打印）
        self._config = dict(
            R_init=R_init,
            refine_iters=refine_iters,
            guidance=guidance,
            num_agents=self.env.num_of_agents,
        )

    # ------------------------------------------------------------------
    # 主接口
    # ------------------------------------------------------------------

    def run(self, max_timesteps: int) -> Tuple[List[TaskRecord], dict]:
        """
        运行仿真，返回 (completed_tasks, stats)。

        Args:
            max_timesteps : 最大仿真步数（论文建议 (width+height)*5）

        Returns:
            completed_tasks : List[TaskRecord]
            stats           : dict，包含 throughput / avg_task_time / tasks_completed 等
        """
        if self._config["guidance"]:
            variant = f"GP-R{self._config['R_init']}"
            if self._config["refine_iters"] > 0:
                variant += f"-Re{self._config['refine_iters']}"
        else:
            variant = "PIBT-baseline"

        print(f"[GuidedPIBTRunner] 算法变体: {variant}")
        print(f"[GuidedPIBTRunner] agents={self._config['num_agents']}, "
              f"max_timesteps={max_timesteps}")

        completed, stats = self.system.run(max_timesteps)

        print(f"[GuidedPIBTRunner] 完成: {stats['tasks_completed']} 任务, "
              f"吞吐量={stats['throughput']:.4f}, "
              f"平均完成时间={stats['avg_task_time']:.1f} 步, "
              f"耗时={stats['wall_time_s']:.2f}s")

        return completed, stats

    # ------------------------------------------------------------------
    # 与 test_lifelong-2.py 兼容的属性
    # ------------------------------------------------------------------

    @property
    def current_time(self) -> int:
        return self.system.timestep

    def get_throughput(self) -> float:
        t = self.system.timestep
        n = len(self.system._completed)
        return n / t if t > 0 else 0.0
