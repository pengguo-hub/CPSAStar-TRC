"""Read-only source/input checks. Does NOT execute a Lifelong trial."""
import ast
from collections import Counter
from contextlib import redirect_stdout
import io
import json
from pathlib import Path

from experiments.revision.R2_05_scalability.original_runtime import CORE, ROOT, build_original_inputs, source_audit
from experiments.revision.R2_05_scalability.run_baseline import digest, write_json


def main():
    rows = source_audit()
    assert all(r['matches'] for r in rows)
    tree = ast.parse((CORE / 'Segment_Planner.py').read_text(encoding='utf-8'))
    cap_reads = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                 and n.id in {'MAX_EXPAND', 'expanded'}]
    assert cap_reads == []
    tree_planner = ast.parse((CORE / 'path_planner_lifelong.py').read_text(encoding='utf-8'))
    funcs = {n.name: n for n in ast.walk(tree_planner) if isinstance(n, ast.FunctionDef)}
    # No alternate engine or simulation callback is installed by the launcher.
    assert 'experiment' not in [a.arg for a in funcs['__init__'].args.args]
    records = []
    for fleet in (10, 30, 50):
        for seed in (39, 40, 41, 42, 43):
            with redirect_stdout(io.StringIO()):
                (grid, info, pos, queue), planner_class, paths = build_original_inputs(fleet, seed)
            assert (grid.width, grid.height, grid.grid.shape) == (16, 11, (11, 16))
            assert len(info) == len(pos) == len(set(pos.values())) == fleet
            assert len(queue) == 3000
            base = list(queue)[:100]
            assert list(queue) == base * 30
            expected_shelves = {(x, y) for x in (1, 3, 5, 7, 9, 11, 13)
                                for y in (1, 2, 3, 4, 6, 7, 8, 9)}
            assert {(x, y) for y in range(11) for x in range(16) if grid.grid[y, x]} == expected_shelves
            assert (grid.grid == 0).sum() == 120
            assert all(b in {(15, y) for y in range(3, 8)} for _, b in queue)
            assert all(0 <= x < 16 and 0 <= y < 11 and grid.grid[y, x] == 0
                       for pair in queue for x, y in pair)
            records.append(dict(fleet=fleet, seed=seed, tasks=len(queue),
                                unique_OD_in_base=len(set(base)),
                                initial_positions_hash=digest(pos), task_queue_hash=digest(list(queue)),
                                map_hash=digest(grid.grid.tolist())))
    # For a fixed seed, the explicit max_tasks=100 makes task streams fleet independent.
    assert all(len({r['task_queue_hash'] for r in records if r['seed'] == s}) == 1
               for s in (39, 40, 41, 42, 43))
    with redirect_stdout(io.StringIO()):
        (grid, info, pos, queue), planner_class, _ = build_original_inputs(30, 39)
    # A source-behaviour microcheck, not a simulation or performance sample:
    planner = planner_class(grid, info, pos, queue, use_priority_replan=True)
    returned = planner.segment_planner.plan_agv('agv_0', [pos['agv_0']], 1.0, info, 0.0)
    assert returned == ([], [])  # Preserve the original single-waypoint behaviour.
    report = dict(status='passed', simulation_trials_executed=0, original_files_verified=len(rows),
                  MAX_EXPAND_executable_reads=cap_reads, input_checks=records,
                  original_single_waypoint_return=returned, imported_paths=paths,
                  source_hashes=rows,
                  not_checked=['500-step completion', 'paper reproduction', 'physical correctness',
                               'runtime scalability', 'arrival adapter', 'traffic response'])
    write_json(ROOT / 'validation/preparation_checks.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in {'source_hashes', 'imported_paths', 'input_checks'}}, indent=2))


if __name__ == '__main__':
    main()
