"""R2-07 inputs, using the authoritative CustomBenchmarkLoader body unchanged."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from experiments.revision.R2_07_factorial_ablation.reference_inputs.custom_benchmark_loader import CustomBenchmarkLoader

ROOT=Path(__file__).resolve().parent
SIZES={'STANDARD':(16,11),'FRANSEN':(20,20),'RING':(20,20)}
MID={'STANDARD':50,'FRANSEN':150,'RING':120}
BASELINE='S1_L0_P1_R1'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    tmp.replace(path)

def grid_for(map_name,tiles=1):
    assert tiles==1,'R2-07 uses original maps only'
    with contextlib.redirect_stdout(io.StringIO()):return CustomBenchmarkLoader(map_name).load_map()

def case(name,map_name,fleet,horizon,mode='backlog',backlog=3000,**unused):
    assert mode=='backlog'
    return dict(name=name,map=map_name,fleet=fleet,horizon=horizon,warmup=0,mode='backlog',backlog=backlog,tiles=1)

def build_workload(c,seed):
    assert c['mode']=='backlog' and c['warmup']==0 and c['tiles']==1
    with contextlib.redirect_stdout(io.StringIO()):
        grid,info,positions,queue=CustomBenchmarkLoader(c['map']).load_all(
            num_agvs=c['fleet'],speed=1.,seed=seed,max_tasks=100,repeat=30,
            forbid_outbound_init=False,pickup_strategy=None,pickup_region=None)
    queue=list(queue)
    if not 0<c['backlog']<=len(queue):raise ValueError('Invalid backlog')
    requests=[dict(id=i,release=0,pickup=list(p),dropoff=list(d)) for i,(p,d) in enumerate(queue[:c['backlog']])]
    data=dict(case=c,seed=seed,initial_positions={a:list(p) for a,p in positions.items()},
        requests=requests,base_request_pool=[[list(a),list(b)] for a,b in queue[:100]],
        map_hash=digest(grid.grid.tolist()),free_cells=int((grid.grid==0).sum()),width=grid.width,height=grid.height)
    return dict(data,workload_hash=digest(data))

def plan_cases(revision='R2-07',smoke=False):
    assert revision=='R2-07'
    cfg=json.loads((ROOT/'configs/experiment.json').read_text(encoding='utf-8'))
    if smoke:return [case('A_backlog','STANDARD',10,24,backlog=40)]
    return cfg['cases']

def variants():
    import itertools
    return [dict(name=f'S{s}_L{l}_P{p}_R{r}',S=s,L=l,P=p,R=r) for s,l,p,r in itertools.product([0,1],repeat=4)]
