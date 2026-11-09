"""Import-only compatibility for byte-identical sources from experiment.zip.

No planner subclass, monkey patch, input replacement, or simulation loop.
"""
from pathlib import Path
import hashlib
import importlib
import json
import sys

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor'
LIFELONG = VENDOR / 'SRTP/experiment/Lifelong'
CORE = LIFELONG / 'CPS_A_lifelong'


def source_audit():
    manifest = json.loads((ROOT / 'provenance/original_sources.json').read_text(encoding='utf-8'))
    return [dict(row, matches=hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest()
                 == row['sha256']) for row in manifest]


def load_original():
    # Original absolute sibling imports and SRTP.experiment.map_config both work.
    # The Lifelong loader is ahead of the duplicate MovingAI-only core loader.
    sys.path[:0] = [str(LIFELONG), str(CORE), str(VENDOR)]
    names = ['custom_benchmark_loader', 'CPS_A_lifelong.path_planner_lifelong',
             'Conflict_Field_Updater', 'Segment_Planner', 'Ticket_Manager',
             'benchmark_loader', 'map_config', 'task_generator', 'SRTP.experiment.map_config']
    modules = {n: importlib.import_module(n) for n in names}
    paths = {n: str(Path(m.__file__).resolve()) for n, m in modules.items()}
    # This is source provenance, not a map reachability or planner feasibility check.
    if not all(Path(p).is_relative_to(VENDOR.resolve()) for p in paths.values()):
        raise RuntimeError('An original module was shadowed: ' + str(paths))
    return (modules[names[0]].CustomBenchmarkLoader,
            modules[names[1]].LifelongPlanner, paths)


def build_original_inputs(fleet, seed):
    loader_class, planner_class, paths = load_original()
    loader = loader_class('STANDARD')
    inputs = loader.load_all(num_agvs=fleet, speed=1.0, seed=seed,
                            max_tasks=100, repeat=30, forbid_outbound_init=False,
                            pickup_strategy=None, pickup_region=None)
    return inputs, planner_class, paths
