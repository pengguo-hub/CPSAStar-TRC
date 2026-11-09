from pathlib import Path as _RepositoryPath
_REPO_ROOT = _RepositoryPath(__file__).resolve().parents[2]
from Astar_congestion.path_planner import GridMap
from src.original_paper.experiment.Astar_base.path_planner import IntegratedAGVPlanner as Astar_base
from src.original_paper.experiment.CA import IntegratedAGVPlanner as CA
from Astar_congestion.path_planner import IntegratedAGVPlanner as astar_congestion
from src.original_paper.experiment.CPS_A.path_planner import IntegratedAGVPlanner as CPS_PBS
from Fransen import FransenPathPlanner, GridGraph
from src.original_paper.experiment.PBS_planner import PBSPlanner
from src.original_paper.experiment.CBS_planner import CBSPlanner
from src.original_paper.experiment.Qlearning.zhang_multi_agv_planner import ZhangMultiAGVPlanner
from src.original_paper.experiment.lacam2_python.warehouse_adapter import make_lacam2_planner
from src.original_paper.experiment.MCCP.integrated_planner import IntegratedAGVPlanner as AGVPlanner_MCCP
# from SRTP.deployer.api_deployer import API_ModelDeployer
from src.original_paper.experiment.map_config import ALL_MAPS
from src.original_paper.experiment.task_generator import generate_test_tasks
import numpy as np
import matplotlib.pyplot as plt
import os
import re
from datetime import datetime
import json
import time

AGV_FILEPATH = str(_REPO_ROOT / 'data/original_paper/planner/agv_info')
API_URL = "https://api.deepseek.com"
API_KEY = __import__("os").environ.get("DEEPSEEK_API_KEY", "")
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(timestamp)

# api_deployer = API_ModelDeployer(api_url=API_URL, api_key=API_KEY)
api_deployer = None
# ============================================================
# 用户配置区 —— 只需修改这里
# ============================================================
MAP_KEYS       = ['STANDARD']          # 要跑的地图列表，可以加多个，例如 ['STANDARD', 'B', 'C']
TASK_COUNTS_LIST = list(range(100, 101, 10))  # 任务量档位，例如 [10,20,...,100]
SEEDS          =  [42, 43, 44, 45, 46]  # 随机种子列表[42, 53, 66, 78, 99]
WIDTH          = 20
HEIGHT         = 20
PICKUP_REGION  = None  # (min_x, max_x, min_y, max_y) 或 None
LOG_DIR        = str(_REPO_ROOT / 'outputs/original_paper/logs_multi_seed_55test')
# ============================================================


