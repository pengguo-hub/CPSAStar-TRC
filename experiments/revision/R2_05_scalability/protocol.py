"""Inputs only. Original task generator and loader; no route searches or feasibility prechecks."""
import math,random
import numpy as np
from experiments.revision.R2_05_scalability.common import ROOT, digest, read_json
from experiments.revision.R2_05_scalability.original_runtime import load_original

FORMAL_SEEDS=list(range(1001,1006))
SMOKE_SEEDS=[901]
HORIZON=500

def cases():
    def c(name,map='STANDARD',fleet=30,tiles=1,rate=.5,mode='poisson',axes=(),coupling=None):
        return dict(name=name,map=map,fleet=fleet,tiles=tiles,arrival_rate=rate,mode=mode,
                    horizon=500,warmup=0,axes=list(axes),traffic_coupling=coupling)
    out=[c('A_fleet30',fleet=30,mode='backlogged',rate=None,axes=['fleet']),
         c('A_fleet10',fleet=10,mode='backlogged',rate=None,axes=['fleet']),
         c('A_fleet50',fleet=50,mode='backlogged',rate=None,axes=['fleet']),
         c('A_open_base',axes=['map_fixed_fleet','map_fixed_density','arrival_rate']),
         c('A_map2_fixed',tiles=2,axes=['map_fixed_fleet']),
         c('A_map3_fixed',tiles=3,axes=['map_fixed_fleet']),
         c('A_map2_density',tiles=2,fleet=120,rate=2.,axes=['map_fixed_density']),
         c('A_map3_density',tiles=3,fleet=270,rate=4.5,axes=['map_fixed_density'])]
    out += [c('A_rate'+str(v),rate=v,axes=['arrival_rate']) for v in [.25,1.,2.]]
    out += [c('B_traffic_'+level,map='FRANSEN',fleet=8,axes=['traffic_coupling'],coupling=level)
            for level in ['dispersed','intermediate','shared']]
    return out

def make_loader(map_name,tiles=1):
    cls,_,_=load_original();loader=cls(map_name)
    if tiles>1:
        w,h=loader.width,loader.height
        def tiled(d):
            return {str(tx)+'_'+str(ty)+'_'+name:[(x+tx*w,y+ty*h) for x,y in ([coords] if isinstance(coords,tuple) else coords)]
                    for tx in range(tiles) for ty in range(tiles) for name,coords in d.items()}
        loader.shelf_map=tiled(loader.shelf_map);loader.outbound_map=tiled(loader.outbound_map)
        loader.width*=tiles;loader.height*=tiles
    return loader

def geometry(map_name,tiles=1):
    loader=make_loader(map_name,tiles);return loader,loader.load_map()

def endpoint_buffer(spec,grid):
    # Graph-radius-one service buffer is just endpoints + their four free neighbours.
    return {q for x,y in spec['origins']+spec['destinations'] for q in [(x,y),(x+1,y),(x-1,y),(x,y+1),(x,y-1)]
            if 0<=q[0]<grid.width and 0<=q[1]<grid.height and grid.grid[q[1],q[0]]==0}

def release_stream(seed,rate,horizon=500):
    rng=np.random.default_rng(np.random.SeedSequence([seed,401]));stream=[];candidate=0
    for t in range(horizon):
        n=int(rng.poisson(4.5))
        for mark in rng.random(n):
            if mark<rate/4.5:stream.append((candidate,t))
            candidate+=1
    return stream

def build_workload(case,seed):
    c=dict(case);loader,grid=geometry(c['map'],c['tiles'])
    info=loader.load_agv_info(c['fleet'],speed=1.)
    positions=loader.load_initial_positions(grid,c['fleet'],seed=seed,forbid_outbound=False)
    spec=read_json(ROOT/'configs/traffic_couplings.json')
    if c['mode']=='backlogged':
        # Exact source input construction for the original fleet conditions.
        q=loader.load_task_queue(grid,c['fleet'],seed=seed,max_tasks=100,repeat=30,pickup_strategy=None,pickup_region=None)
        requests=[dict(id=i,release=0,pickup=list(a),dropoff=list(b)) for i,(a,b) in enumerate(q)]
        protocol='original_100_repeated_30_all_at_t0'
    else:
        stream=release_stream(seed,c['arrival_rate'],c['horizon']);requests=[]
        if c['traffic_coupling']:
            parking=[(x,y) for y in range(grid.height) for x in range(grid.width)
                     if grid.grid[y,x]==0 and (x,y) not in endpoint_buffer(spec,grid)]
            random.Random(seed+101).shuffle(parking)
            positions={f'agv_{i}':p for i,p in enumerate(parking[:c['fleet']])}
            rng=random.Random(seed+701);full=(len(stream)//8)*8
            for base in range(0,len(stream),8):
                order=list(range(8));rng.shuffle(order)
                level=c['traffic_coupling'] if base<full else 'dispersed';perm=spec['levels'][level]['permutation']
                for j,(rid,t) in enumerate(stream[base:base+8]):
                    i=order[j]
                    requests.append(dict(id=rid,release=t,pickup=spec['origins'][i],dropoff=spec['destinations'][perm[i]],
                        origin_index=i,intrinsic_distance=spec['distance_by_origin'][i],coupling_applied=level,matched_full_motif=base<full))
            protocol='matched_couplings_v1'
        else:
            base_loader,base_grid=geometry('STANDARD',1)
            base=list(base_loader.load_task_queue(base_grid,30,seed=seed,max_tasks=100,repeat=1))
            tiles=random.Random(seed+703)
            for i,(rid,t) in enumerate(stream):
                tx,ty=int(tiles.random()*c['tiles']),int(tiles.random()*c['tiles'])
                a,b=base[i%100]
                requests.append(dict(id=rid,release=t,pickup=[a[0]+16*tx,a[1]+11*ty],
                                     dropoff=[b[0]+16*tx,b[1]+11*ty],base_index=i%100,tile=[tx,ty]))
            protocol='original_100_OD_cyclic_order_with_tile_offsets'
    w=dict(schema=1,case=c,seed=seed,width=grid.width,height=grid.height,grid=grid.grid.tolist(),
           initial_positions={a:list(p) for a,p in positions.items()},agv_info=info,
           requests=requests,free_cells=int((grid.grid==0).sum()),map_hash=digest(grid.grid.tolist()),od_protocol=protocol,
           release_hash=digest([[r['id'],r['release']] for r in requests]),
           pickup_hash=digest([r['pickup'] for r in requests]),
           initial_positions_hash=digest({a:list(p) for a,p in positions.items()}))
    w['workload_hash']=digest(w);return w
