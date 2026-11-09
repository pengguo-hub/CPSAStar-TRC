"""
mapf_planner.py
===============
对应 C++ guided-pibt/src/MAPFPlanner.cpp + MAPFPlanner.h

严格按照 C++ 源码复现，修复了以下关键错误：

[BUG1] 优先级初始化错误
  原：priorities = [N, N-1, ..., 1]（整数，无分数部分）
  C++：随机打乱 ids，然后 p[ids[i]] = (ids.size()-i) / (ids.size()+1)
  → 优先级是 (0,1) 之间的浮点数，保证初始时无重复
  → task_change 时 p[i] = p_copy[i]（重置回初始值），否则 p[i] += 1

[BUG2] task_change 检测时机错误
  原：在 _step_update() 里检测
  C++：在 plan() 开头的 per-agent 初始化循环里检测（for i in range(N) 那段）
  → task_change[i] = (goal_locations[i][0] != trajLNS.tasks[i])
  → 然后 trajLNS.tasks[i] = goal_locations[i][0].first
  → 如果 task_change[i]: p[i] = p_copy[i]，否则 p[i] += 1
  这保证了优先级更新和任务变化检测在同一循环，在 PIBT 之前完成。

[BUG3] occupied/decided 状态管理缺失
  原：每步重建 occupied_now / occupied_next，不持久化 decided 状态
  C++：decided[i] 跨 timestep 持久化（DCR {loc, DONE::NOT_DONE/DONE}），
       表示 agent 上一步决定移动到某位置但还未实际到达。
       这是 PIBT 在 MAPFT 模型下的核心：agent 可能需要多步才能完成"转向+前进"。
  → 修复：tracked_next[i] 跨步持久化，仅在 agent 实际到达 decided 位置时清除

[BUG4] PIBT 邻居排序 tie-breaking 错误
  原：随机 tie-breaking
  C++：successors 按 heuristic 升序排序，同值时随机（rand()%2==1）
  → 已基本正确，但原代码先排序再合并 wait，应该 wait 也参与排序

[BUG5] update_traj 的起点错误（最关键！）
  原：update_traj 用 tf_env.curr_states[i].location 作为起点（即当前位置）
  C++：同样用 curr_states[i].location 作为起点 ✓
  但原代码在 _step_update 里已经 sync 过 tf_env，所以这点是对的。

[BUG6] destory_improve 调用时序错误
  原：先 _step_update()，再 _step_refine()（destroy_improve）
  C++：先检测 task_change + 执行 remove+update_traj，
       然后 init_traj（如果未全部初始化），
       然后 destroy_improve（仅在 init_done=True 时）
  → init_done = (traj_inited == num_of_agents)
  → destroy_improve 只在所有 agent 都有 guide path 后才调用！

[BUG7] traj_inited 计数管理错误
  原：_has_guide[i] 标志与 C++ traj_inited 不完全对应
  C++：traj_inited 是全局计数，init_traj 每次 +1
  → 修复：用 self._lns.traj_inited 统一追踪

[BUG8] Dist2Path 更新遗漏
  C++ 中，对 task_change[i] && updated.find(i)==updated.end() 的 agent
  也要 update_dist_2_path。原代码只对 updated 里的 agent 更新。

算法结构（严格对应 C++ MAPFPlanner::plan()）：
  1. 初始化 heuristics + task_change 检测 + 优先级更新
  2. Updating: task_change agent 的 remove+update_traj（GUIDANCE 且已初始化）
  3. Initialising: init_traj（如果 traj_inited < N）
  4. Refining: destroy_improve（仅 init_done 时）+ 更新 dist2path
  5. PIBT sort + causalPIBT
"""

from __future__ import annotations

import random
import sys
from typing import List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .shared_env import SharedEnv

import importlib
import os
import sys as _sys

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE not in _sys.path:
    pass  # Package imports replace process-wide import-path mutation.


