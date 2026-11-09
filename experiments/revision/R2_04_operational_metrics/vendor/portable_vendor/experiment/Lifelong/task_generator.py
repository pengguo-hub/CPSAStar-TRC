# 任务生成工具与多组预生成任务集
import random
from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.map_config import ALL_MAPS


def is_point_on_shelf(x, y, shelf_map):
    """检查点是否在货架上"""
    target = (x, y)
    for coords in shelf_map.values():
        if isinstance(coords, list):
            if target in coords:
                return True
        elif isinstance(coords, tuple):
            if target == coords:
                return True
    return False


def sample_free_point(grid_width, grid_height, shelf_map, exclude_shelf=True):
    """随机采样一个自由点"""
    while True:
        x = random.randint(0, grid_width - 1)
        y = random.randint(0, grid_height - 1)
        if exclude_shelf and is_point_on_shelf(x, y, shelf_map):
            continue
        return [x, y]


def generate_valid_pickup_positions(shelf_map, grid_width, grid_height, pickup_region=None):
    """
    生成所有合法取货点：即与任意货架相邻（上下左右）且自身不是货架的自由格子。
    返回一个列表 of (x, y) 元组。
    """
    # 将所有货架坐标放入集合，加速查询
    shelf_set = set()
    for coords in shelf_map.values():
        if isinstance(coords, list):
            shelf_set.update(coords)
        elif isinstance(coords, tuple):
            shelf_set.add(coords)

    pickup_positions = set()
    directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]  # 上、下、右、左

    if pickup_region is not None:
        min_x,max_x,min_y,max_y = pickup_region
    else:
        min_x, max_x = 0, grid_width - 1
        min_y, max_y = 0, grid_height - 1

    for (sx, sy) in shelf_set:
        for dx, dy in directions:
            nx, ny = sx + dx, sy + dy
            # 检查是否在地图范围内 AND 在 pickup_region 内
            if not (0 <= nx < grid_width and 0 <= ny < grid_height):
                continue
            if not (min_x <= nx <= max_x and min_y <= ny <= max_y):
                continue
            # 检查是否不是货架（即为通道）
            if (nx, ny) not in shelf_set:
                pickup_positions.add((nx, ny))

    return list(pickup_positions)


def classify_circular_pickup_positions(shelf_map, grid_width, grid_height):
    """
    针对 Map C 的环形货架，将合法取货点分为：
    - inner: 环内部（x in [16,33], y in [16,33]）
    - outer: 环外部（不在 [15,34]×[15,34] 区域内，或在边界外侧）

    返回 {'inner': [...], 'outer': [...]}
    """
    # 先获取所有合法取货点（邻接货架的自由格）
    if '中心环形货架' not in shelf_map:
        # 非环形地图，返回全部为 outer（或报错）
        all_valid = generate_valid_pickup_positions(shelf_map, grid_width, grid_height)
        return {'inner': [], 'outer': all_valid}

    ring_coords = shelf_map['中心环形货架']
    if isinstance(ring_coords, tuple):
        ring_coords = [ring_coords]
    elif not isinstance(ring_coords, list):
        ring_coords = list(ring_coords)

    xs = [x for x, y in ring_coords]
    ys = [y for x, y in ring_coords]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # 环内部区域：严格在 (min_x, max_x) × (min_y, max_y) 内部
    inner_region = (min_x + 1, max_x - 1, min_y + 1, max_y - 1)
    inner_min_x, inner_max_x, inner_min_y, inner_max_y = inner_region

    all_valid = generate_valid_pickup_positions(shelf_map, grid_width, grid_height)

    inner = []
    outer = []
    for (x, y) in all_valid:
        if inner_min_x <= x <= inner_max_x and inner_min_y <= y <= inner_max_y:
            inner.append((x, y))
        else:
            outer.append((x, y))

    return {'inner': inner, 'outer': outer}

