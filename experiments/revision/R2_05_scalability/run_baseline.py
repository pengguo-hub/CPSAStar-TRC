"""One original-Lifelong baseline, never a matrix; no wall-clock timeout.

--prepare-only constructs and saves original inputs without running a simulation.
The child calls the original run_lifelong(max_time=500) without wrappers/hooks.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

from experiments.revision.R2_05_scalability.original_runtime import ROOT, build_original_inputs, source_audit


def write_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def od_counts(tasks):
    return Counter((tuple(a), tuple(b)) for a, b in tasks)


def worker(args):
    import numpy as np
    out = args.output
    planner = None
    original_tasks = []
    loop_started = None
    meta = dict(status='initializing', fleet=args.fleet, seed=args.seed,
                map='STANDARD', horizon=500, warmup=0,
                supply='100 original generated requests repeated 30 times, all queued at t=0',
                nominal_arrival_rate=None, source='experiment.zip/experiment/Lifelong',
                python=sys.version, numpy=np.__version__, platform=platform.platform(),
                processor=platform.processor(), cpu_count=os.cpu_count(),
                max_expand_enabled=False, trial_wall_timeout=None,
                eligible_full_run=False, paper_reproduction_gate='not_run')
    try:
        hashes = source_audit()
        write_json(out / 'source_verification.json', hashes)
        if not all(row['matches'] for row in hashes):
            raise RuntimeError('Vendored source differs from the recorded original ZIP bytes')
        (grid, agv_info, positions, queue), planner_class, paths = build_original_inputs(args.fleet, args.seed)
        original_tasks = list(queue)
        inputs = dict(grid=grid.grid.tolist(), width=grid.width, height=grid.height,
                      agv_info=agv_info, initial_positions=positions, task_queue=original_tasks)
        write_json(out / 'inputs.json', inputs)
        meta.update(input_hash=digest(inputs), map_hash=digest(inputs['grid']),
                    width=grid.width, height=grid.height, import_paths=paths,
                    initial_tasks=len(queue), free_cells=int((grid.grid == 0).sum()))
        write_json(out / 'metadata.json', meta)
        if args.prepare_only:
            meta.update(status='prepared_only', simulation_executed=False)
            write_json(out / 'native_result.json', meta)
            print('PREPARED ONLY: no simulation, no throughput, no performance sample.', flush=True)
            return 0
        planner = planner_class(grid, agv_info, positions, queue, use_priority_replan=True)
        write_json(out / 'metadata.json', dict(meta, status='running'))
        print('Original 30/10/50 fleet baseline: begin t=0, stop at t=500; no warmup.', flush=True)
        loop_started = time.perf_counter()
        loop_cpu_started = time.process_time()
        completed, total_assigned = planner.run_lifelong(max_time=500)
        loop_wall = time.perf_counter() - loop_started
        loop_cpu = time.process_time() - loop_cpu_started
        # Exactly the formulas in test_ourmap.py:run_cpsa.
        throughput = planner.get_throughput()
        success_rate = len(completed) / total_assigned * 100.0 if total_assigned > 0 else 0.0
        # Post-run, read-only accounting. Nothing feeds back to planning.
        finished_od = [(t['pickup'], t['dropoff']) for _, t in completed]
        active_od = [(t['pickup'], t['dropoff']) for t in planner.agv_tasks.values()]
        conserved = od_counts(original_tasks) == od_counts(finished_od + active_od + list(planner.task_queue))
        count_ok = len(original_tasks) == len(completed) + len(planner.agv_tasks) + len(planner.task_queue)
        assigned_ok = total_assigned == len(completed) + len(planner.agv_tasks)
        full = planner.current_time == 500
        meta.update(status='completed' if full and conserved and count_ok and assigned_ok else 'incomplete_or_accounting_mismatch',
                    simulation_executed=True, observed_time=planner.current_time,
                    completed=len(completed), source_total_assigned=total_assigned,
                    final_queue=len(planner.task_queue), active_tasks=len(planner.agv_tasks),
                    unfinished=len(original_tasks)-len(completed),
                    throughput=throughput, source_success_percent=success_rate,
                    completion_fraction_of_initial_supply=len(completed)/len(original_tasks),
                    native_loop_wall_seconds=loop_wall,
                    native_loop_cpu_seconds=loop_cpu,
                    native_assignment_seconds=planner.total_assignment_time,
                    native_pure_seconds=loop_wall-planner.total_assignment_time,
                    segment_planning_seconds=None, cumulative_batch_planning_seconds=None,
                    waiting_time=None, flow_time=None, queue_length_time_mean=None,
                    raw_native_metrics=True, eligible_full_run=full and conserved and count_ok and assigned_ok,
                    count_conservation=count_ok, od_multiset_conservation=conserved,
                    source_assigned_identity=assigned_ok, paper_reproduction_gate='not_reviewed')
        print(json.dumps(meta, ensure_ascii=False), flush=True)
        return 0 if meta['eligible_full_run'] else 2
    except BaseException as exc:
        meta.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'error',
                    simulation_executed=loop_started is not None, error=traceback.format_exc(),
                    eligible_full_run=False, paper_reproduction_gate='not_passed')
        if planner is not None:
            meta.update(observed_time=planner.current_time, completed=len(planner.completed_tasks),
                        final_queue=len(planner.task_queue), active_tasks=len(planner.agv_tasks))
        print(meta['error'], flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        if planner is not None:
            write_json(out / 'final_native_state.json', dict(
                current_time=planner.current_time, completed_tasks=planner.completed_tasks,
                agv_tasks=planner.agv_tasks, task_queue=list(planner.task_queue),
                agv_positions=planner.agv_positions,
                total_assigned_tasks=planner.total_assigned_tasks))
        write_json(out / 'native_result.json', meta)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fleet', type=int, choices=[10, 30, 50], default=30)
    p.add_argument('--seed', type=int, default=39)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    args.output = args.output.resolve()
    if args._worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)  # Never overwrite a previous trial.
    started = time.perf_counter()
    status = dict(status='running', started_utc=datetime.now(timezone.utc).isoformat(),
                  parent_pid=os.getpid(), fleet=args.fleet, seed=args.seed,
                  prepare_only=args.prepare_only, trial_wall_timeout=None)
    write_json(args.output / 'status.json', status)
    cmd = [sys.executable, '-u', str(Path(__file__).resolve()), '--_worker',
           '--fleet', str(args.fleet), '--seed', str(args.seed), '--output', str(args.output)]
    if args.prepare_only:
        cmd.append('--prepare-only')
    print('Output:', args.output, flush=True)
    print('Progress log:', args.output / 'native.log', flush=True)
    with (args.output / 'native.log').open('w', encoding='utf-8', buffering=1) as log:
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
        process = subprocess.Popen(cmd, cwd=ROOT.parents[2], stdout=log, stderr=subprocess.STDOUT, env=env)
        status['child_pid'] = process.pid
        write_json(args.output / 'status.json', status)
        try:
            code = process.wait()  # Deliberately no timeout, budget, kill, or retry.
        except KeyboardInterrupt:
            # Preserve the process state if only the parent received an interrupt.
            # A terminal-generated Ctrl+C normally reaches the child independently.
            status.update(status='parent_interrupted', child_returncode=process.poll(),
                          elapsed_seconds=time.perf_counter()-started)
            write_json(args.output / 'status.json', status)
            print('Parent interrupted; inspect child PID and retained logs. No automatic kill.', flush=True)
            return 130
    elapsed = time.perf_counter() - started
    result_path = args.output / 'native_result.json'
    result = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else dict(status='child_exited_without_result')
    result.update(child_returncode=code, child_process_wall_seconds=elapsed,
                  wall_scope='parent measured child startup, imports, input generation, simulation and child output; excludes parent final JSON write')
    write_json(args.output / 'result.json', result)
    status.update(status=result['status'], child_returncode=code, elapsed_seconds=elapsed,
                  finished_utc=datetime.now(timezone.utc).isoformat())
    write_json(args.output / 'status.json', status)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
