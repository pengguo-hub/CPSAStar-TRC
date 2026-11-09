"""
check_map_max_agvs.py

统计每张自定义地图最多能放多少 AGV。
规则：
- 只有 shelf 是障碍；
- 其余格子都视为可通行；
- max_agvs_all_passable = 所有非 shelf 格子数；
- max_agvs_excluding_outbound = 所有非 shelf 且非 outbound 格子数。

运行:
    python check_map_max_agvs.py
"""

from src.original_paper.experiment.Lifelong.custom_benchmark_loader import CustomBenchmarkLoader
from src.original_paper.experiment.Lifelong.map_config import ALL_MAPS


def flatten_cells(cell_dict):
    cells = []
    for coords in cell_dict.values():
        if isinstance(coords, tuple):
            cells.append(coords)
        else:
            cells.extend(list(coords))
    return cells


def analyze_map(map_name: str):
    loader = CustomBenchmarkLoader(map_name)
    grid = loader.load_map()

    shelf_cells = set(flatten_cells(loader.shelf_map))
    outbound_cells = set(flatten_cells(loader.outbound_map))

    passable_all = []
    passable_without_outbound = []

    for y in range(grid.height):
        for x in range(grid.width):
            pos = (x, y)
            if pos in shelf_cells:
                continue
            passable_all.append(pos)
            if pos not in outbound_cells:
                passable_without_outbound.append(pos)

    print("=" * 70)
    print(f"地图: {map_name}")
    print(f"尺寸: {grid.width} x {grid.height} = {grid.width * grid.height} 格")
    print(f"货架障碍数(shelf): {len(shelf_cells)}")
    print(f"outbound/workstation 数: {len(outbound_cells)}")
    print(f"可通行格数(含outbound): {len(passable_all)}")
    print(f"最大AGV数(允许初始位置在outbound): {len(passable_all)}")
    print(f"可通行格数(不含outbound): {len(passable_without_outbound)}")
    print(f"最大AGV数(禁止初始位置在outbound): {len(passable_without_outbound)}")

    return {
        "map_name": map_name,
        "width": grid.width,
        "height": grid.height,
        "total_cells": grid.width * grid.height,
        "shelf_cells": len(shelf_cells),
        "outbound_cells": len(outbound_cells),
        "max_agvs_all_passable": len(passable_all),
        "max_agvs_excluding_outbound": len(passable_without_outbound),
    }


def main():
    print("开始统计每张地图最大可放置 AGV 数...\n")

    results = []
    for map_name in ALL_MAPS.keys():
        results.append(analyze_map(map_name))

    print("\n" + "#" * 70)
    print("汇总")
    print("#" * 70)
    for r in results:
        print(
            f"{r['map_name']}: "
            f"尺寸={r['width']}x{r['height']}, "
            f"最大AGV(含outbound)={r['max_agvs_all_passable']}, "
            f"最大AGV(不含outbound)={r['max_agvs_excluding_outbound']}"
        )


if __name__ == "__main__":
    main()
