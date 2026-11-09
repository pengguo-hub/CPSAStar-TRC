#!/usr/bin/env python3
"""Prepare DISJOINT historical and learned-prediction congestion representations.

Calibration data are generated on independent seeds with the same maps/task generator but a
collision-only controlled planner (no soft congestion term, rollback off).  This avoids training
or constructing the indirect baselines from the proposed Gaussian CPS-A itself.

Outputs:
  historical_<map>_<load>.npz : mean RAW occupancy E[psi(x,y,t)] from calibration episodes
  learned_<map>.pt             : conditional predictor of RAW occupancy from current task demand
At experiment time BOTH are passed through the SAME Gaussian kernel as exact CPS-A.
"""
from __future__ import annotations
import argparse
import json
import random
import time
from dataclasses import replace
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader

from config import Config, MAPS
from instances import build_instance, build_grid, parsed_tasks, agv_info, canonical_hash, write_json, seed_all
from controlled_search import Budget
from controlled_planner import ControlledPlanner
from learned_prediction import LearnedOccupancyPredictor, task_demand_array

ROOT = Path(__file__).resolve().parent

def occupancy_dense(records, height, width, horizon):
    arr = np.zeros((horizon + 1, height, width), dtype=np.float32)
    for item in records.values():
        for (x, y), t in zip(item["path"], item["times"]):
            ti = int(t)
            if 0 <= ti <= horizon and 0 <= x < width and 0 <= y < height:
                arr[ti, y, x] = 1.0  # collision-free occupancy: at most one AGV per cell/time
    return arr


