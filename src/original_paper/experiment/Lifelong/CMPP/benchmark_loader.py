"""
统一的地图/任务/AGV初始化加载器。
所有参与对比的算法（你的方法、RHCR、PIBT等）都通过这个类获取：
  - GridMap 对象
  - agv_info 字典
  - initial_positions 字典
  - task_queue 双端队列

保证相同参数下，所有算法拿到完全一致的输入，确保实验对比公平。
"""
import numpy as np
import random
from collections import deque

class GridMap:
    def __init__(self, width=0, height=0, cell_size=1):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.grid = np.zeros((height, width), dtype=int)
        # grid 值含义：0=可通行，1=静态障碍，2=空闲AGV临时占位

    def load_movingai_map(self, file_path):
        with open(file_path, 'r') as f:
            lines = f.read().splitlines()

        if not lines or lines[0].strip() != 'type octile':
            raise ValueError("不支持的 MAP 格式，目前只支持 'type octile'")

        # 动态查找 height 和 width，不依赖固定行号
        self.height = None
        self.width = None
        map_start = None

        for i, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == 'height':
                self.height = int(parts[1])
            elif len(parts) == 2 and parts[0] == 'width':
                self.width = int(parts[1])
            elif line.strip() == 'map':
                map_start = i + 1
                break

        if self.height is None or self.width is None or map_start is None:
            raise ValueError("MAP 文件格式错误，缺少 height/width 或 map 标记")

        self.grid = np.zeros((self.height, self.width), dtype=int)
        for i in range(self.height):
            line = lines[map_start + i].strip()
            for j, ch in enumerate(line):
                if ch == '@' or ch == 'T':
                    self.grid[i][j] = 1

        print(f"MovingAI 地图加载成功: {self.width} x {self.height}")
        return self.grid


