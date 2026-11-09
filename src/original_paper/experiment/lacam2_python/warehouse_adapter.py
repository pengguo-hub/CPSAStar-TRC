"""
warehouse_adapter.py
--------------------
将仓库地图和任务格式适配到 lacam2_python（Guided LaCAM2）求解器。

功能：
  1. build_map_file()      — 将 shelf_map (x,y) 障碍物转换为 MovingAI .map 文件（临时文件）
  2. xy_to_index()         — (x, y) → LaCAM2 顶点下标  (index = y * width + x)
  3. index_to_xy()         — LaCAM2 顶点下标 → (x, y)
  4. solve_phase()         — 对一组 (start_xy, goal_xy) 调用 LaCAM2，返回每个 agent 的坐标路径
  5. IntegratedAGVPlanner_LaCAM2 — 与 test.py 的 planner_classes 接口兼容的规划器类
                                   实现 batch_plan(parsed_tasks) → {agv_id: [(x,y), ...]}

算法参数（固定，与论文 Fig.2 一致）：
  GUIDANCE=ON, GUIDANCE_LNS=5000, INIT_PP=ON
  OBJECTIVE=OBJ_VC, FOCAL_SEARCH w=2, LNS_GROUP_SIZE=10, GUID_T=30 (ms)

两阶段规划策略：
  阶段一：agv_position → source   （多 AGV 同步无冲突路径）
  阶段二：source → destination    （多 AGV 同步无冲突路径）
  拼接：phase1_path + phase2_path[1:]  (去掉 phase2 起点，避免重复)
"""

from __future__ import annotations

import os
import sys
import tempfile
import random
from typing import Dict, List, Tuple, Optional

# ── 将 lacam2_python 加入搜索路径（若直接运行此文件时）──────────────────────
# _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# _LACAM2_DIR = os.path.join(_THIS_DIR, "lacam2_python")
# if _LACAM2_DIR not in sys.path:
#     sys.path.insert(0, _LACAM2_DIR)

from .lacam2 import Instance, Deadline, solve, Objective, is_feasible_solution

# ═══════════════════════════════════════════════════════════════════════════════
# 坐标工具
# ═══════════════════════════════════════════════════════════════════════════════

def xy_to_index(x: int, y: int, width: int) -> int:
    """(x, y) → 顶点下标。LaCAM2 用 row-major: index = y * width + x"""
    return y * width + x


def index_to_xy(index: int, width: int) -> Tuple[int, int]:
    """顶点下标 → (x, y)"""
    return index % width, index // width


# ═══════════════════════════════════════════════════════════════════════════════
# 地图文件构建
# ═══════════════════════════════════════════════════════════════════════════════

def build_map_file(
    width: int,
    height: int,
    shelf_map: Dict,
    map_path: Optional[str] = None,
) -> str:
    """
    将仓库 shelf_map 中的坐标转换为 MovingAI .map 格式文件。

    Parameters
    ----------
    width, height : 地图尺寸
    shelf_map     : {shelf_name: [(x,y)...] or (x,y)}，货架坐标即障碍物
    map_path      : 若为 None，则写入临时文件；否则写到指定路径

    Returns
    -------
    写入的 .map 文件路径（字符串）
    """
    # 收集所有障碍物坐标
    obstacles = set()
    for coords in shelf_map.values():
        if isinstance(coords, list):
            for pt in coords:
                obstacles.add(tuple(pt))
        elif isinstance(coords, tuple) and len(coords) == 2:
            # 单个坐标 (x, y)
            if isinstance(coords[0], int):
                obstacles.add(coords)
            else:
                # coords 是坐标对的 tuple-of-tuples（罕见，防御性处理）
                for pt in coords:
                    obstacles.add(tuple(pt))

    # 构建网格字符串
    lines = [
        "type octile",
        f"height {height}",
        f"width {width}",
        "map",
    ]
    for row in range(height):        # row = y
        cells = []
        for col in range(width):     # col = x
            if (col, row) in obstacles:
                cells.append("@")
            else:
                cells.append(".")
        lines.append("".join(cells))

    content = "\n".join(lines) + "\n"

    if map_path is None:
        fd, map_path = tempfile.mkstemp(suffix=".map", prefix="warehouse_")
        os.close(fd)

    with open(map_path, "w", encoding="utf-8") as f:
        f.write(content)

    return map_path


# ═══════════════════════════════════════════════════════════════════════════════
# 单阶段求解
# ═══════════════════════════════════════════════════════════════════════════════