from src.original_paper.experiment.Lifelong.Guide_Paths.traffic_mapf.types import SharedEnvironment as TFSharedEnv, AgentState as TFAgentState, Int4, HeuristicTable, Dist2Path, MAX_TIMESTEP, GUIDANCE_LNS, LNS_GROUP_SIZE
from src.original_paper.experiment.Lifelong.Guide_Paths.traffic_mapf.heuristics import init_heuristic, get_heuristic, init_dist_2_path, get_dist_2_path
from src.original_paper.experiment.Lifelong.Guide_Paths.traffic_mapf.traj_lns import TrajLNS
from src.original_paper.experiment.Lifelong.Guide_Paths.traffic_mapf.flow import init_traj, init_dist_table, destroy_improve, add_traj, remove_traj, update_traj
from src.original_paper.experiment.Lifelong.Guide_Paths.traffic_mapf.utils import get_neighbor_locs


# ===========================================================================
# PIBT 内部状态（对应 C++ decided[i], DCR struct）
# ===========================================================================

class _Agent:
    """PIBT per-agent 状态（跨 timestep 持久化 decided）"""
    __slots__ = ("id", "v_now", "v_next")

    def __init__(self, aid: int):
        self.id = aid
        self.v_now: int = -1
        self.v_next: int = -1   # -1 = 未规划（对应 C++ next_states[i].location == -1）


# ===========================================================================
# MAPFPlanner（严格对应 C++ MAPFPlanner）
# ===========================================================================

