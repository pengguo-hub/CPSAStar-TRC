from collections import deque
import random

from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.benchmark_loader import GridMap
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.map_config import ALL_MAPS
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.task_generator import generate_test_tasks


MANUAL_MAP_SIZES = {
    "STANDARD": (16, 11),
    "FRANSEN": (20, 20),
    "RING": (20, 20),
}


def _flatten_cells(cell_dict):
    cells = []
    for coords in cell_dict.values():
        if isinstance(coords, tuple):
            cells.append(coords)
        else:
            cells.extend(list(coords))
    return cells


class CustomBenchmarkLoader:
    """
    用 map_config + task_generator 为 lifelong benchmark 提供统一输入：
    - grid: GridMap
    - agv_info: {agv_id: {'speed': ...}}
    - initial_positions: {agv_id: (x, y)}
    - task_queue: deque([((sx, sy), (gx, gy)), ...])

    约定：
    - 只有 shelf 是障碍；outbound/workstation 都可通行。
    - AGV 初始位置独立随机生成，不再复用任务中的 agv_position。
    - 任务通过 task_generator.generate_test_tasks() 生成，再提取 source/destination。
    - lifelong 任务量通过 repeat 扩充，允许重复任务。
    """

    def __init__(self, map_name: str):
        if map_name not in ALL_MAPS:
            raise ValueError(f"未知 map_name: {map_name}，可选: {list(ALL_MAPS.keys())}")

        self.map_name = map_name
        self.shelf_map, self.outbound_map, self.region_values = ALL_MAPS[map_name]

        if map_name not in MANUAL_MAP_SIZES:
            raise ValueError(
                f"地图 {map_name} 没有手动尺寸，请在 MANUAL_MAP_SIZES 中补上"
            )

        self.width, self.height = MANUAL_MAP_SIZES[map_name]

    def load_map(self) -> GridMap:
        grid = GridMap(width=self.width, height=self.height, cell_size=1)

        for x, y in _flatten_cells(self.shelf_map):
            if not (0 <= x < self.width and 0 <= y < self.height):
                raise ValueError(f"货架坐标越界: {(x, y)} / map={self.map_name}")
            grid.grid[y][x] = 1   # shelf 作为障碍物

        print(f"Custom 地图加载成功: {self.map_name} -> {self.width} x {self.height}")
        return grid

    def load_agv_info(self, num_agvs: int, speed: float = 1.0) -> dict:
        return {f"agv_{i}": {"speed": speed} for i in range(num_agvs)}

    def load_initial_positions(
        self,
        grid: GridMap,
        num_agvs: int,
        seed: int = 42,
        forbid_outbound: bool = False,
    ) -> dict:
        rng = random.Random(seed)

        shelf_cells = set(_flatten_cells(self.shelf_map))
        outbound_cells = set(_flatten_cells(self.outbound_map))

        passable = []
        for y in range(grid.height):
            for x in range(grid.width):
                if (x, y) in shelf_cells:
                    continue
                if forbid_outbound and (x, y) in outbound_cells:
                    continue
                passable.append((x, y))

        if len(passable) < num_agvs:
            raise ValueError(
                f"地图可放置初始 AGV 的自由格只有 {len(passable)} 个，不足以放置 {num_agvs} 个 AGV"
            )

        sampled = rng.sample(passable, num_agvs)
        return {f"agv_{i}": pos for i, pos in enumerate(sampled)}

    def load_task_queue(
        self,
        grid: GridMap,
        num_agvs: int,
        seed: int = 42,
        max_tasks: int = None,
        repeat: int = 1,
        pickup_strategy: str = None,
        pickup_region=None,
        ensure_enough_for_init: bool = True,
    ) -> deque:
        if max_tasks is None:
            base_n = max(num_agvs * 4, 1000)
        else:
            base_n = max(max_tasks, num_agvs if ensure_enough_for_init else 1)

        tasks = generate_test_tasks(
            n_tasks=base_n,
            shelf_map=self.shelf_map,
            outbound_zones=self.outbound_map,
            grid_width=grid.width,
            grid_height=grid.height,
            seed=seed,
            pickup_strategy=pickup_strategy,
            pickup_region=pickup_region,
            occupied_positions=None,
        )

        extracted = []
        shelf_cells = set(_flatten_cells(self.shelf_map))

        for t in tasks:
            sx, sy = t["source"]
            gx, gy = t["destination"]

            if (sx, sy) in shelf_cells:
                raise ValueError(f"任务 source 落在货架上: {(sx, sy)}")
            if (gx, gy) in shelf_cells:
                raise ValueError(f"任务 destination 落在货架上: {(gx, gy)}")

            extracted.append(((sx, sy), (gx, gy)))

        if max_tasks is not None:
            extracted = extracted[:max_tasks]

        if repeat > 1:
            extracted = extracted * repeat

        return deque(extracted)

    def load_all(
        self,
        num_agvs: int,
        speed: float = 1.0,
        seed: int = 42,
        max_tasks: int = None,
        repeat: int = 1,
        forbid_outbound_init: bool = False,
        pickup_strategy: str = None,
        pickup_region=None,
    ):
        grid = self.load_map()
        agv_info = self.load_agv_info(num_agvs, speed)
        initial_positions = self.load_initial_positions(
            grid=grid,
            num_agvs=num_agvs,
            seed=seed,
            forbid_outbound=forbid_outbound_init,
        )
        task_queue = self.load_task_queue(
            grid=grid,
            num_agvs=num_agvs,
            seed=seed,
            max_tasks=max_tasks,
            repeat=repeat,
            pickup_strategy=pickup_strategy,
            pickup_region=pickup_region,
        )

        print(f"初始化完成：{num_agvs} 个 AGV，{len(task_queue)} 个待执行任务")
        return grid, agv_info, initial_positions, task_queue