def solve_phase(
    map_file: str,
    width: int,
    starts_xy: List[Tuple[int, int]],
    goals_xy: List[Tuple[int, int]],
    timeout_ms: int = 60000,
    guid_t_ms: int = 30000,
    rng: Optional[random.Random] = None,
    verbose: int = 0,
    disappear_on_goal: bool = False,
) -> Optional[Dict[int, List[Tuple[int, int]]]]:
    """
    对给定起点/终点列表调用 Guided LaCAM2 求解一次 MAPF。

    Parameters
    ----------
    map_file    : .map 文件路径
    width       : 地图宽度（用于坐标转换）
    starts_xy   : 每个 agent 的起点 [(x,y), ...]
    goals_xy    : 每个 agent 的终点 [(x,y), ...]
    timeout_ms  : 求解总时限（毫秒），默认 60 秒
    guid_t_ms   : 离线引导规划时限（毫秒），默认 30 秒（论文参数）
    rng         : 随机数生成器（None 则新建）
    verbose     : 日志级别（0=静默）

    Returns
    -------
    {agent_idx: [(x,y), ...]} 每个 agent 的时空路径，或 None（求解失败）
    """
    if rng is None:
        rng = random.Random(0)

    # 坐标 → 下标
    starts_idx = [xy_to_index(x, y, width) for x, y in starts_xy]
    goals_idx  = [xy_to_index(x, y, width) for x, y in goals_xy]

    ins = Instance.from_indexes(map_file, starts_idx, goals_idx)

    solution, info = solve(
        ins,
        verbose=verbose,
        deadline=Deadline(timeout_ms),
        rng=rng,
        objective=Objective.OBJ_NONE,   # OBJ_VC 对应 OBJECTIVE=1；OBJ_NONE 仍走 Guided 流程
        guid_t_ms=guid_t_ms,
        disappear_on_goal=disappear_on_goal,
    )

    if solution is None:
        return None

    # 将 solution (List[Config]) → {agent_idx: [(x,y), ...]}
    N = len(starts_xy)
    paths: Dict[int, List[Tuple[int, int]]] = {i: [] for i in range(N)}
    for config in solution:
        for i, vertex in enumerate(config):
            paths[i].append(index_to_xy(vertex.index, width))

    # # 标记未完成的 AGV（路径终点不是 goal），清空路径让上层过滤
    # for i in range(N):
    #     goal_xy = index_to_xy(goals_idx[i], width)
    #     if paths[i] and paths[i][-1] != goal_xy:
    #         paths[i] = []

    return paths

# ═══════════════════════════════════════════════════════════════════════════════
# 主规划器类（与 test.py 接口兼容）
# ═══════════════════════════════════════════════════════════════════════════════