class MAPFPlanner:
    """
    对应 C++ class MAPFPlanner

    参数：
      R_init       : 每 timestep 最多 lazy-init 多少条 guide path（RELAX 宏，默认100）
      refine_iters : GUIDANCE_LNS 宏值（>0 表示启用 LNS）
      guidance     : 对应 #define GUIDANCE
      time_limit_s : 每 timestep 的时间预算（秒），传给 destroy_improve
                     C++ 中 plan_time_limit 默认 1 秒，destroy_improve 用 time_limit*0.8
    """

    def __init__(
        self,
        env: "SharedEnv",
        R_init: int = 100,
        refine_iters: int = 10,
        guidance: bool = True,
        time_limit_s: float = 1.0,
    ):
        self.env = env
        self.R_init = R_init          # 对应 C++ RELAX 宏
        self.refine_iters = refine_iters  # 对应 C++ GUIDANCE_LNS 宏
        self.guidance = guidance       # 对应 C++ #define GUIDANCE
        self.time_limit_s = time_limit_s  # 每步时间预算

        N = env.num_of_agents
        M = len(env.map)

        # ---- TFSharedEnv（traffic_mapf 内部使用） ----
        self._tf_env: TFSharedEnv = self._build_tf_env()

        # ---- TrajLNS ----
        self._lns: TrajLNS = TrajLNS(self._tf_env)
        self._lns.init_mem()

        # traffic 约束（-1 = 无约束）
        self._traffic: List[int] = [-1] * M

        # ---- C++ 对应字段 ----
        # p[i]：优先级，初始为随机 (0,1) 浮点（对应 C++ p[ids[i]] = (n-i)/(n+1)）
        self._p: List[float] = [0.0] * N
        self._p_copy: List[float] = [0.0] * N  # 初始优先级副本（task_change 时重置）
        self._init_priorities()

        # task_change[i]：本 timestep 该 agent 目标是否变化
        self._task_change: List[bool] = [False] * N

        # decided[i]：上一步决定的下一位置（跨步持久化）
        # 对应 C++ decided[i] = DCR({loc, DONE::NOT_DONE/DONE})
        # -1 表示未初始化（首步）
        self._decided_loc: List[int] = [-1] * N
        self._decided_done: List[bool] = [True] * N  # True=DONE, False=NOT_DONE

        # PIBT 工作数组（每步重置）
        self._prev_decision: List[int] = [-1] * M   # prev_decision[loc] = agent_id
        self._decision: List[int] = [-1] * M        # decision[loc] = agent_id
        self._occupied: List[bool] = [False] * M    # 对应 C++ occupied[loc]
        self._prev_states: List[int] = [-1] * N     # prev_states[i].location
        self._next_states: List[int] = [-1] * N     # next_states[i].location（-1=未规划）
        self._ids: List[int] = list(range(N))       # 排序后的 agent 顺序

        # 首步标志
        self._initialized: bool = False

    def _init_priorities(self) -> None:
        """
        对应 C++ initialize() 中的优先级初始化：
          std::shuffle(ids.begin(), ids.end(), rng)
          for i in range(n): p[ids[i]] = (n-i)/(n+1)  [浮点]
        """
        N = self.env.num_of_agents
        ids = list(range(N))
        random.shuffle(ids)
        for i, aid in enumerate(ids):
            val = float(N - i) / float(N + 1)
            self._p[aid] = val
            self._p_copy[aid] = val

    def _build_tf_env(self) -> TFSharedEnv:
        tf_env = TFSharedEnv()
        tf_env.rows = self.env.rows
        tf_env.cols = self.env.cols
        tf_env.map = self.env.map
        tf_env.neighbors = self.env.neighbors
        tf_env.num_of_agents = self.env.num_of_agents
        tf_env.curr_states = []
        for i in range(self.env.num_of_agents):
            st = TFAgentState()
            st.location = self.env.curr_states[i].location
            st.orientation = self.env.curr_states[i].orientation
            st.timestep = self.env.curr_states[i].timestep
            tf_env.curr_states.append(st)
        return tf_env

    # ------------------------------------------------------------------
    # 主接口：compute_actions（对应 C++ plan()）
    # ------------------------------------------------------------------

    def compute_actions(self, timestep: int) -> List[int]:
        """
        对应 C++ void MAPFPlanner::plan(int time_limit, vector<Action>& actions)

        完整实现 Algorithm 3 GuidedPlanStep，严格按照 C++ 执行顺序：
          1. 清空 prev_decision / occupied
          2. Per-agent 初始化循环：heuristic init + task_change 检测 + 优先级更新
             + decided 状态维护 + prev_states 记录
          3. [GUIDANCE] Updating: task_change agent 重新规划 guide path
          4. [GUIDANCE] Initialising: init_traj（if traj_inited < N）
          5. [GUIDANCE_LNS] Refining: destroy_improve（只在 init_done 后）
          6. [GUIDANCE] Dist2path 更新
          7. 按优先级排序 ids
          8. causalPIBT for each undecided agent
          9. 提取 actions
        """
        N = self.env.num_of_agents
        M = len(self.env.map)

        # 同步 tf_env.curr_states
        self._sync_tf_env_states()

        # ----------------------------------------------------------------
        # Step 0: 清空每步工作数组（对应 C++ plan() 开头）
        # ----------------------------------------------------------------
        for loc in range(M):
            self._prev_decision[loc] = -1
            self._occupied[loc] = False
        # decision 数组在 PIBT 过程中维护，最终每个 entry 都会被清除

        # ----------------------------------------------------------------
        # Step 1: Per-agent 初始化循环（严格对应 C++ for(int i=0;i<N;i++) 块）
        # ----------------------------------------------------------------
        count = 0
        init_done_before = (self._lns.traj_inited >= N)

        for i in range(N):
            # 懒惰初始化 heuristic table（无论是否 GUIDANCE 都需要）
            # 对应 C++ 的 if(traj_inited < N && count < RELAX) || (traj_inited >= N)
            if (self._lns.traj_inited < N and count < self.R_init) or (self._lns.traj_inited >= N):
                gl = self.env.goal_locations[i]
                if gl:
                    for goal_entry in gl:
                        goal_loc = goal_entry[0]
                        if self._lns.heuristics[goal_loc].empty():
                            init_heuristic(self._lns.heuristics[goal_loc], self._tf_env, goal_loc)
                            count += 1

            # task_change 检测（对应 C++ task_change[i] = ...）
            gl = self.env.goal_locations[i]
            if gl:
                current_goal = gl[0][0]
            else:
                current_goal = -1

            # 注意：C++ 检测的是 goal_locations[i].front().first != trajLNS.tasks[i]
            old_task = self._lns.tasks[i]
            self._task_change[i] = (current_goal != old_task) and (current_goal >= 0)
            if current_goal >= 0:
                self._lns.tasks[i] = current_goal

            # prev_states 记录（对应 C++ prev_states[i] = env->curr_states[i]）
            self._prev_states[i] = self._tf_env.curr_states[i].location

            # next_states 重置（-1 = 未规划）
            self._next_states[i] = -1

            # prev_decision 记录（对应 C++ prev_decision[curr_states[i].location] = i）
            self._prev_decision[self._prev_states[i]] = i

            # decided 首次初始化（对应 C++ if(decided[i].loc == -1)）
            if self._decided_loc[i] == -1:
                self._decided_loc[i] = self._prev_states[i]
                assert self._decided_done[i]  # 首次应为 DONE

            # 检查 agent 是否已到达上次 decided 的位置（对应 C++ if(prev==decided.loc) DONE）
            if self._prev_states[i] == self._decided_loc[i]:
                self._decided_done[i] = True

            # 标记 occupied（对应 C++ if decided.state==NOT_DONE: occupied[decided.loc]=occupied[prev]=true）
            if not self._decided_done[i]:
                self._occupied[self._decided_loc[i]] = True
                self._occupied[self._prev_states[i]] = True

            # 优先级更新（对应 C++ task_change ? p[i]=p_copy[i] : p[i]+=1）
            if self._task_change[i]:
                self._p[i] = self._p_copy[i]
            else:
                self._p[i] += 1.0

        # ----------------------------------------------------------------
        # Step 2-6: GUIDANCE 分支（对应 C++ #ifdef GUIDANCE 块）
        # ----------------------------------------------------------------
        if self.guidance:
            import time as _time
            step_start = _time.perf_counter()

            # --- Updating: 对 task_change 且已有轨迹的 agent 重新规划 ---
            # 对应 C++:
            #   for i in range(N):
            #     if task_change[i] && !trajLNS.trajs[i].empty():
            #       remove_traj(trajLNS, i)
            #       update_traj(trajLNS, i, traffic)
            for i in range(N):
                if self._task_change[i] and self._lns.trajs[i]:
                    remove_traj(self._lns, i)
                    update_traj(self._lns, i, self._traffic)

            # --- Initialising: init_traj（if traj_inited < N）---
            # 对应 C++: if(trajLNS.traj_inited < N) init_traj(trajLNS, traffic, RELAX)
            if self._lns.traj_inited < N:
                init_traj(self._lns, self._traffic, self.R_init)

            # init_done：所有 agent 都已有 guide path
            init_done = (self._lns.traj_inited >= N)

            # --- Refining: destroy_improve（仅 init_done 后）---
            # 对应 C++: #ifdef GUIDANCE_LNS if(init_done) destory_improve(trajLNS,traffic,updated,GUIDANCE_LNS,time_limit*0.8)
            updated: Set[int] = set()
            if self.refine_iters > 0 and init_done:
                destroy_improve(
                    self._lns,
                    self._traffic,
                    updated,
                    max_ite=self.refine_iters,
                    time_limit=self.time_limit_s * 0.8,  # 对应 C++ time_limit * 0.8
                )

            # --- Dist2Path 更新 ---
            # 对应 C++ #ifndef FLOW_GUIDANCE 分支：
            #   1. 如果 dist2path_inited < N: init_dist_table(trajLNS, traffic, RELAX)
            #   2. 对 task_change[i] && updated.find(i)==updated.end() 的已初始化 agent 更新
            if self._lns.dist2path_inited < N:
                init_dist_table(self._lns, self._traffic, self.R_init)

            # task_change 且未被 LNS 更新过的 agent → 重建 dist2path
            for i in range(N):
                if not self._task_change[i]:
                    continue
                if i in updated:
                    continue
                if not self._lns.traj_dists[i].empty() and self._lns.trajs[i]:
                    self._lns.traj_dists[i] = Dist2Path()
                    init_dist_2_path(
                        self._lns.traj_dists[i], self._tf_env,
                        self._lns.trajs[i], self._traffic,
                    )

            # LNS 改动过的 agent → 重建 dist2path
            for i in updated:
                if self._lns.trajs[i]:
                    self._lns.traj_dists[i] = Dist2Path()
                    init_dist_2_path(
                        self._lns.traj_dists[i], self._tf_env,
                        self._lns.trajs[i], self._traffic,
                    )

        # ----------------------------------------------------------------
        # Step 7: 按优先级排序（对应 C++ std::sort(ids...) by p descending）
        # ----------------------------------------------------------------
        self._ids.sort(key=lambda a: self._p[a], reverse=True)

        # ----------------------------------------------------------------
        # Step 8: causalPIBT（对应 C++ for i in ids: if NOT_DONE skip; causalPIBT(i,-1,...)）
        # ----------------------------------------------------------------
        for i in self._ids:
            # 跳过上一步 NOT_DONE 的 agent（还在路上）
            if not self._decided_done[i]:
                continue
            # 跳过已在本步规划过的 agent
            if self._next_states[i] != -1:
                continue
            self._causal_pibt(i, -1)

        # ----------------------------------------------------------------
        # Step 9: 提取 actions + 更新 decided 状态
        # 对应 C++:
        #   for id in ids:
        #     if next_states[id].location != -1: decision[next_states[id].location] = -1
        #     if next_states[id].location >= 0: decided[id] = DCR({next_loc, NOT_DONE})
        #     actions[id] = getAction(prev_states[id], decided[id].loc, env)
        # ----------------------------------------------------------------
        result_locs: List[int] = [-1] * N

        for i in self._ids:
            # 清除 decision 表（对应 C++ decision[next.loc]=-1）
            if self._next_states[i] != -1:
                self._decision[self._next_states[i]] = -1

            # 更新 decided（对应 C++ decided[id]=DCR({next_loc, NOT_DONE})）
            if self._next_states[i] >= 0:
                self._decided_loc[i] = self._next_states[i]
                self._decided_done[i] = False

            # 获取目标位置（decided.loc）
            result_locs[i] = self._decided_loc[i]

        # 验证 decision 数组已清空（debug）
        # assert all(d == -1 for d in self._decision)

        return result_locs

    # ------------------------------------------------------------------
    # causalPIBT（严格对应 C++ pibt.cpp causalPIBT()）
    # ------------------------------------------------------------------

    def _causal_pibt(self, curr_id: int, higher_id: int) -> bool:
        """
        对应 C++ bool causalPIBT(curr_id, higher_id, prev_states, next_states,
                                   prev_decision, decision, occupied, traffic, lns)

        核心逻辑：
          1. 枚举 curr_id 的所有邻居（4方向 + wait）
          2. 过滤 traffic rule 违规的邻居
          3. 计算每个邻居的 guide heuristic（dist2path 或 BFS）
          4. 按 heuristic 升序排序（用 quickSort + 随机 tie-break）
          5. 遍历排序后的候选，找到一个合法的下一步：
             - 未被 occupied 且未被 decision 占用
             - 不会制造与 higher_id 的交换冲突
             - 如果该位置有 lower_id，递归为 lower_id 规划
          6. 失败则原地等待
        """
        prev_loc = self._prev_states[curr_id]
        cols = self.env.cols

        # 生成邻居列表（4方向）
        neighbor_locs = list(self.env.neighbors[prev_loc])

        # 过滤 traffic rule 违规（对应 C++ traffic check）
        valid_neighbors = []
        for nb in neighbor_locs:
            if self._traffic[nb] != -1:
                # traffic[nb] 方向对应的位置 = candidates[traffic[nb]]
                candidates = [nb + 1, nb + cols, nb - 1, nb - cols]
                td = self._traffic[nb]
                if 0 <= td < 4:
                    if prev_loc == candidates[td]:
                        continue  # 违反 traffic rule，跳过
            valid_neighbors.append(nb)

        # 构建 successors（loc, heuristic）包含 wait
        successors: List[Tuple[int, int]] = []
        for nb in valid_neighbors:
            h = self._get_guide_h(curr_id, nb)
            successors.append((nb, h))
        # wait：原地
        h_wait = self._get_guide_h(curr_id, prev_loc)
        successors.append((prev_loc, h_wait))

        # 按 heuristic 升序排序，同值随机 tie-break（对应 C++ quickSort + rand()%2）
        successors.sort(key=lambda x: (x[1], random.random()))

        # 遍历候选
        for (next_loc, _h) in successors:
            # occupied check（对应 C++ if(occupied[next.location]) continue）
            if self._occupied[next_loc]:
                continue

            # decision check（对应 C++ if(decision[next.location] != -1) continue）
            if self._decision[next_loc] != -1:
                continue

            # higher_id 交换冲突 check
            # 对应 C++ if(higher_id != -1 && prev_decision[next.location] == higher_id) continue
            if higher_id != -1 and self._prev_decision[next_loc] == higher_id:
                continue

            # 预订 next_loc
            self._next_states[curr_id] = next_loc
            self._decision[next_loc] = curr_id

            # 优先级继承：如果 next_loc 上有 lower_id 还未规划，递归
            # 对应 C++: if(prev_decision[next.loc]!=-1 && next_states[lower].loc==-1)
            #               causalPIBT(lower_id, curr_id, ...)
            lower_id = self._prev_decision[next_loc]
            if lower_id != -1 and self._next_states[lower_id] == -1:
                if not self._causal_pibt(lower_id, curr_id):
                    # lower_id 规划失败，放弃 next_loc
                    self._decision[next_loc] = -1
                    self._next_states[curr_id] = -1
                    continue

            return True

        # 所有候选失败：原地等待
        # 对应 C++: next_states[curr_id] = State(prev_loc,-1,-1); decision[prev_loc]=curr_id
        self._next_states[curr_id] = prev_loc
        self._decision[prev_loc] = curr_id
        return False

    # ------------------------------------------------------------------
    # Guide Heuristic（对应 C++ PIBT 中的 heuristic 查询）
    # ------------------------------------------------------------------

    def _get_guide_h(self, agent_id: int, loc: int) -> int:
        """
        对应 C++ pibt.cpp 中的 heuristic 查询逻辑：
          1. FLOW_GUIDANCE: flow_heuristic（本实现不用）
          2. traj_dists 非空：get_dist_2_path（d_p + d_g）← 主要路径
          3. heuristics[task] 非空：get_heuristic（纯 BFS）
          4. 否则：Manhattan distance
        """
        # 主路径：dist2path（d_p + d_g）
        dp = self._lns.traj_dists[agent_id]
        if not dp.empty():
            val = get_dist_2_path(dp, self._tf_env, self._traffic, loc)
            if val < MAX_TIMESTEP:
                return val

        # 回退：BFS 距离
        task = self._lns.tasks[agent_id]
        if task >= 0 and not self._lns.heuristics[task].empty():
            return get_heuristic(self._lns.heuristics[task], self._tf_env, self._traffic, self._lns.flow, loc)

        # 最终回退：Manhattan
        if task >= 0:
            r1, c1 = divmod(loc, self.env.cols)
            r2, c2 = divmod(task, self.env.cols)
            return abs(r1 - r2) + abs(c1 - c2)

        return 0

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _get_agent_goal(self, i: int) -> int:
        gl = self.env.goal_locations[i]
        if not gl:
            return -1
        return gl[0][0]

    def _sync_tf_env_states(self) -> None:
        for i in range(self.env.num_of_agents):
            self._tf_env.curr_states[i].location = self.env.curr_states[i].location

    # ------------------------------------------------------------------
    # 对外：goal_reached 通知（由 CompetitionSystem 调用）
    # ------------------------------------------------------------------

    def on_goal_reached(self, agent_id: int) -> None:
        """
        当 agent 到达当前 goal 时调用。
        对应 C++ 中 env->goal_locations 被 CompetitionSystem 更新后，
        下一步 plan() 检测到 task_change 并执行 remove+update_traj。

        在 Python 版本中，我们在此预清理旧 guide path，
        以便 task_change 时 trajs[i] 已为空（触发 init_traj 而非 update_traj）。
        
        注意：C++ 中不需要这个钩子，因为 task_change 检测是在 plan() 内部做的。
        但我们保留此方法以便 CompetitionSystem 调用，实际上可以什么都不做——
        task_change 会在下一步 compute_actions 里被自动检测到。
        """
        # 不需要在这里 remove_traj，因为 compute_actions 里的 Updating 步骤
        # 会在检测到 task_change 时自动执行 remove_traj + update_traj
        # 这里只重置 _lns.tasks[i] 以强制触发 task_change 检测
        self._lns.tasks[agent_id] = -1
