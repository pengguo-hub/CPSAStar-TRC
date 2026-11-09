import numpy as np
from tqdm import tqdm
from src.original_paper.experiment.MCCP.path_planner import GridMap
from src.original_paper.experiment.MCCP.map_config import ALL_MAPS
from src.original_paper.experiment.MCCP.congestion_predictor import MonteCarloCongestionPredictor

# 配置（与训练脚本保持一致）
MAP_ID = 'STANDARD'
NUM_ROBOTS_RANGE = (10, 100)
T_MAX = 50
NUM_SAMPLES = 10000   # 最终需要的样本数
PARTICLE_NUM = 150

# 加载地图
shelf_dict, outbound_dict, _ = ALL_MAPS[MAP_ID]
all_coords = []
for coords in shelf_dict.values():
    all_coords.extend(coords)
for coords in outbound_dict.values():
    all_coords.extend(coords)
max_x = max(x for x, y in all_coords) + 1
max_y = max(y for x, y in all_coords) + 1
real_map = GridMap(width=max_x, height=max_y)
for coords_list in shelf_dict.values():
    for (x, y) in coords_list:
        real_map.add_static_obstacle(x, y)

# 获取自由格子列表
free_cells = [(x, y) for x in range(real_map.width) for y in range(real_map.height)
              if (x, y) not in real_map.static_obstacles]

# 用于存储所有样本的数组
all_u0 = []
all_t = []
all_ut = []

print("开始生成训练数据...")
for i in tqdm(range(NUM_SAMPLES)):
    # 随机选择机器人数量
    min_r, max_r = NUM_ROBOTS_RANGE
    max_possible = min(max_r, len(free_cells))
    n_robots = np.random.randint(min_r, max_possible + 1)

    start_indices = np.random.choice(len(free_cells), n_robots, replace=False)
    starts = [free_cells[i] for i in start_indices]
    goal_indices = np.random.choice(len(free_cells), n_robots, replace=False)
    goals = [free_cells[i] for i in goal_indices]
    tasks = [{'start': s, 'goal': g} for s, g in zip(starts, goals)]

    # 蒙特卡洛模拟
    predictor = MonteCarloCongestionPredictor(real_map, num_particles=PARTICLE_NUM, sigma_smooth=0.8)
    density_dict = predictor.predict(tasks, T_MAX, dt=1.0)

    # 提取 u0
    u0 = np.zeros((real_map.height, real_map.width))
    for y in range(real_map.height):
        for x in range(real_map.width):
            u0[y, x] = density_dict.get((0, x, y), 0.0)

    # 随机选择 t_target
    t_target = np.random.randint(1, T_MAX + 1)
    t_norm = t_target / T_MAX
    u_t = np.zeros((real_map.height, real_map.width))
    for y in range(real_map.height):
        for x in range(real_map.width):
            u_t[y, x] = density_dict.get((t_target, x, y), 0.0)

    all_u0.append(u0)
    all_t.append(t_norm)
    all_ut.append(u_t)

# 保存为 .npz 文件
np.savez('training_data.npz', u0=np.stack(all_u0), t=np.array(all_t), ut=np.stack(all_ut))
print("数据生成完成，已保存到 training_data.npz")