class BenchmarkLoader:
    def __init__(self, map_file: str, scen_file: str):
        """
        Args:
            map_file:  MovingAI .map 文件路径
            scen_file: MovingAI .scen 文件路径
        """
        self.map_file  = map_file
        self.scen_file = scen_file
        self._raw_tasks = None  # 缓存原始任务列表，避免重复读文件

    # =========================================================================
    # 地图
    # =========================================================================
    def load_map(self) -> GridMap:
        """
        加载地图，返回 GridMap 对象。
        直接传给 LifelongPlanner(grid=...) 即可。
        """
        grid = GridMap()
        grid.load_movingai_map(self.map_file)
        return grid

    # =========================================================================
    # AGV 基本信息
    # =========================================================================
    def load_agv_info(self, num_agvs: int, speed: float = 1.0) -> dict:
        """
        返回 agv_info: {agv_id: {'speed': float}}
        agv_id 格式为 'agv_0', 'agv_1', ...

        Args:
            num_agvs: AGV 数量
            speed:    所有 AGV 统一速度，默认 1.0（即每时间步移动1格）
        """
        return {f"agv_{i}": {"speed": speed} for i in range(num_agvs)}

    # =========================================================================
    # AGV 初始位置
    # =========================================================================
    def load_initial_positions(
        self,
        grid: GridMap,
        num_agvs: int,
        strategy: str = "random",
        seed: int = 42,
    ) -> dict:
        """
        返回 initial_positions: {agv_id: (x, y)}

        Args:
            grid:     GridMap 对象（strategy='random' 时用于筛选可通行格）
            num_agvs: AGV 数量
            strategy: 初始化策略
                'from_scen' —— 从 scen 文件前 num_agvs 行的 start_x/start_y 作为初始位置
                              （与任务队列的 skip_first_n=num_agvs 配合使用）
                'random'    —— 从地图可通行格（grid==0）随机均匀采样
                              （用 seed 固定随机数，保证可复现）
            seed:     随机种子（仅 strategy='random' 时生效）

        Returns:
            {agv_id: (x, y)}，agv_id 与 load_agv_info 保持一致
        """
        if strategy == "from_scen":
            raw = self._get_raw_tasks()
            if len(raw) < num_agvs:
                raise ValueError(
                    f"scen 文件只有 {len(raw)} 条记录，不足以初始化 {num_agvs} 个 AGV"
                )
            positions = {}
            for i in range(num_agvs):
                agv_id = f"agv_{i}"
                start, _ = raw[i]          # raw[i] = ((start_x, start_y), (goal_x, goal_y))
                positions[agv_id] = start
            return positions

        elif strategy == "random":
            rng = random.Random(seed)
            # 收集所有可通行格（grid 值为 0）
            passable = [
                (x, y)
                for y in range(grid.height)
                for x in range(grid.width)
                if grid.grid[y][x] == 0
            ]
            if len(passable) < num_agvs:
                raise ValueError(
                    f"地图可通行格只有 {len(passable)} 个，不足以放置 {num_agvs} 个 AGV"
                )
            sampled = rng.sample(passable, num_agvs)
            return {f"agv_{i}": pos for i, pos in enumerate(sampled)}

        else:
            raise ValueError(f"未知的 strategy: '{strategy}'，可选 'from_scen' 或 'random'")

    # =========================================================================
    # 任务队列
    # =========================================================================
    def load_task_queue(
        self,
        skip_first_n: int = 0,
        max_tasks: int = None,
        repeat = 1
    ) -> deque:
        """
        返回 task_queue: deque of ((pickup_x, pickup_y), (dropoff_x, dropoff_y))

        Args:
            skip_first_n: 跳过前 n 条记录
                          strategy='from_scen' 初始化时用了前 num_agvs 条，
                          所以这里传 skip_first_n=num_agvs，避免重复使用同一条记录作为任务
            max_tasks:    最多加载多少个任务（None 表示全部）

        Returns:
            deque，每个元素是 (pickup, dropoff)，均为 (x, y) 元组
        """
        raw = self._get_raw_tasks()
        tasks = raw[skip_first_n:]
        if max_tasks is not None:
            tasks = tasks[:max_tasks]
        if repeat > 1:
            tasks = tasks * repeat
        return deque(tasks)

    # =========================================================================
    # 内部：解析 .scen 文件
    # =========================================================================
    def _get_raw_tasks(self):
        """
        解析 .scen 文件，返回 list of ((start_x, start_y), (goal_x, goal_y))。
        结果缓存在 self._raw_tasks，避免重复 IO。

        .scen 文件格式（每行）：
            bucket  map  width  height  start_x  start_y  goal_x  goal_y  optimal_length
        在 lifelong MAPD 场景中：
            start_x/start_y → pickup 点
            goal_x/goal_y   → dropoff 点
        """
        if self._raw_tasks is not None:
            return self._raw_tasks

        tasks = []
        with open(self.scen_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("version") or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 8:
                    pickup  = (int(parts[4]), int(parts[5]))
                    dropoff = (int(parts[6]), int(parts[7]))
                    tasks.append((pickup, dropoff))

        self._raw_tasks = tasks
        print(f"scen 文件解析完成，共 {len(tasks)} 条任务记录")
        return tasks

    # =========================================================================
    # 便捷方法：一次性返回所有参数（推荐调用方式）
    # =========================================================================
    def load_all(
        self,
        num_agvs: int,
        speed: float = 1.0,
        strategy: str = "random",
        seed: int = 42,
        max_tasks: int = None,
        repeat = 1
    ) -> tuple:
        """
        一次性返回 (grid, agv_info, initial_positions, task_queue)，
        直接解包传给 LifelongPlanner。

        Args:
            num_agvs:  AGV 数量
            speed:     AGV 速度
            strategy:  初始位置策略，'from_scen' 或 'random'
            seed:      随机种子（strategy='random' 时生效）
            max_tasks: 任务队列最大长度（None 表示全部）

        Returns:
            (grid, agv_info, initial_positions, task_queue)

        典型用法：
            loader = BenchmarkLoader("warehouse.map", "warehouse.scen")
            grid, agv_info, init_pos, task_queue = loader.load_all(num_agvs=100)
            planner = LifelongPlanner(grid, agv_info, init_pos, task_queue)
            completed, failed = planner.run_lifelong()
        """
        grid = self.load_map()
        agv_info = self.load_agv_info(num_agvs, speed)
        initial_positions = self.load_initial_positions(grid, num_agvs, strategy, seed)

        # strategy='from_scen' 时前 num_agvs 条用于初始化位置，任务从第 num_agvs 条开始
        skip = num_agvs if strategy == "from_scen" else 0
        task_queue = self.load_task_queue(skip_first_n=skip, max_tasks=max_tasks, repeat=repeat)

        print(f"初始化完成：{num_agvs} 个 AGV，{len(task_queue)} 个待执行任务")
        return grid, agv_info, initial_positions, task_queue
