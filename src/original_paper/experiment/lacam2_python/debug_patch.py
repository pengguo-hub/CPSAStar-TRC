"""
debug_patch.py
==============
调试补丁：在 warehouse_adapter.py 的 solve_phase() 里加入详细诊断信息。
将此文件放在和 warehouse_adapter.py 同目录，然后在 test.py 里把
    from warehouse_adapter import make_lacam2_planner
改为
    from debug_patch import make_lacam2_planner_debug as make_lacam2_planner
即可看到完整诊断。
"""

import sys, os, time, random
pass  # Package imports replace process-wide import-path mutation.

from .lacam2 import Instance, Deadline, solve, Objective, is_feasible_solution
from .warehouse_adapter import build_map_file, xy_to_index, index_to_xy, IntegratedAGVPlanner_LaCAM2


def solve_phase_debug(
    map_file, width,
    starts_xy, goals_xy,
    timeout_ms=60000,
    guid_t_ms=30000,
    rng=None,
    verbose=0,
    phase_name="",
):
    """带完整诊断信息的 solve_phase"""
    if rng is None:
        rng = random.Random(0)

    N = len(starts_xy)
    print(f"\n[DEBUG] ===== {phase_name} =====")
    print(f"[DEBUG] N agents = {N}")
    print(f"[DEBUG] timeout_ms = {timeout_ms}, guid_t_ms = {guid_t_ms}")

    # ── 1. 检查起点/终点是否在地图范围内 ────────────────────────────────
    for i, (x, y) in enumerate(starts_xy):
        if not (0 <= x < width):
            print(f"[DEBUG] ❌ Agent {i} start x={x} 越界 (width={width})")
        if not (0 <= y):
            print(f"[DEBUG] ❌ Agent {i} start y={y} 越界")
    for i, (x, y) in enumerate(goals_xy):
        if not (0 <= x < width):
            print(f"[DEBUG] ❌ Agent {i} goal x={x} 越界 (width={width})")

    # ── 2. 检查起点/终点是否是障碍物（在图中存在） ──────────────────────
    starts_idx = [xy_to_index(x, y, width) for x, y in starts_xy]
    goals_idx  = [xy_to_index(x, y, width) for x, y in goals_xy]

    ins = Instance.from_indexes(map_file, starts_idx, goals_idx)
    print(f"[DEBUG] Graph size (free vertices) = {ins.G.size()}")
    print(f"[DEBUG] Total map cells = {width * (ins.G.V_size if hasattr(ins.G, 'V_size') else '?')}")

    for i in range(N):
        s = ins.starts[i]
        g = ins.goals[i]
        if s is None:
            print(f"[DEBUG] ❌ Agent {i} start {starts_xy[i]} → None (障碍物或越界!)")
        else:
            print(f"[DEBUG]    Agent {i} start {starts_xy[i]} → vertex id={s.id}, index={s.index}, neighbors={len(s.neighbor)}")
        if g is None:
            print(f"[DEBUG] ❌ Agent {i} goal  {goals_xy[i]} → None (障碍物或越界!)")
        else:
            print(f"[DEBUG]    Agent {i} goal  {goals_xy[i]} → vertex id={g.id}, index={g.index}, neighbors={len(g.neighbor)}")

    # ── 3. 检查起点==终点的 agent（合法但可能引发问题） ──────────────────
    same_count = sum(1 for i in range(N) if starts_xy[i] == goals_xy[i])
    if same_count > 0:
        print(f"[DEBUG] ⚠️  {same_count} agents 起点==终点（原地不动，合法但占用位置）")
        for i in range(N):
            if starts_xy[i] == goals_xy[i]:
                print(f"[DEBUG]    Agent {i}: start==goal={starts_xy[i]}")

    # ── 4. 检查起点重复（两个 agent 在同一格） ───────────────────────────
    from collections import Counter
    start_counter = Counter(starts_xy)
    dup_starts = {pos: cnt for pos, cnt in start_counter.items() if cnt > 1}
    if dup_starts:
        print(f"[DEBUG] ❌ 起点重复: {dup_starts}")
    else:
        print(f"[DEBUG] ✅ 起点无重复")

    goal_counter = Counter(goals_xy)
    dup_goals = {pos: cnt for pos, cnt in goal_counter.items() if cnt > 1}
    if dup_goals:
        print(f"[DEBUG] ⚠️  终点重复（合法但可能导致搜索困难）: {dup_goals}")

    # ── 5. 执行求解，记录详细时间 ─────────────────────────────────────────
    print(f"[DEBUG] 开始构建 Planner (setup_guidance 在此执行)...")
    t0 = time.perf_counter()

    deadline = Deadline(timeout_ms)

    solution, info = solve(
        ins,
        verbose=1,           # 强制 verbose=1 以看到 timeout/no_solution 日志
        deadline=deadline,
        rng=rng,
        objective=Objective.OBJ_NONE,
        guid_t_ms=guid_t_ms,
    )

    elapsed = time.perf_counter() - t0
    print(f"[DEBUG] solve() 耗时: {elapsed:.2f}s")
    print(f"[DEBUG] Deadline 剩余: {timeout_ms - deadline.elapsed_ms():.0f}ms")
    print(f"[DEBUG] solve() info:\n{info}")

    if solution is None or len(solution) == 0:
        print(f"[DEBUG] ❌ {phase_name} 无解！")
        print(f"[DEBUG]    → 原因可能是：超时 / 无路径 / 起点重复")
        return None

    print(f"[DEBUG] ✅ {phase_name} 成功，makespan={len(solution)-1} 步")

    # 验证解的合法性
    feasible = is_feasible_solution(ins, solution, verbose=0)
    print(f"[DEBUG] is_feasible_solution = {feasible}")

    # 转换为 xy 路径
    paths = {i: [] for i in range(N)}
    for config in solution:
        for i, vertex in enumerate(config):
            paths[i].append(index_to_xy(vertex.index, width))
    return paths


