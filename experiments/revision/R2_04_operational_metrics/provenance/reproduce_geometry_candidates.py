"""Reproduce pre-smoke geometry screening only; no planner runs."""
import sys,itertools,json,collections,time
from pathlib import Path
import numpy as np
pass  # Package imports replace process-wide import-path mutation.
from experiments.revision.R2_04_operational_metrics.workload import grid_for

def prepare(mp,O,D):
 g=grid_for(mp).grid;V=[(x,y) for y in range(g.shape[0]) for x in range(g.shape[1]) if g[y,x]==0];ix={p:i for i,p in enumerate(V)};adj=[[ix[q] for q in [(x+1,y),(x-1,y),(x,y+1),(x,y-1)] if q in ix] for x,y in V]
 def bfs(p):
  dist=np.full(len(V),999,dtype=int);cnt=[0]*len(V);s=ix[p];dist[s]=0;cnt[s]=1;q=collections.deque([s])
  while q:
   u=q.popleft()
   for v in adj[u]:
    if dist[v]>dist[u]+1:dist[v]=dist[u]+1;q.append(v)
    if dist[v]==dist[u]+1:cnt[v]+=cnt[u]
  return dist,np.array(cnt,dtype=float)
 b={p:bfs(p) for p in O+D};mask=np.ones(len(V),bool)
 for p in O+D:mask[b[p][0]<=1]=False
 vectors=[];lengths=[]
 for o in O:
  for d in D:
   a,na=b[o];z,nz=b[d];L=a[ix[d]];v=np.where(a+z==L,na*nz/na[ix[d]],0);v[~mask]=0;vectors.append(v);lengths.append(L)
 vectors=np.array(vectors);G=vectors@vectors.T;L=np.array(lengths).reshape(len(O),len(D));return G,L,len(V),int(mask.sum())
def design(mp,O,D,match='origin'):
 O=list(map(tuple,O));D=list(map(tuple,D));G,L,free,inter=prepare(mp,O,D);n=len(O);groups={};idx=np.arange(n)*n
 for perm in itertools.permutations(range(n)):
  ds=L[np.arange(n),perm];key=tuple(ds) if match=='origin' else tuple(sorted(ds));j=idx+perm;mat=G[np.ix_(j,j)];score=(mat.sum()-np.trace(mat))/(n*(n-1));groups.setdefault(key,[]).append((score,perm))
 candidates=[]
 for key,ls in groups.items():
  if len(ls)<3:continue
  ls.sort();spread=ls[-1][0]-ls[0][0]
  # Absolute overlap span per mean reference travel length, purely geometric.
  if spread>1e-8:candidates.append((spread/np.mean(key),spread,key,ls))
 if not candidates:return dict(map=mp,match=match,none=True)
 norm,spread,key,ls=max(candidates,key=lambda x:(x[0],x[1],x[2]));mid=min(ls,key=lambda z:abs(z[0]-(ls[0][0]+ls[-1][0])/2))
 return dict(map=mp,match=match,origins=O,destinations=D,distance_labels=list(map(int,key)),free_cells=free,interior_cells=inter,feasible_permutations=len(ls),normalized_span=norm,overlap_span=spread,levels={k:dict(reference_overlap=float(v[0]),permutation=v[1]) for k,v in zip(['dispersed','intermediate','shared'],[ls[0],mid,ls[-1]])})
sets={
'STANDARD':[
 ([(2,2),(4,2),(10,2),(12,2),(2,8),(4,8),(10,8),(12,8)],[(0,0),(4,0),(10,0),(14,0),(0,10),(4,10),(10,10),(14,10)]),
 ([(0,2),(4,2),(8,2),(12,2),(0,8),(4,8),(8,8),(12,8)],[(2,0),(6,0),(10,0),(14,0),(2,10),(6,10),(10,10),(14,10)]),
 ([(0,2),(2,2),(4,2),(6,2),(0,8),(2,8),(4,8),(6,8)],[(8,0),(10,0),(12,0),(14,0),(8,10),(10,10),(12,10),(14,10)])],
'RING':[
 ([(3,7),(3,12),(16,7),(16,12),(7,3),(12,3),(7,16),(12,16)],[(8,8),(11,8),(8,11),(11,11),(9,8),(10,11),(8,9),(11,10)]),
 ([(1,5),(1,14),(18,5),(18,14),(5,1),(14,1),(5,18),(14,18)],[(6,6),(13,6),(6,13),(13,13),(8,8),(11,8),(8,11),(11,11)]),
 ([(3,5),(3,14),(16,5),(16,14),(5,3),(14,3),(5,16),(14,16)],[(1,9),(1,10),(18,9),(18,10),(9,1),(10,1),(9,18),(10,18)])]}
all=[]
for mp,choices in sets.items():
 for k,(O,D) in enumerate(choices):
  for match in ['origin']:
   r=design(mp,O,D,match);r['set']=k;all.append(r);print(json.dumps(r),flush=True)
Path('reproduced_geometry_candidates.json').write_text(json.dumps(all,indent=2))