def load_agv_info(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            agv_data = json.load(f)
            for agv_id, info in agv_data.items():
                if isinstance(info['position'], list):
                    info['position'] = tuple(info['position'])
                info['type'] = str(info['type']).strip()
            return agv_data
    else:
        print(f"没有找到{filepath}文件")


agv_info = load_agv_info(AGV_FILEPATH)


def count_turns(path):
    if len(path) < 3:
        return 0
    turns = 0
    prev_dx = path[1][0] - path[0][0]
    prev_dy = path[1][1] - path[0][1]
    for i in range(2, len(path)):
        curr_dx = path[i][0] - path[i - 1][0]
        curr_dy = path[i][1] - path[i - 1][1]
        if (curr_dx, curr_dy) != (prev_dx, prev_dy):
            turns += 1
            prev_dx, prev_dy = curr_dx, curr_dy
    return turns


def count_wait_steps(path):
    if not path or len(path) < 2:
        return 0
    return sum(1 for i in range(1, len(path)) if path[i] == path[i - 1])


def compute_conflicts(paths):
    """计算所有路径之间的点冲突和边冲突总数"""
    if not paths:
        return 0, 0, 0
    max_timesteps = max(len(p) for p in paths.values())
    total_node_conflicts = 0
    total_edge_conflicts = 0
    for t in range(max_timesteps):
        active_positions = {}
        active_edges = {}
        for agv_id, path in paths.items():
            if t >= len(path):
                continue
            x, y = path[t]
            active_positions[agv_id] = (x, y)
            if t > 0:
                prev_x, prev_y = path[t - 1]
                edge = frozenset({(prev_x, prev_y), (x, y)})
                active_edges[agv_id] = edge

        pos_to_agvs = {}
        for agv, pos in active_positions.items():
            pos_to_agvs.setdefault(pos, []).append(agv)
        total_node_conflicts += sum(1 for agvs in pos_to_agvs.values() if len(agvs) > 1)

        edge_to_agvs = {}
        for agv, edge in active_edges.items():
            edge_to_agvs.setdefault(edge, []).append(agv)
        for agvs in edge_to_agvs.values():
            if len(agvs) > 1:
                directions = []
                for agv in agvs:
                    path = paths[agv]
                    if t < len(path) and t > 0:
                        directions.append((path[t - 1], path[t]))
                for i in range(len(directions)):
                    for j in range(i + 1, len(directions)):
                        p1, c1 = directions[i]
                        p2, c2 = directions[j]
                        if p1 == c2 and c1 == p2:
                            total_edge_conflicts += 1
                            break
                    else:
                        continue
                    break

    return max_timesteps, total_node_conflicts, total_edge_conflicts

# def compute_conflicts(paths, times_dict=None):
#     """计算所有路径之间的点冲突和边冲突总数（基于离散 step t）
#        如果提供 times_dict，就顺便打印真实时间戳"""
#     if not paths:
#         return 0, 0, 0
#     max_timesteps = max(len(p) for p in paths.values())
#     total_node_conflicts = 0
#     total_edge_conflicts = 0
#
#     for t in range(max_timesteps):
#         active_positions = {}
#         active_edges = {}
#         for agv_id, path in paths.items():
#             if t >= len(path):
#                 continue
#             x, y = path[t]
#             active_positions[agv_id] = (x, y)
#             if t > 0:
#                 prev_x, prev_y = path[t - 1]
#                 edge = frozenset({(prev_x, prev_y), (x, y)})
#                 active_edges[agv_id] = edge
#
#         # 点冲突
#         pos_to_agvs = {}
#         for agv, pos in active_positions.items():
#             pos_to_agvs.setdefault(pos, []).append(agv)
#
#         for pos, agvs in pos_to_agvs.items():
#             if len(agvs) > 1:
#                 total_node_conflicts += 1
#                 print("\n[DEBUG STEP NODE CONFLICT]", "step=", t, "pos=", pos, "agvs=", agvs)
#                 if times_dict is not None:
#                     for agv in agvs:
#                         if agv in times_dict and t < len(times_dict[agv]):
#                             print("   ", agv, "real_t=", times_dict[agv][t])
#                         else:
#                             print("   ", agv, "real_t= N/A")
#
#         # 边冲突
#         edge_to_agvs = {}
#         for agv, edge in active_edges.items():
#             edge_to_agvs.setdefault(edge, []).append(agv)
#
#         for edge, agvs in edge_to_agvs.items():
#             if len(agvs) > 1:
#                 directions = []
#                 for agv in agvs:
#                     path = paths[agv]
#                     if t < len(path) and t > 0:
#                         directions.append((path[t - 1], path[t]))
#                 for i in range(len(directions)):
#                     for j in range(i + 1, len(directions)):
#                         p1, c1 = directions[i]
#                         p2, c2 = directions[j]
#                         if p1 == c2 and c1 == p2:
#                             total_edge_conflicts += 1
#                             # print("\n[DEBUG STEP EDGE CONFLICT]", "step=", t, "edge=", edge, "agvs=", agvs)
#                             if times_dict is not None:
#                                 for agv in agvs:
#                                     if agv in times_dict and t < len(times_dict[agv]):
#                                         print("   ", agv, "real_t=", times_dict[agv][t],
#                                               "move=", (path[t - 1], path[t]))
#                                     else:
#                                         print("   ", agv, "real_t= N/A")
#                             break
#                     else:
#                         continue
#                     break
#
#     return max_timesteps, total_node_conflicts, total_edge_conflicts



def run_single(planner_name, planner_or_class, waypoints_map, grid,
               api_deployer, agv_info, fransen_grid=None, shelf_map=None,
               obstacle_map=None):
    """跑一次规划，返回该次的各项指标 dict"""

    is_fransen = isinstance(planner_or_class, FransenPathPlanner)

    if is_fransen:
        planner = planner_or_class
    else:
        planner = planner_or_class(grid=grid, llm_deployer=None, api_deployer=api_deployer, agv_info=agv_info)
        if hasattr(planner, "waypoint_generator"):
            class MockWaypointGen:
                def llm_generate_waypoints(self, parsed_tasks):
                    return waypoints_map
            planner.waypoint_generator = MockWaypointGen()

    start_time = time.time()
    try:
        if is_fransen:
            tasks = [
                {"task_id": tid, "agv_id": agv_id,
                 "agv_position": info["agv_position"],
                 "source": info["source"],
                 "destination": info["destination"],
                 "constraints": info.get("constraints", {})}
                for tid, (agv_id, info) in enumerate(waypoints_map.items())
            ]
            metrics = planner.simulate_execution(tasks, max_time=10000.0, dt=1.0)
            result = {
                next(t["agv_id"] for t in tasks if t["task_id"] == task_id):
                [planner.grid.centerpoint_to_coord(cp) for cp in path]
                for task_id, path in planner.task_paths.items()
            }
        else:
            result = planner.batch_plan(parsed_tasks=waypoints_map)
        success = True
    except Exception as e:
        import traceback
        print(f"  ❌ {planner_name} 规划失败: {e}")
        print("".join(traceback.format_exception(type(e), e, e.__traceback__)))
        result = {}
        success = False
    end_time = time.time()
    planning_time = end_time - start_time

    total_tasks = len(waypoints_map)
    success_count = sum(1 for agv_id in waypoints_map if agv_id in result and result[agv_id])
    total_length = sum(len(result[agv_id]) for agv_id in waypoints_map if agv_id in result and result[agv_id])
    avg_length = total_length / success_count if success_count > 0 else 0
    success_rate = success_count / total_tasks

    total_turns = sum(count_turns(result[agv_id]) for agv_id in waypoints_map if agv_id in result and result[agv_id])
    avg_turns = total_turns / success_count if success_count > 0 else 0

    total_waits = sum(count_wait_steps(result[agv_id]) for agv_id in waypoints_map if agv_id in result and result[agv_id])
    avg_waits = total_waits / success_count if success_count > 0 else 0

    makespan, node_conflicts, edge_conflicts = compute_conflicts(result)

    return {
        "planning_time":      round(planning_time, 4),
        "success_rate":       round(success_rate, 4),
        "success_count":      success_count,
        "total_tasks":        total_tasks,
        "total_path_length":  int(total_length),
        "average_path_length": round(avg_length, 4),
        # "total_turns":        int(total_turns),
        # "average_turns":      round(avg_turns, 4),
        # "total_waits":        int(total_waits),
        # "average_waits":      round(avg_waits, 4),
        # "makespan":           int(makespan),
        # "node_conflicts":     int(node_conflicts),
        # "edge_conflicts":     int(edge_conflicts),
        # "run_success":        success,
    }


# ============================================================
# 主循环
# ============================================================
os.makedirs(LOG_DIR, exist_ok=True)

for MAP_KEY in MAP_KEYS:
    shelf_map, outbound_map, region_values = ALL_MAPS[MAP_KEY]

    # 构建 grid
    grid = GridMap(width=WIDTH, height=HEIGHT, cell_size=1)
    grid_data = np.zeros((HEIGHT, WIDTH), dtype=int)
    for shelf_name, coords in shelf_map.items():
        val = region_values[shelf_name]
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid.region_coordinate(x, y, val)
            grid_data[y][x] = val
    for out_name, coords in outbound_map.items():
        val = region_values[out_name]
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            grid_data[y][x] = val

    # obstacle_map for Q-learning
    obstacle_map = np.zeros((HEIGHT, WIDTH), dtype=int)
    for coords in shelf_map.values():
        coords_list = coords if isinstance(coords, list) else [coords]
        for x, y in coords_list:
            if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                obstacle_map[y, x] = 1

    # Fransen grid
    fransen_grid = GridGraph(grid_width=WIDTH, grid_height=HEIGHT, zone_size=1.0)
    all_obstacles = []
    for coords in shelf_map.values():
        if isinstance(coords, list):
            all_obstacles.extend(coords)
        else:
            all_obstacles.append(coords)
    if all_obstacles:
        fransen_grid.add_static_obstacles(all_obstacles)

    for TASK_COUNTS in TASK_COUNTS_LIST:
        print(f"\n{'='*60}")
        print(f"地图: {MAP_KEY}  任务量: {TASK_COUNTS}")
        print(f"{'='*60}")

        # 本次（地图, 任务量）的所有结果
        # 结构: log_data[planner_name][str(seed)] = metrics_dict
        log_data = {
            "map_key":    MAP_KEY,
            "task_count": TASK_COUNTS,
            "seeds":      SEEDS,
            "results":    {}
        }

        for SEED in SEEDS:
            print(f"\n  -- seed={SEED} --")

            # 生成任务
            test_tasks = generate_test_tasks(
                n_tasks=TASK_COUNTS, shelf_map=shelf_map,
                outbound_zones=outbound_map, grid_width=WIDTH,
                grid_height=HEIGHT, pickup_region=PICKUP_REGION,
                seed=SEED,
                pickup_strategy='inner' if MAP_KEY == 'C' else None
            )

            # 构建 waypoints_map
            waypoints_map = {}
            for task in test_tasks:
                waypoints_map[task["agv_id"]] = {
                    "task_id":      task["task_id"],
                    "agv_position": task["agv_position"],
                    "source":       task["source"],
                    "destination":  task["destination"],
                    "waypoints":    [task["agv_position"], task["source"], task["destination"]],
                    "constraints":  task["constraints"],
                }

            # 构建 Fransen planner（每次 seed 重新实例化，避免状态残留）
            fransen_planner = FransenPathPlanner(
                grid=fransen_grid,
                dz=5, delta_t=10.0, k=0.25, T=50.0,
                alpha=200.0, p_turn=1.0, agv_speed=1.0
            )

            # 算法字典 —— 自行增删
            planner_classes = {
                "CA*": Astar_base,
                # "CA":   lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: CA(grid=grid, agv_info=agv_info),
                "CPS-A*": lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: CPS_PBS(grid=grid, agv_info=agv_info),
                # "PBS":  lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: PBSPlanner(grid=grid, agv_info=agv_info, max_iter=20000, time_limit=60),
                # "CBS":  lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: CBSPlanner(grid=grid, agv_info=agv_info, max_iters=20000, time_limit=60),
                # "Q_Learning": lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: ZhangMultiAGVPlanner(
                #     grid_map=obstacle_map, agv_speed=1.0, gamma=0.8, alpha=0.1,
                #     obstacle_reward=-10, goal_reward=100, epsilon=0.1),
                # "MCCP": lambda grid, llm_deployer=None, api_deployer=None, agv_info=None: AGVPlanner_MCCP(grid=grid, predictor_type='neural',
                #                                                                                       model_path="./MCCP/A_neural_predictor_final.pth"),
                # "LaCAM2_Guided": make_lacam2_planner(
                #     width=WIDTH, height=HEIGHT, shelf_map=shelf_map,
                #     timeout_ms=60000, guid_t_ms=30000, verbose=0),
            }

            for name, planner_or_class in planner_classes.items():
                print(f"    {name} ...", end=" ", flush=True)
                metrics = run_single(
                    planner_name=name,
                    planner_or_class=planner_or_class,
                    waypoints_map=waypoints_map,
                    grid=grid,
                    api_deployer=api_deployer,
                    agv_info=agv_info,
                    obstacle_map=obstacle_map,
                )
                print(
                    f"成功率={metrics['success_rate']:.2%}  "
                    f"耗时={metrics['planning_time']:.3f}s  "
                    f"均路径长={metrics['average_path_length']:.1f}  "
                    # f"均转弯={metrics['average_turns']:.1f}  "
                    # f"均等待={metrics['average_waits']:.1f}  "
                    # f"makespan={metrics['makespan']}  "
                    # f"点冲突={metrics['node_conflicts']}  "
                    # f"边冲突={metrics['edge_conflicts']}"
                )

                # 存入 log_data
                if name not in log_data["results"]:
                    log_data["results"][name] = {}
                log_data["results"][name][str(SEED)] = metrics

        # 保存当前（地图, 任务量）的 JSON 日志
        log_filename = os.path.join(LOG_DIR, f"{MAP_KEY}_{TASK_COUNTS}tasks.json")
        os.makedirs(os.path.dirname(log_filename), exist_ok=True)
        with open(log_filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ 已保存: {log_filename}")

print("\n🎉 全部实验完成！")
