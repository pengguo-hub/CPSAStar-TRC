"""
cmpp_adapter.py
将上层任务（waypoints 列表）转换为 CMPP 问题实例并求解，返回稀疏路径或网格路径。

论文 Section VI.C Integration of CMPP with PIBT：
  "A-CMTS computes CMPP solutions πi=(πi[1],...,πi[Li]) for each agent i on graph G.
   Each agent's next waypoint on the grid G* is determined from this path:
   if Li≥3, the agent is directed to the representative cell of πi[2] via the
   injective map g:V→V*; otherwise, it proceeds directly to its goal gi."
"""

from collections import defaultdict
from .cmpp_graph import CMPPGraph
from .cmpp_low_level import CMPPLowLevelPlanner
from .cmpp_acmts import CMPPA_CMTS


class Agent:
    """CMPP agent 抽象：一段 start→goal 的稀疏图路径规划任务"""
    __slots__ = ('id', 'start', 'goal', 'orig_id', 'seg_idx')

    def __init__(self, id, start, goal, orig_id, seg_idx):
        self.id = id
        self.start = start
        self.goal = goal
        self.orig_id = orig_id
        self.seg_idx = seg_idx

    def __repr__(self):
        return f"Agent({self.id}, {self.start}->{self.goal})"


def plan_with_cmpp(parsed_tasks, grid, delta=1.0, max_time_per_plan=1.0,
                   omega=1.3, initial_paths=None, graph_step=2,
                   graph=None, return_sparse=False):
    """
    对一批 AGV 任务调用 A-CMTS 求解 CMPP，返回路径字典。

    Parameters
    ----------
    parsed_tasks      : dict  {agv_id: {'waypoints': [(x,y),...]}}
                         waypoints 是稀疏顶点序列（从 LifelongPlanner 传入时已映射）
    grid              : GridMap
    delta             : float  保留接口
    max_time_per_plan : float  A-CMTS 时间上限（秒）
    omega             : float  次优因子
    initial_paths     : dict   {seg_id: [sparse_vertices]}  热启动路径
    graph_step        : int    稀疏图步长（graph=None 时使用）
    graph             : CMPPGraph  若已构建则直接传入（推荐，避免重复构建）
    return_sparse     : bool   True→返回稀疏顶点序列，False→映射回网格坐标

    Returns
    -------
    dict {agv_id: [vertices]}
    """
    # ── 1. 提取障碍物 ────────────────────────────────────────────────────
    obstacles = set()
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.grid[y][x] == 1:
                obstacles.add((x, y))

    # ── 2. 构建稀疏图（若未传入）──────────────────────────────────────────
    if graph is None:
        graph = CMPPGraph.from_grid(grid.width, grid.height, obstacles,
                                    step=graph_step)

    # ── 3. 构建 Agent 列表（每段 waypoints[i]→waypoints[i+1] 一个 agent）──
    agents = []
    agent_initial_paths = {}   # {seg_id: [sparse_vertices]}

    for agv_id, info in parsed_tasks.items():
        waypoints = info['waypoints']   # 已经是稀疏顶点

        for i in range(len(waypoints) - 1):
            seg_id = f"{agv_id}_seg{i}"
            start_v = waypoints[i]
            goal_v = waypoints[i + 1]

            # 跳过起终点相同的段
            if start_v == goal_v:
                continue

            # 确认顶点在图中
            if start_v not in graph.adj or goal_v not in graph.adj:
                continue

            ag = Agent(
                id=seg_id,
                start=start_v,
                goal=goal_v,
                orig_id=agv_id,
                seg_idx=i,
            )
            agents.append(ag)

            # 热启动路径
            if initial_paths and seg_id in initial_paths:
                ip = initial_paths[seg_id]
                # 验证：路径在图中且起终点匹配
                if (ip and ip[0] == start_v and ip[-1] == goal_v
                        and all(v in graph.adj for v in ip)):
                    agent_initial_paths[seg_id] = ip

    if not agents:
        return {}

    # ── 4. 低层规划器 ────────────────────────────────────────────────────
    low_planner = CMPPLowLevelPlanner(graph, delta=delta)

    # ── 5. 运行 A-CMTS ───────────────────────────────────────────────────
    acmts = CMPPA_CMTS(
        graph=graph,
        agents=agents,
        low_level=low_planner,
        omega=omega,
        time_limit=max_time_per_plan,
        initial_paths=agent_initial_paths,
    )
    solution = acmts.solve()

    # ── 6. 合并分段路径，返回每个 agv_id 的完整路径 ───────────────────────
    # 先按 orig_id 和 seg_idx 排序
    from collections import defaultdict
    seg_paths = defaultdict(dict)   # {orig_id: {seg_idx: path}}

    for ag in agents:
        sparse_path = solution.get(ag.id)
        if not sparse_path:
            continue
        seg_paths[ag.orig_id][ag.seg_idx] = sparse_path

    final_paths = {}
    for agv_id, info in parsed_tasks.items():
        waypoints = info['waypoints']
        n_segs = len(waypoints) - 1
        full_path = []

        for i in range(n_segs):
            seg = seg_paths.get(agv_id, {}).get(i)
            if not seg:
                # 某段规划失败，截断
                break
            if return_sparse:
                path_to_use = seg
            else:
                path_to_use = [graph.vertex_to_grid.get(v, v) for v in seg]

            if not full_path:
                full_path.extend(path_to_use)
            else:
                # 拼接：去掉重复的连接点
                if path_to_use and path_to_use[0] == full_path[-1]:
                    full_path.extend(path_to_use[1:])
                else:
                    full_path.extend(path_to_use)

        if full_path:
            final_paths[agv_id] = full_path

    return final_paths
