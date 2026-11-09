"""Only FRANSEN: N=200, 3000 matched-OD tasks at t=0, 500 steps. No timeout."""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Install next to the existing run.py. No existing module is replaced or monkey-patched.
HERE = Path(__file__).resolve().parent
try:
    from experiments.revision.R2_05_scalability.common import ROOT, read_json, write_json, digest, execution_hash, execution_sources
    from experiments.revision.R2_05_scalability.protocol import geometry, endpoint_buffer
    from experiments.revision.R2_05_scalability.run import check_gate
except ModuleNotFoundError as exc:
    raise SystemExit('Place the add-on files in the original R2-05 project root beside run.py and worker.py; do not place them inside results_formal/.') from exc

CONFIG = HERE / 'fransen_backlog_config.json'
REFERENCE = HERE / 'fransen_backlog_reference.json'
ADDON_INPUTS = ['run_fransen_backlog.py', 'fransen_backlog_config.json', 'fransen_backlog_reference.json']


def addon_sources():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in ADDON_INPUTS}


def verify_version():
    ref = read_json(REFERENCE)
    actual = execution_sources()
    if actual != ref['source_files'] or execution_hash() != ref['execution_hash']:
        differences = sorted(k for k in set(actual) | set(ref['source_files']) if actual.get(k) != ref['source_files'].get(k))
        raise RuntimeError('Project differs from the runtime recorded in R2_5_results_formal.zip: ' + ', '.join(differences))
    gate = check_gate()  # Existing original baseline evidence remains valid for the UNCHANGED core.
    manifest = read_json(HERE / 'FRANSEN_BACKLOG_PATCH_MANIFEST.json')
    for row in manifest['files']:
        p = HERE / row['path']
        if not p.is_file() or p.stat().st_size != row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError('Add-on file differs from delivery: ' + row['path'])
    cfg = read_json(CONFIG)
    if (cfg['map'], cfg['fleet'], cfg['tasks'], cfg['horizon'], cfg['warmup'], cfg['mode'], cfg['arrival_rate']) != ('FRANSEN', 200, 3000, 500, 0, 'backlogged', None):
        raise RuntimeError('This add-on is frozen to FRANSEN / 200 / 3000 / 500 / no warm-up / no lambda.')
    return cfg, gate


def condition(level, cfg):
    return dict(name='B_traffic_' + level, map='FRANSEN', fleet=cfg['fleet'], tiles=1,
                arrival_rate=None, mode='backlogged', horizon=cfg['horizon'], warmup=0,
                axes=['traffic_coupling'], traffic_coupling=level, initial_tasks=cfg['tasks'],
                input_protocol_id=cfg['experiment_id'])


def build_workload(c, seed, cfg):
    loader, grid = geometry('FRANSEN', 1)
    coupling = read_json(ROOT / 'configs/traffic_couplings.json')
    info = loader.load_agv_info(c['fleet'], speed=1.)
    excluded = endpoint_buffer(coupling, grid)
    parking = [(x, y) for y in range(grid.height) for x in range(grid.width)
               if grid.grid[y, x] == 0 and (x, y) not in excluded]
    # Input capacity assertion only: no route search or planner feasibility precheck.
    if c['fleet'] > len(parking):
        raise ValueError('Insufficient initial free cells outside the common service buffer')
    random.Random(seed + cfg['initial_position_rng_offset']).shuffle(parking)
    positions = {f'agv_{i}': p for i, p in enumerate(parking[:c['fleet']])}
    n = cfg['tasks']; block = cfg['task_block_size']
    assert block == len(coupling['origins']) == len(coupling['destinations']) == 8 and n % block == 0
    rng = random.Random(seed + cfg['origin_order_rng_offset'])
    level = c['traffic_coupling']; perm = coupling['levels'][level]['permutation']
    requests = []
    for base in range(0, n, block):
        order = list(range(block)); rng.shuffle(order)
        for j, i in enumerate(order):
            requests.append(dict(id=base+j, release=0, pickup=coupling['origins'][i],
                                 dropoff=coupling['destinations'][perm[i]], origin_index=i,
                                 intrinsic_distance=coupling['distance_by_origin'][i],
                                 coupling_applied=level, matched_full_motif=True))
    w = dict(schema=1, case=c, seed=seed, width=grid.width, height=grid.height, grid=grid.grid.tolist(),
             initial_positions={a:list(p) for a,p in positions.items()}, agv_info=info,
             requests=requests, free_cells=int((grid.grid == 0).sum()), map_hash=digest(grid.grid.tolist()),
             od_protocol='matched_couplings_backlogged_375_blocks_v1',
             release_hash=digest([[r['id'],r['release']] for r in requests]),
             pickup_hash=digest([r['pickup'] for r in requests]),
             initial_positions_hash=digest({a:list(p) for a,p in positions.items()}),
             input_builder_sources=addon_sources(), reference_runtime_hash=execution_hash())
    w['workload_hash'] = digest(w)
    return w


