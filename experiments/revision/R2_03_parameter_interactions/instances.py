"""Generate and cache paired one-shot task instances. No background planner is used."""
import compat  # noqa: F401
import copy
import hashlib
import json
import random
from pathlib import Path
import numpy as np
from config import MAPS
from vendor.CPS_A.path_planner import GridMap
from vendor.map_config import ALL_MAPS
from vendor import task_generator

def canonical_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)

def seed_all(seed):
    random.seed(int(seed))
    np.random.seed(int(seed) % 2**32)

def build_grid(map_name):
    spec = MAPS[map_name]
    shelves, _, values = ALL_MAPS[spec["key"]]
    grid = GridMap(spec["width"], spec["height"], cell_size=1)
    for name, cells in shelves.items():
        for x, y in cells:
            grid.region_coordinate(x, y, values[name])
    return grid

def generate_tasks(map_name, task_count, seed):
    """Use the original experiment task generator, with deterministic pickup ordering."""
    seed_all(seed)
    spec = MAPS[map_name]
    shelves, outbound, _ = ALL_MAPS[spec["key"]]
    original_pickups = task_generator.generate_valid_pickup_positions
    task_generator.generate_valid_pickup_positions = lambda *a, **kw: sorted(original_pickups(*a, **kw))
    try:
        tasks = task_generator.generate_test_tasks(
            task_count, shelves, outbound, spec["width"], spec["height"], seed=seed
        )
    finally:
        task_generator.generate_valid_pickup_positions = original_pickups
    return tasks

def parsed_tasks(tasks):
    return {
        t["agv_id"]: dict(copy.deepcopy(t), waypoints=[t["agv_position"], t["source"], t["destination"]])
        for t in tasks
    }

def agv_info(tasks, config):
    return {t["agv_id"]: {"speed": config.speed, "position": tuple(t["agv_position"])} for t in tasks}

def get_task_instance(cache_dir, map_name, task_count, seed):
    cache_dir = Path(cache_dir)
    path = cache_dir / f"{map_name}_N{task_count}_seed{seed}.json"
    if path.exists():
        obj = json.loads(path.read_text(encoding="utf-8"))
    else:
        tasks = generate_tasks(map_name, task_count, seed)
        obj = {
            "map": map_name,
            "task_count": int(task_count),
            "seed": int(seed),
            "tasks": tasks,
            "task_hash": canonical_hash(tasks),
        }
        write_json(path, obj)
    if len(obj["tasks"]) != task_count:
        raise AssertionError("Cached task count mismatch")
    if canonical_hash(obj["tasks"]) != obj["task_hash"]:
        raise AssertionError("Cached task hash mismatch")
    return obj