def generate_test_tasks(n_tasks, shelf_map, outbound_zones, grid_width , grid_height, seed=None, pickup_strategy=None, pickup_region=None, occupied_positions=None):
    """
    新增参数:
        occupied_positions: Set[Tuple[int, int]] - 禁止生成任务的坐标集合（例如已有AGV的位置）
    """
    """生成 n 个任务"""
    if seed is not None:
        random.seed(seed)

    # >>> 新增：预计算所有合法取货点 <<<
    # valid_pickups = generate_valid_pickup_positions(shelf_map,grid_width, grid_height)
    valid_pickups = generate_valid_pickup_positions(shelf_map,grid_width,grid_height,pickup_region=pickup_region)
    # >>> 特殊处理 Map C <<<
    # 如何判断是 Map C？可通过检查是否存在 "中心环形货架"
    if '中心环形货架' in shelf_map:
        classified = classify_circular_pickup_positions(shelf_map,grid_width, grid_height)
        if pickup_strategy == 'inner':
            valid_pickups = classified['inner']
            # print(f"[Info] Map C: 使用内部取货点，共 {len(valid_pickups)} 个")
        elif pickup_strategy == 'outer':
            valid_pickups = classified['outer']
            # print(f"[Info] Map C: 使用外部取货点，共 {len(valid_pickups)} 个")
        # 如果 pickup_strategy is None，则仍用全部（inner + outer）

    if not valid_pickups:
        raise ValueError("没有找到任何合法取货点！请检查货架布局。")

    # 获取所有出库口位置
    outbound_list = []
    for coords in outbound_zones.values():
        outbound_list.extend(coords)

    tasks = []
    used_positions = set()

    for i in range(n_tasks):
        task_id = i + 1
        agv_id = f"AGV-{i + 1:03d}"

        # AGV 当前位置：随机自由点（避免重复）
        while True:
            pos = tuple(sample_free_point(grid_width, grid_height, shelf_map))
            if pos not in used_positions and (occupied_positions is None or pos not in occupied_positions):
                used_positions.add(pos)
                break

        # source：取货点，在道路上
        source = list(random.choice(valid_pickups))

        # destination：从出库口中随机选
        dest = random.choice(outbound_list)
        # while True:
        #     dest = sample_free_point(grid_width, grid_height, shelf_map)
        #     if dest != source:
        #         break
        # dest = list(dest)

        priority = random.choices(["emergency", "high", "normal"], weights=[1, 2, 7])[0]
        time_limit = None
        # if priority == "high":
        #     time_limit = f"{random.randint(10, 15):02d}:{random.choice([0, 15, 30, 45]):02d}"
        # elif priority == "emergency":
        #     time_limit = f"{random.randint(8, 12):02d}:{random.choice([0, 15]):02d}"

        tasks.append({
            "task_id": task_id,
            "agv_id": agv_id,
            "agv_position": list(pos),
            "source": source,
            "destination": dest,
            "constraints": {
                "priority": priority,
                "time_limit": time_limit
            }
        })

    return tasks

#特殊八个任务
TASKS = [
    {
        'task_id': 'AGV-001',
        'agv_position': (4, 10),
        'source': (4,3),
        'destination': (12, 0)
    },
    {
        'task_id': 'AGV-002',
        'agv_position': (8, 8),
        'source': (8,3),
        'destination': (3, 0)
    },
    {
        'task_id': 'AGV-003',
        'agv_position': (10, 3),
        'source': (10, 1),
        'destination': (2, 2)
    },
    {
        'task_id': 'AGV-004',
        'agv_position': (11, 5),
        'source': (7, 5),
        'destination': (2, 6)
    },
    {
        'task_id': 'AGV-005',
        'agv_position': (6, 0),
        'source': (6, 2),
        'destination': (6, 7)
    },
    {
        'task_id': 'AGV-006',
        'agv_position': (7, 10),
        'source': (10, 9),
        'destination': (10, 6)
    },
    {
        'task_id': 'AGV-007',
        'agv_position': (12, 3),
        'source': (12, 6),
        'destination': (8, 7)
    },
    {
        'task_id': 'AGV-008',
        'agv_position': (2, 8),
        'source': (2, 6),
        'destination': (4, 8)
    }
]

def convert_predefined_tasks():
    """将预定义的任务转换为标准格式"""
    converted_tasks = []
    for i, task in enumerate(TASKS):
        converted_task = {
            "task_id": i + 1,
            "agv_id": task['task_id'],
            "agv_position": list(task['agv_position']),
            "source": list(task['source']),
            "destination": list(task['destination']),
            "constraints": {
                "priority": "normal",
                "time_limit": None
            }
        }
        converted_tasks.append(converted_task)
    return converted_tasks