class IntegratedAGVPlanner_LaCAM2_Debug(IntegratedAGVPlanner_LaCAM2):
    """带调试输出的规划器，继承自原版"""

    def batch_plan(self, parsed_tasks):
        agv_ids  = list(parsed_tasks.keys())
        N        = len(agv_ids)

        if N == 0:
            return {}

        pos_list = [tuple(parsed_tasks[aid]["agv_position"]) for aid in agv_ids]
        src_list = [tuple(parsed_tasks[aid]["source"])       for aid in agv_ids]
        dst_list = [tuple(parsed_tasks[aid]["destination"])  for aid in agv_ids]

        print(f"\n[DEBUG] ============ batch_plan: {N} agents ============")
        print(f"[DEBUG] map_file = {self._map_file}")
        print(f"[DEBUG] width={self.width}, height={self.height}")
        print(f"[DEBUG] timeout_ms={self.timeout_ms}, guid_t_ms={self.guid_t_ms}")

        # 打印所有任务
        for i, aid in enumerate(agv_ids):
            print(f"[DEBUG] {aid}: pos={pos_list[i]} → src={src_list[i]} → dst={dst_list[i]}")

        # ── Phase 1 ──────────────────────────────────────────────────────
        phase1 = solve_phase_debug(
            map_file   = self._map_file,
            width      = self.width,
            starts_xy  = pos_list,
            goals_xy   = src_list,
            timeout_ms = self.timeout_ms,
            guid_t_ms  = self.guid_t_ms,
            rng        = self._rng,
            verbose    = 1,
            phase_name = "Phase 1: agv_position → source",
        )

        if phase1 is None:
            print("[DEBUG] Phase 1 失败，返回空路径")
            return {aid: [] for aid in agv_ids}

        # Phase 2 的实际起点（= phase1 路径末尾）
        phase2_starts = [phase1[i][-1] for i in range(N)]
        print(f"\n[DEBUG] Phase 2 实际起点（应等于 source）:")
        for i, aid in enumerate(agv_ids):
            expected = src_list[i]
            actual   = phase2_starts[i]
            match = "✅" if actual == expected else "❌"
            print(f"[DEBUG]   {aid}: 期望={expected}, 实际={actual} {match}")

        # ── Phase 2 ──────────────────────────────────────────────────────
        phase2 = solve_phase_debug(
            map_file   = self._map_file,
            width      = self.width,
            starts_xy  = phase2_starts,
            goals_xy   = dst_list,
            timeout_ms = self.timeout_ms,
            guid_t_ms  = self.guid_t_ms,
            rng        = self._rng,
            verbose    = 1,
            phase_name = "Phase 2: source → destination",
        )

        if phase2 is None:
            print("[DEBUG] Phase 2 失败，返回空路径")
            return {aid: [] for aid in agv_ids}

        # ── 拼接 ──────────────────────────────────────────────────────────
        result = {}
        for i, aid in enumerate(agv_ids):
            full_path = phase1[i] + phase2[i][1:]
            result[aid] = full_path
            print(f"[DEBUG] {aid}: phase1={len(phase1[i])}步 + phase2={len(phase2[i])}步 → total={len(full_path)}步")

        return result


def make_lacam2_planner_debug(width, height, shelf_map,
                               timeout_ms=60000, guid_t_ms=30000, verbose=0):
    """调试版工厂函数，替换原版 make_lacam2_planner"""
    def factory(grid=None, llm_deployer=None, api_deployer=None, agv_info=None):
        p = IntegratedAGVPlanner_LaCAM2_Debug(
            width=width, height=height, shelf_map=shelf_map,
            timeout_ms=timeout_ms, guid_t_ms=guid_t_ms, verbose=verbose,
        )
        return p
    return factory