def calibration_episode(map_name, load, seed, config, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{map_name}_{load}_{seed}.npz"
    meta_path = cache_dir / f"{map_name}_{load}_{seed}.json"
    identity = canonical_hash(dict(version=2, map=map_name, load=load, seed=seed,
                                   config=config.to_dict(), generator="collision_only_controlled_planner"))
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("identity") != identity:
            raise ValueError(f"Calibration cache protocol changed: {path}")
        z = np.load(path, allow_pickle=False)
        return z["occupancy"], z["demand"], meta

    instance = build_instance(map_name, seed, load, config)
    tasks = instance["tasks"][:load]
    seed_all(seed)
    grid = build_grid(map_name)
    planner = ControlledPlanner(grid, agv_info(tasks, config), "no_field", config, Budget(config.timeout),
                                map_name=map_name, field_context=None)
    planner.batch_plan(parsed_tasks(tasks), rollback=False)
    records = {aid: dict(path=info["path"], times=info["times"])
               for aid, info in planner.agv_tasks.items() if info.get("path")}
    occupancy = occupancy_dense(records, grid.height, grid.width, config.reference_horizon)
    demand = task_demand_array(tasks, grid.height, grid.width)
    np.savez_compressed(path, occupancy=occupancy, demand=demand)
    meta = dict(identity=identity, map=map_name, load=load, calibration_seed=seed,
                task_seed=instance["task_seed"], task_hash=canonical_hash(tasks),
                success_count=len(records), task_count=load, timed_out=bool(planner.timeout),
                generator="collision_only_controlled_planner", rollback="off",
                soft_congestion="none", created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    write_json(meta_path, meta)
    return occupancy, demand, meta


def train_map_model(map_name, episodes, grid, output, config, epochs, batch_size, hidden, samples_per_episode, train_seed):
    rng = np.random.default_rng(train_seed + ord(map_name))
    X, T, Y, episode_ids = [], [], [], []
    for ep_id, (occ, demand, meta) in enumerate(episodes):
        # Deterministic time sampling; include t=0 and spread samples over occupied horizon.
        active = np.flatnonzero(occ.reshape(occ.shape[0], -1).sum(axis=1) > 0)
        max_t = int(active.max()) if len(active) else 0
        candidate = np.unique(np.linspace(0, max(1, max_t), samples_per_episode, dtype=int))
        if len(candidate) < samples_per_episode:
            extra = rng.integers(0, max(2, max_t + 1), size=samples_per_episode-len(candidate))
            candidate = np.unique(np.concatenate([candidate, extra]))
        for t in candidate[:samples_per_episode]:
            X.append(demand)
            T.append(float(t) / config.reference_horizon)
            Y.append(occ[int(t)])
            episode_ids.append(ep_id)
    X = torch.from_numpy(np.asarray(X, np.float32))
    T = torch.from_numpy(np.asarray(T, np.float32))
    Y = torch.from_numpy(np.asarray(Y, np.float32))[:, None]
    episode_ids = np.asarray(episode_ids)
    if len(X) < 2:
        raise ValueError("Too few learned-predictor training samples")

    # Split by EPISODE, not time slices, so validation cannot leak another t from the same run.
    unique_eps = np.arange(len(episodes))
    rng.shuffle(unique_eps)
    n_val = max(1, int(round(0.2 * len(unique_eps)))) if len(unique_eps) > 2 else 1
    val_eps = set(unique_eps[:n_val].tolist())
    val_mask = np.array([e in val_eps for e in episode_ids])
    if val_mask.all(): val_mask[0] = False
    if (~val_mask).sum() == 0: val_mask[-1] = True

    train_ds = TensorDataset(X[~torch.from_numpy(val_mask)], T[~torch.from_numpy(val_mask)], Y[~torch.from_numpy(val_mask)])
    val_ds = TensorDataset(X[torch.from_numpy(val_mask)], T[torch.from_numpy(val_mask)], Y[torch.from_numpy(val_mask)])
    generator = torch.Generator().manual_seed(train_seed + ord(map_name))
    loader = DataLoader(train_ds, batch_size=min(batch_size, len(train_ds)), shuffle=True, generator=generator)
    vloader = DataLoader(val_ds, batch_size=min(batch_size, len(val_ds)), shuffle=False)

    torch.manual_seed(train_seed + ord(map_name))
    model = LearnedOccupancyPredictor(grid.height, grid.width, hidden=hidden)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    free = torch.from_numpy((grid.grid == 0).astype(np.float32))[None, None]
    history = []
    for epoch in range(epochs):
        model.train(); losses=[]
        for xb, tb, yb in loader:
            opt.zero_grad()
            pred = model(xb, tb, free)
            # Occupancy is sparse: positive states receive extra weight, but target remains raw occupancy.
            weight = 1.0 + 4.0 * yb
            loss = ((pred-yb)**2 * weight).mean()
            loss.backward(); opt.step(); losses.append(float(loss.detach()))
        model.eval(); vals=[]
        with torch.no_grad():
            for xb,tb,yb in vloader:
                pred=model(xb,tb,free); vals.append(float((((pred-yb)**2)*(1+4*yb)).mean()))
        history.append(dict(epoch=epoch+1, train_loss=float(np.mean(losses)), val_loss=float(np.mean(vals))))

    calibration_seeds=sorted({int(meta["calibration_seed"]) for _,_,meta in episodes})
    metadata=dict(map=map_name,height=grid.height,width=grid.width,hidden=hidden,
                  calibration_seeds=calibration_seeds,
                  label_generator="collision_only_controlled_planner",label_representation="raw_occupancy",
                  inputs=["current_task_start_count","current_task_pickup_count","current_task_destination_count","x","y","normalized_time","obstacle_mask"],
                  gaussian_applied_after_prediction=True,reference_horizon=config.reference_horizon,
                  samples_per_episode=samples_per_episode,epochs=epochs,train_seed=train_seed,
                  final_train_loss=history[-1]["train_loss"],final_val_loss=history[-1]["val_loss"],
                  note="Conditional learned prediction; test instances are never used for training.")
    torch.save(dict(state_dict=model.state_dict(),metadata=metadata,history=history), output/f"learned_{map_name}.pt")
    write_json(output/f"learned_{map_name}.json", metadata)


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"reference_artifacts")
    p.add_argument("--calibration-seeds",type=int,default=30)
    p.add_argument("--calibration-seed-start",type=int,default=10000)
    p.add_argument("--epochs",type=int,default=40)
    p.add_argument("--samples-per-episode",type=int,default=10)
    p.add_argument("--batch-size",type=int,default=32)
    p.add_argument("--hidden",type=int,default=24)
    p.add_argument("--timeout",type=float,default=None)
    p.add_argument("--maps",choices=list(MAPS),nargs="+")
    p.add_argument("--smoke",action="store_true")
    p.add_argument("--force",action="store_true",help="Regenerate final reference artifacts even if an identical complete set already exists")
    a=p.parse_args()
    config=Config()
    if a.timeout is not None: config=replace(config,timeout=a.timeout)
    if a.smoke:
        a.calibration_seeds=min(a.calibration_seeds,2);a.epochs=min(a.epochs,1);a.samples_per_episode=min(a.samples_per_episode,3)
    config.validate()
    seeds=list(range(a.calibration_seed_start,a.calibration_seed_start+a.calibration_seeds))
    maps=a.maps or (["A"] if a.smoke else list(MAPS))
    a.output.mkdir(parents=True,exist_ok=True);cache=a.output/"calibration_cache"
    plan=dict(config=config.to_dict(),maps=maps,calibration_seeds=seeds,
              loads={m:([20] if a.smoke else MAPS[m]["loads"]) for m in maps},
              generator="collision_only_controlled_planner",rollback="off",soft_congestion="none",
              learned_epochs=a.epochs,samples_per_episode=a.samples_per_episode,hidden=a.hidden,smoke=a.smoke)
    manifest_path=a.output/"preparation_manifest.json"
    expected=[]
    for m in maps:
        for load in plan["loads"][m]:
            expected += [a.output/f"historical_{m}_{load}.npz", a.output/f"historical_{m}_{load}.json"]
        expected += [a.output/f"learned_{m}.pt", a.output/f"learned_{m}.json"]
    if manifest_path.exists() and not a.force:
        existing=json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != plan:
            raise ValueError("Reference directory contains a different preparation protocol. Use a new --output directory or --force.")
        if all(x.exists() for x in expected):
            print(f"Reference artifacts already complete; reusing without regenerating/training: {a.output}")
            return
    write_json(manifest_path,plan)
    for m in maps:
        grid=build_grid(m);map_episodes=[]
        for load in plan["loads"][m]:
            occs=[];metas=[]
            for seed in seeds:
                print(f"calibration {m} load={load} seed={seed}",flush=True)
                occ,demand,meta=calibration_episode(m,load,seed,config,cache)
                occs.append(occ);metas.append(meta);map_episodes.append((occ,demand,meta))
            hist=np.mean(np.stack(occs),axis=0).astype(np.float32)
            np.savez_compressed(a.output/f"historical_{m}_{load}.npz",raw_expected_occupancy=hist)
            hmeta=dict(map=m,load=load,calibration_seeds=seeds,
                       generator="collision_only_controlled_planner",rollback="off",soft_congestion="none",
                       value_semantics="mean raw occupancy E[psi(x,y,t)] in occupancy-count units",
                       gaussian_applied_at_test_time=True,reference_horizon=config.reference_horizon,
                       calibration_success_rate=float(sum(x["success_count"] for x in metas)/(load*len(metas))),
                       calibration_timeout_count=sum(bool(x["timed_out"]) for x in metas))
            write_json(a.output/f"historical_{m}_{load}.json",hmeta)
        train_map_model(m,map_episodes,grid,a.output,config,a.epochs,a.batch_size,a.hidden,a.samples_per_episode,20261022)
    print(f"Prepared reference artifacts: {a.output}")

if __name__=="__main__": cli()