def validate_inputs(workloads):
    checks = []
    for w in workloads:
        r = w['requests']; c = w['case']; level = c['traffic_coupling']
        assert len(r) == 3000 and {x['release'] for x in r} == {0}
        assert len(w['agv_info']) == len(w['initial_positions']) == len(set(map(tuple,w['initial_positions'].values()))) == 200
        assert Counter(x['origin_index'] for x in r) == Counter({i:375 for i in range(8)})
        assert set(Counter(tuple(x['dropoff']) for x in r).values()) == {375}
        assert all(x['coupling_applied'] == level and x['matched_full_motif'] for x in r)
        assert w['workload_hash'] == digest({k:v for k,v in w.items() if k != 'workload_hash'})
        checks.append(dict(case=c['name'],seed=w['seed'],agents=200,tasks=3000,release_times=[0],
                           full_blocks=375,lambda_used=False,workload_hash=w['workload_hash']))
    for seed in sorted({w['seed'] for w in workloads}):
        group = [w for w in workloads if w['seed'] == seed]
        for field in ['map_hash','release_hash','pickup_hash','initial_positions_hash']:
            assert len({w[field] for w in group}) == 1, (seed, field)
        for w in group[1:]:
            assert Counter(tuple(r['dropoff']) for r in w['requests']) == Counter(tuple(r['dropoff']) for r in group[0]['requests'])
            assert [r['intrinsic_distance'] for r in w['requests']] == [r['intrinsic_distance'] for r in group[0]['requests']]
    return checks


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--all', action='store_true', help='All three pairings x five matched seeds: 15 trials only')
    mode.add_argument('--level', choices=['dispersed','intermediate','shared'], help='Exactly one pairing')
    p.add_argument('--seed', type=int, help='Exactly one seed with --level; defaults to 1001')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dry-run', action='store_true', help='Save and verify inputs; execute zero trials')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--retry-incomplete', action='store_true')
    p.add_argument('--stop-after', type=int, help='Pause BETWEEN completed trials, never within a trial')
    a = p.parse_args()
    if a.all and a.seed is not None: p.error('--seed is for --level only; --all uses the original five seeds')
    if a.retry_incomplete and not a.resume: p.error('--retry-incomplete needs --resume')
    if a.stop_after is not None and a.stop_after < 1: p.error('--stop-after must be positive')
    return a


