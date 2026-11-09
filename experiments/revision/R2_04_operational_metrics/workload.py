"""Frozen geometry-only OD modes, 3000 balanced requests released at t=0."""
import hashlib,json,random
from pathlib import Path
from collections import Counter
from experiments.revision.R2_04_operational_metrics.original_runtime import load_original
load_original()
from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.benchmark_loader import GridMap
from experiments.revision.R2_04_operational_metrics.vendor.portable_vendor.experiment.Lifelong.map_config import ALL_MAPS
ROOT=Path(__file__).resolve().parent
SIZES={'STANDARD':(16,11),'FRANSEN':(20,20),'RING':(20,20)}
FLEETS={'STANDARD':[30,50],'FRANSEN':[100,200],'RING':[80,160]}
LEVELS=['dispersed','intermediate','shared']
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');q.replace(p)
def flatten(d):return [tuple(p) for v in d.values() for p in ([v] if isinstance(v,tuple) else v)]
def grid_for(name):
    w,h=SIZES[name];g=GridMap(w,h,1)
    for x,y in flatten(ALL_MAPS[name][0]):g.grid[y,x]=1
    return g
def specs():return json.loads((ROOT/'configs/od_patterns.json').read_text(encoding='utf-8'))['maps']
def plan_cases():
    return [dict(name=f'{m}_N{n}_{level}',map=m,fleet=n,horizon=500,mode='backlogged',arrival_rate=None,
                 concentration=None,od_mode=level,followup=500,initial_backlog=3000,tiles=1,
                 protocol='R2_04_fixed_OD_backlog3000_v1') for m,ns in FLEETS.items() for n in ns for level in LEVELS]
def build_workload(case,seed):
    c=dict(case);g=grid_for(c['map']);s=specs()[c['map']];free=[(x,y) for y in range(g.height) for x in range(g.width) if not g.grid[y,x]]
    endpoints=[tuple(p) for p in s['origins']+s['destinations']];buffer={q for x,y in endpoints for q in [(x,y),(x+1,y),(x-1,y),(x,y+1),(x,y-1)] if q in set(free)}
    parking=[p for p in free if p not in buffer];random.Random(seed+101).shuffle(parking)
    if len(parking)<c['fleet']:raise ValueError('Not enough unique initial cells outside the common endpoint buffer')
    initial=parking[:c['fleet']];rng=random.Random(seed+701);perm=s['levels'][c['od_mode']]['permutation'];requests=[]
    for block in range(375):
        order=list(range(8));rng.shuffle(order)
        for i in order:requests.append(dict(id=len(requests),release=0,pickup=s['origins'][i],dropoff=s['destinations'][perm[i]],origin_index=i,intrinsic_distance=s['distance_by_origin'][i]))
    w=dict(schema=3,case=c,seed=seed,width=g.width,height=g.height,map_grid=g.grid.tolist(),free_cells=len(free),initial_positions={f'agv_{i}':list(p) for i,p in enumerate(initial)},
           requests=requests,map_hash=digest(g.grid.tolist()),release_hash=digest([r['release'] for r in requests]),od_hash=digest([[r['pickup'],r['dropoff']] for r in requests]),
           pickup_hash=digest([r['pickup'] for r in requests]),initial_state_hash=digest(initial),od_spec_hash=digest(s),
           reference_overlap=s['levels'][c['od_mode']]['reference_overlap'],distance_by_origin=s['distance_by_origin'],origins=s['origins'],destinations=s['destinations'],initial_parking_capacity=len(parking))
    return dict(w,workload_hash=digest(w))
def validate_workload(w):
    assert digest({k:v for k,v in w.items() if k!='workload_hash'})==w['workload_hash']
    c=w['case'];g=grid_for(c['map']);s=specs()[c['map']];assert digest(g.grid.tolist())==w['map_hash'];assert w['od_spec_hash']==digest(s)
    assert c in plan_cases();assert len(w['requests'])==3000 and {r['release'] for r in w['requests']}=={0}
    assert [r['id'] for r in w['requests']]==list(range(3000));pos=list(w['initial_positions'].values());assert len(pos)==len(set(map(tuple,pos)))==c['fleet']
    assert Counter(r['origin_index'] for r in w['requests'])==Counter({i:375 for i in range(8)})
    assert Counter(tuple(r['dropoff']) for r in w['requests'])==Counter({tuple(p):375 for p in s['destinations']})
    for p in pos+[r[k] for r in w['requests'] for k in ['pickup','dropoff']]:assert 0<=p[0]<g.width and 0<=p[1]<g.height and g.grid[p[1],p[0]]==0
    for base in range(0,3000,8):assert {r['origin_index'] for r in w['requests'][base:base+8]}==set(range(8))
    return True
