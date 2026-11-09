"""Recalculate fixed OD overlaps and verify matching without a simulation."""
import argparse,itertools,gzip,json
from collections import deque,Counter
from pathlib import Path
import numpy as np
import pandas as pd
from experiments.revision.R2_04_operational_metrics.workload import ROOT, specs, grid_for, plan_cases, build_workload, validate_workload, write_json, digest

def geometry_score(mp,s):
    grid=grid_for(mp).grid;V=[(x,y) for y in range(grid.shape[0]) for x in range(grid.shape[1]) if grid[y,x]==0];idx={p:i for i,p in enumerate(V)}
    adj=[[idx[q] for q in [(x+1,y),(x-1,y),(x,y+1),(x,y-1)] if q in idx] for x,y in V]
    def bfs(p):
        ds=np.full(len(V),999,dtype=int);count=[0]*len(V);u=idx[tuple(p)];ds[u]=0;count[u]=1;q=deque([u])
        while q:
            u=q.popleft()
            for v in adj[u]:
                if ds[v]>ds[u]+1:ds[v]=ds[u]+1;q.append(v)
                if ds[v]==ds[u]+1:count[v]+=count[u]
        return ds,np.asarray(count,float)
    O=list(map(tuple,s['origins']));D=list(map(tuple,s['destinations']));B={p:bfs(p) for p in O+D};interior=np.ones(len(V),bool)
    for p in O+D:interior[B[p][0]<=1]=False
    Q=[];L=[]
    for o in O:
        for d in D:
            a,ca=B[o];b,cb=B[d];dist=int(a[idx[d]]);prob=np.where(a+b==dist,ca*cb/ca[idx[d]],0);prob[~interior]=0;Q.append(prob);L.append(dist)
    Q=np.asarray(Q);L=np.array(L).reshape(8,8);G=Q@Q.T
    def score(perm):
        indices=np.arange(8)*8+perm;M=G[np.ix_(indices,indices)];return float((M.sum()-np.trace(M))/56)
    feasible=[]
    for perm in itertools.permutations(range(8)):
        if list(L[np.arange(8),perm])==s['distance_by_origin']:feasible.append((score(perm),list(perm)))
    feasible.sort();mid=(feasible[0][0]+feasible[-1][0])/2
    target={'dispersed':feasible[0][0],'intermediate':min(feasible,key=lambda z:abs(z[0]-mid))[0],'shared':feasible[-1][0]}
    rows=[]
    for level,info in s['levels'].items():
        perm=info['permutation'];value=score(perm);assert abs(value-info['reference_overlap'])<1e-10;assert abs(value-target[level])<1e-10
        assert list(L[np.arange(8),perm])==s['distance_by_origin']
        for i,j in enumerate(perm):rows.append(dict(map=mp,mode=level,origin=f'O{i+1}',destination=f'D{j+1}',pickup_x=O[i][0],pickup_y=O[i][1],dropoff_x=D[j][0],dropoff_y=D[j][1],shortest_distance=int(L[i,j]),requests_per_OD=375,reference_overlap=value))
    return rows,dict(map=mp,feasible_permutations=len(feasible),free_cells=len(V),scoring_cells=int(interior.sum()),distance_by_origin=s['distance_by_origin'],scores=target)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'validation/input_checks');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    pairs=[];geo=[]
    for mp,s in specs().items():rr,gg=geometry_score(mp,s);pairs.extend(rr);geo.append(gg)
    workloads=[]
    for c in plan_cases():
        for seed in [7,8,39,40,41,42,43]:
            w=build_workload(c,seed);validate_workload(w);workloads.append(w)
            frozen=ROOT/'prepared_inputs'/f'{c["name"]}_{seed}.json.gz'
            assert frozen.exists(),'Run prepare_inputs.py to restore missing packaged inputs'
            assert json.loads(gzip.decompress(frozen.read_bytes()))==w,'Prepared input differs from generated workload'
    for mp in specs():
      for seed in [7,8,39,40,41,42,43]:
        group=[w for w in workloads if w['case']['map']==mp and w['seed']==seed]
        for field in ['release_hash','pickup_hash']:assert len({w[field] for w in group})==1
        assert len({digest([r['intrinsic_distance'] for r in w['requests']]) for w in group})==1
        for n in sorted({w['case']['fleet'] for w in group}):assert len({w['initial_state_hash'] for w in group if w['case']['fleet']==n})==1
        lo,hi=sorted({w['case']['fleet'] for w in group});x=next(w for w in group if w['case']['fleet']==lo);y=next(w for w in group if w['case']['fleet']==hi)
        assert all(y['initial_positions'][k]==v for k,v in x['initial_positions'].items())
    pd.DataFrame(pairs).to_csv(a.output/'OD_PAIRINGS.csv',index=False)
    write_json(a.output/'input_checks.json',dict(passed=True,simulation_count=0,workloads_checked=len(workloads),geometry=geo,
        matched=['task count','all releases zero','origin sequence','per-request shortest OD distance','destination marginal counts','initial positions within fleet','initial position prefixes across fleets'],
        input_hashes=[dict(case=w['case']['name'],seed=w['seed'],workload_hash=w['workload_hash'],initial_parking_capacity=w['initial_parking_capacity']) for w in workloads]))
    print('PASS: geometry and',len(workloads),'full workloads; ZERO simulations.');print(pd.DataFrame(geo)[['map','feasible_permutations','free_cells','scoring_cells']].to_string(index=False))
if __name__=='__main__':main()