def main():
    a = parse_args(); cfg, gate = verify_version()
    levels = cfg['levels'] if a.all else [a.level]
    seeds = cfg['seeds'] if a.all else [a.seed if a.seed is not None else 1001]
    if not set(seeds) <= set(cfg['seeds']): raise ValueError('Use a recorded formal seed from 1001 to 1005')
    cases = [condition(level,cfg) for level in levels]
    spec = dict(schema=1,purpose='formal',experiment_id=cfg['experiment_id'],cases=cases,seeds=seeds,
                horizon=500,warmup=0,trial_timeout=None,execution_hash=execution_hash(),source_files=execution_sources(),
                input_builder_sources=addon_sources(),baseline_gate=gate,
                baseline_evidence_scope='Unchanged original core; this new N200 OD/backlog workload has not been formally run in delivery',
                planned_trials=[dict(case=c['name'],seed=s) for c in cases for s in seeds])
    out = a.output.resolve()
    if (out/'manifest.json').exists():
        if not a.resume: raise ValueError('Output exists; use --resume with the same selection, or a new directory')
        manifest = read_json(out/'manifest.json')
        if digest(manifest['spec']) != digest(spec): raise ValueError('Resume protocol/hash mismatch; do not mix the old N8/Poisson runs with N200/backlog runs')
        workloads = []
        for trial in manifest['trials']:
            w = read_json(out/trial['workload'])
            assert w['workload_hash'] == trial['workload_hash']; workloads.append(w)
    else:
        if out.exists() and any(out.iterdir()): raise ValueError('Refusing to overwrite a nonempty directory')
        out.mkdir(parents=True,exist_ok=True)
        manifest = dict(spec=spec,created_utc=datetime.now(timezone.utc).isoformat(),trials=[]); workloads=[]
        for c in cases:
            for seed in seeds:
                key = c['name']+'__seed'+str(seed); rel = 'workloads/'+key+'.json'
                w = build_workload(c,seed,cfg); workloads.append(w); write_json(out/rel,w)
                manifest['trials'].append(dict(key=key,case=c['name'],seed=seed,workload=rel,workload_hash=w['workload_hash'],state='planned',attempts=[]))
        write_json(out/'manifest.json',manifest)
    write_json(out/'input_checks.json',dict(passed=True,checks=validate_inputs(workloads)))
    print(f'FRANSEN ONLY: {len(manifest["trials"])} trial(s), 200 AGVs, 3000 initial tasks, 500 steps, no lambda, no warm-up, no trial timeout.',flush=True)
    if a.dry_run:
        print('DRY RUN: inputs and plan saved; ZERO simulations executed.',flush=True); return 0
    completed = 0
    for trial in manifest['trials']:
        previous = [x for x in trial['attempts'] if x.get('state') == 'completed']
        if previous:
            r = read_json(out/previous[0]['directory']/'result.json')['row']
            if not (r.get('eligible') and r.get('execution_hash') == execution_hash() and r.get('workload_hash') == trial['workload_hash']):
                raise RuntimeError('Saved result differs from its verified trial identity')
            print('SKIP completed',trial['key'],flush=True); continue
        if trial['attempts'] and not a.retry_incomplete:
            print('Retained incomplete attempt; inspect logs/PID before --resume --retry-incomplete.',flush=True); return 2
        folder = Path('trials')/trial['key']/('attempt_%02d' % (len(trial['attempts'])+1)); dest = out/folder
        dest.mkdir(parents=True,exist_ok=False)
        write_json(dest/'job.json',dict(workload=str((out/trial['workload']).resolve()),output=str(dest.resolve()),purpose='formal'))
        attempt = dict(directory=folder.as_posix(),state='running',started_utc=datetime.now(timezone.utc).isoformat())
        trial['attempts'].append(attempt); trial['state']='running'; write_json(out/'manifest.json',manifest)
        start=time.perf_counter(); print('START',trial['key'],flush=True)
        with (dest/'native.log').open('w',encoding='utf-8',buffering=1) as log:
            env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
            process=subprocess.Popen([sys.executable,'-u','-m','experiments.revision.R2_05_scalability.worker','--job',str(dest/'job.json')],cwd=ROOT.parents[2],stdout=log,stderr=subprocess.STDOUT,env=env)
            attempt['pid']=process.pid; write_json(out/'manifest.json',manifest)
            try: code=process.wait()  # Deliberately no timeout or automatic kill.
            except KeyboardInterrupt:
                attempt.update(state='parent_interrupted',returncode=process.poll(),elapsed_seconds=time.perf_counter()-start)
                trial['state']='interrupted';write_json(out/'manifest.json',manifest)
                print('Interrupted; logs/PID retained. Check whether the worker is still running before retrying.',flush=True);return 130
        elapsed=time.perf_counter()-start
        attempt.update(returncode=code,elapsed_seconds=elapsed,finished_utc=datetime.now(timezone.utc).isoformat())
        if (dest/'result.json').exists():
            result=read_json(dest/'result.json');result['row'].update(trial_wall_seconds=elapsed,worker_returncode=code,
                input_builder_hash=digest(addon_sources()),experiment_id=cfg['experiment_id'])
            write_json(dest/'result.json',result)
            state='completed' if code==0 and result['row'].get('eligible') else result['row'].get('status','error')
        else:state='exited_without_result'
        attempt['state']=trial['state']=state;write_json(out/'manifest.json',manifest)
        print('END',trial['key'],state,'wall=%.2fs'%elapsed,flush=True)
        if state!='completed':return 2
        completed+=1
        if a.stop_after is not None and completed>=a.stop_after:
            print('Paused BETWEEN completed trials; resume with the same selection.',flush=True);return 0
    print('Done. Analyze with: python analyze.py --input '+str(out),flush=True)
    return 0


if __name__=='__main__': raise SystemExit(main())
