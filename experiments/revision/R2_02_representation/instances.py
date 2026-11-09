"""Generate one matched direct-planning task set per map/seed."""
import compat  # noqa: F401 -- installs legacy namespace before importing upstream modules
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
    shelves, outbound, values = ALL_MAPS[spec["key"]]
    grid = GridMap(spec["width"], spec["height"], cell_size=1)
    for name, cells in shelves.items():
        for x,y in cells:
            grid.region_coordinate(x,y,values[name])
    return grid


def generate_tasks(map_name, n, seed, prefix, occupied=None):
    seed_all(seed)
    spec = MAPS[map_name]
    shelves, outbound, _ = ALL_MAPS[spec["key"]]
    grid = build_grid(map_name)
    occupied = set(occupied or ())
    capacity = sum(grid.grid[y,x] == 0 and (x,y) not in occupied
                   for x in range(grid.width) for y in range(grid.height))
    if n > capacity:
        raise ValueError(f"{n} unique starts requested but only {capacity} available")
    original_pickups = task_generator.generate_valid_pickup_positions
    task_generator.generate_valid_pickup_positions = lambda *a, **kw: sorted(original_pickups(*a, **kw))
    try:
        tasks = task_generator.generate_test_tasks(n, shelves, outbound, spec["width"], spec["height"],
                                                   seed=seed, occupied_positions=occupied)
    finally:
        task_generator.generate_valid_pickup_positions = original_pickups
    for i, task in enumerate(tasks):
        task["agv_id"] = f"{prefix}-{i+1:04d}"
    return tasks


def parsed_tasks(tasks):
    return {t["agv_id"]: dict(copy.deepcopy(t), waypoints=[t["agv_position"],t["source"],t["destination"]])
            for t in tasks}


def agv_info(tasks, config):
    return {t["agv_id"]: {"speed": config.speed, "position": tuple(t["agv_position"])} for t in tasks}


def initial_order(tasks):
    ranks = {"emergency": 3, "high": 2, "normal": 1}
    return [t["agv_id"] for t in sorted(tasks, key=lambda t: ranks[t["constraints"]["priority"]], reverse=True)]


def build_instance(map_name, seed, max_load, config):
    """Build the complete one-shot task pool. Planning always starts with an empty reservation table."""
    task_seed = int(np.random.SeedSequence([seed, ord(map_name), 1]).generate_state(1)[0])
    tasks = generate_tasks(map_name, max_load, task_seed, "TASK")
    return dict(
        map=map_name,
        seed=seed,
        task_seed=task_seed,
        tasks=tasks,
        task_pool_hash=canonical_hash(tasks),
        task_order_rule="stable priority descending; deadlines=None",
        protocol_note="Direct one-shot planning from an empty reservation table."
    )


def get_instance(directory,map_name,seed,max_load,config):
    path = Path(directory)/f"{map_name}_seed_{seed}.json"
    identity = canonical_hash(dict(protocol_version=4, speed=config.speed, map=MAPS[map_name], max_load=max_load, seed=seed))
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("instance_config_hash") != identity:
            raise ValueError(f"Instance config changed: use another output directory ({path})")
        if canonical_hash(value["tasks"]) != value["task_pool_hash"]:
            raise ValueError("Cached task hash mismatch")
        return value
    value = build_instance(map_name,seed,max_load,config)
    value["instance_config_hash"] = identity
    write_json(path,value)
    return json.loads(path.read_text(encoding="utf-8"))