class IntegratedAGVPlanner_LaCAM2:
    """
    Guided LaCAM2 规划器适配器。

    与 test.py 中其他规划器接口兼容：
      - 构造：planner = IntegratedAGVPlanner_LaCAM2(
                  grid, width, height, shelf_map,
                  timeout_ms=60000, guid_t_ms=30000, verbose=0)
      - 调用：result = planner.batch_plan(parsed_tasks=waypoints_map)
              result: {agv_id: [(x,y), ...]}  完整两阶段路径

    两阶段策略：
      Phase 1：所有 AGV 同时从 agv_position → source（无冲突）
      Phase 2：所有 AGV 同时从 source → destination（无冲突）
      最终路径 = phase1 + phase2[1:]（去重连接点）

    若某一阶段求解失败（超时或无解），该组所有 AGV 的路径返回空列表。
    """

    def __init__(
        self,
        grid=None,                  # 保留参数，与其他规划器签名一致（不使用）
        width: int = 20,
        height: int = 20,
        shelf_map: Optional[Dict] = None,
        timeout_ms: int = 60000,
        guid_t_ms: int = 30000,
        verbose: int = 0,
        # 以下参数保持与其他规划器工厂函数签名一致（忽略）
        llm_deployer=None,
        api_deployer=None,
        agv_info=None,
    ):
        self.width = width
        self.height = height
        self.shelf_map = shelf_map or {}
        self.timeout_ms = timeout_ms
        self.guid_t_ms = guid_t_ms
        self.verbose = verbose

        # 生成临时地图文件（整个规划器生命周期内复用）
        self._map_file = build_map_file(width, height, self.shelf_map)
        self._rng = random.Random(42)

    def __del__(self):
        # 清理临时文件
        try:
            if hasattr(self, "_map_file") and os.path.exists(self._map_file):
                os.remove(self._map_file)
        except Exception:
            pass

    def batch_plan(
        self,
        parsed_tasks: Dict[str, Dict],
    ) -> Dict[str, List[Tuple[int, int]]]:
        """
        输入：waypoints_map = {
            agv_id: {
                "agv_position": [x, y],
                "source":       [x, y],
                "destination":  [x, y],
                ...
            }, ...
        }

        输出：{agv_id: [(x0,y0), (x1,y1), ...]}
              完整路径 agv_position → source → destination
              坐标为 (x, y) 元组，与 test.py 中的 count_turns/count_wait_steps 一致
        """
        agv_ids   = list(parsed_tasks.keys())
        N         = len(agv_ids)

        if N == 0:
            return {}

        # 提取三个关键点（统一转为 tuple）
        pos_list  = [tuple(parsed_tasks[aid]["agv_position"]) for aid in agv_ids]
        src_list  = [tuple(parsed_tasks[aid]["source"])       for aid in agv_ids]
        dst_list  = [tuple(parsed_tasks[aid]["destination"])  for aid in agv_ids]

        # ── 阶段一：agv_position → source ──────────────────────────────────
        if self.verbose >= 1:
            print(f"[LaCAM2] Phase 1: {N} agents, agv_position → source")

        # 若某 agent 起点==终点，LaCAM2 也能处理（原地停留 1 步）
        phase1 = solve_phase(
            map_file   = self._map_file,
            width      = self.width,
            starts_xy  = pos_list,
            goals_xy   = src_list,
            timeout_ms = self.timeout_ms,
            guid_t_ms  = self.guid_t_ms,
            rng        = self._rng,
            verbose    = self.verbose,
            disappear_on_goal=True,
        )

        if phase1 is None:
            print(f"[LaCAM2] Phase 1 failed completely.")
            return {aid: [] for aid in agv_ids}
        # 过滤 Phase 1 成功的 AGV（路径终点 == source）
        p1_success = [i for i in range(N) if phase1[i] and phase1[i][-1] == src_list[i]]
        if not p1_success:
            print("[LaCAM2] Phase 1: no agent reached source.")
            return {aid: [] for aid in agv_ids}
        if self.verbose >= 1:
            print(f"[LaCAM2] Phase 1: {len(p1_success)}/{N} agents succeeded.")

        # ── 阶段二：source → destination ───────────────────────────────────
        # Phase 2 的起点是 Phase 1 路径末尾的实际位置（= source，LaCAM2 保证到达目标）
        # 只遍历成功的索引 i，确保 phase1[i] 是有效且完整的路径
        phase2_starts = [phase1[i][-1] for i in p1_success]

        if self.verbose >= 1:
            print(f"[LaCAM2] Phase 2: {N} agents, source → destination")

        phase2 = solve_phase(
            map_file   = self._map_file,
            width      = self.width,
            starts_xy  = phase2_starts,
            goals_xy = [dst_list[i] for i in p1_success],
            timeout_ms = self.timeout_ms,
            guid_t_ms  = self.guid_t_ms,
            rng        = self._rng,
            verbose    = self.verbose,
            disappear_on_goal=True,
        )

        if phase2 is None:
            print(f"[LaCAM2] Phase 2 failed completely.")
            return {aid: [] for aid in agv_ids}

        # ── 拼接路径 ──
        # 只对 Phase 2 中路径终点 == destination 的 AGV 算成功
        result = {}
        p2_success_count = 0
        for sub_i, i in enumerate(p1_success):
            aid = agv_ids[i]
            p2 = phase2[sub_i]
            if not p2:
                result[aid] = []
                if self.verbose >= 1:
                    print(f"[LaCAM2] {aid}: Phase2 ❌ p2 路径为空")
                continue
            if p2[-1] == dst_list[i]:
                result[aid] = phase1[i] + p2[1:]
                p2_success_count += 1
                if self.verbose >= 1:
                    print(f"[LaCAM2] {aid}: Phase2 ✅ dst={dst_list[i]}, total_steps={len(result[aid])}")
            else:
                result[aid] = []
                if self.verbose >= 1:
                    print(f"[LaCAM2] {aid}: Phase2 ❌ dst={dst_list[i]}, actual_end={p2[-1]}")

        # Phase 1 就失败的 AGV 也返回空
        for i in range(N):
            if i not in p1_success:
                result[agv_ids[i]] = []
                if self.verbose >= 1:
                    print(f"[LaCAM2] {agv_ids[i]}: Phase1 ❌ (never reached source)")

        if self.verbose >= 1:
            print(f"[LaCAM2] 最终成功: {p2_success_count}/{N} agents")

        return result


# ═══════════════════════════════════════════════════════════════════════════════
# test.py 用的工厂函数包装（与其他 planner_classes lambda 写法兼容）
# ═══════════════════════════════════════════════════════════════════════════════

def make_lacam2_planner(width: int, height: int, shelf_map: Dict,
                        timeout_ms: int = 60000, guid_t_ms: int = 30000,
                        verbose: int = 0):
    """
    返回一个工厂 lambda，可直接放入 planner_classes 字典。

    用法：
        planner_classes["LaCAM2_Guided"] = make_lacam2_planner(
            width=WIDTH, height=HEIGHT, shelf_map=shelf_map)

    或者直接实例化：
        planner = IntegratedAGVPlanner_LaCAM2(
            width=WIDTH, height=HEIGHT, shelf_map=shelf_map)
        result = planner.batch_plan(waypoints_map)
    """
    def factory(grid=None, llm_deployer=None, api_deployer=None, agv_info=None):
        return IntegratedAGVPlanner_LaCAM2(
            grid=grid,
            width=width,
            height=height,
            shelf_map=shelf_map,
            timeout_ms=timeout_ms,
            guid_t_ms=guid_t_ms,
            verbose=verbose,
            llm_deployer=llm_deployer,
            api_deployer=api_deployer,
            agv_info=agv_info,
        )
    return factory
