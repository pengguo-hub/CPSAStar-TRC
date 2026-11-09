"""Post-run neutral exposure metrics; no feasibility or physical collision checks."""
from collections import Counter,deque

def neighborhoods(grid,radius):
    result={};h=len(grid);w=len(grid[0])
    for y in range(h):
        for x in range(w):
            if grid[y][x]:continue
            seen={(x,y)};todo=deque([((x,y),0)])
            while todo:
                (u,v),d=todo.popleft()
                if d==radius:continue
                for dx,dy in [(0,1),(1,0),(0,-1),(-1,0)]:
                    q=(u+dx,v+dy)
                    if 0<=q[0]<w and 0<=q[1]<h and grid[q[1]][q[0]]==0 and q not in seen:
                        seen.add(q);todo.append((q,d+1))
            result[(x,y)]=seen
    return result

def exposure_metrics(frames,grid):
    # Interval-start executed positions t=0,...,H-1, equal weights including idle AGVs.
    allpos=[{a:tuple(p) for a,p in f['positions'].items()} for f in frames]
    values={};n=len(allpos[0]);T=len(allpos)-1
    counts=[Counter(p.values()) for p in allpos]
    for radius in [1,2,3]:
        near=neighborhoods(grid,radius);total=0
        for pos,c in zip(allpos[:-1],counts[:-1]):
            total+=sum(sum(c.get(q,0) for q in near[p])-1 for p in pos.values())
        values[f'exposure_r{radius}']=total/(T*n)
        if radius==2:
            temporal=0
            for t,pos in enumerate(allpos[:-1]):
                ts=[u for u in [t-1,t,t+1] if 0<=u<T]
                temporal+=sum(sum(sum(counts[u].get(q,0) for q in near[p])-int(allpos[u][aid] in near[p]) for u in ts)/len(ts) for aid,p in pos.items())
            values['exposure_time_radius1']=temporal/(T*n)
    values['neutral_exposure']=values['exposure_r2']
    values['exposure_fraction_other']=values['exposure_r2']/(n-1) if n>1 else 0.
    return values
