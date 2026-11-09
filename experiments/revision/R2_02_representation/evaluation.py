"""Post-hoc evaluation for the direct one-shot representation comparison."""
from collections import defaultdict
import numpy as np
from vendor.CPS_A.Conflict_Field_Updater import ConflictFieldUpdater
from vendor.CPS_A.Ticket_Manager import TicketManager
from vendor.CPS_A.Segment_Planner import SegmentPlanner

PATH_METRICS = ["path_length","path_duration","wait_steps","neutral_congestion_exposure","turns"]
RUN_METRICS = ["success_rate","planning_time","search_and_update_time","field_initialization_time",
               "avg_path_length","avg_path_duration","avg_wait_steps","neutral_congestion_exposure",
               "avg_turns","gaussian_AC"]


def raw_occupancy(paths):
    result = defaultdict(int)
    for item in paths.values():
        for p,t in zip(item["path"],item["times"]):
            result[(int(p[0]),int(p[1]),int(t))] += 1
    return result


def exposure_values(path,times,occupancy,radius,time_radius,own=None):
    offsets = [(x,y,s) for x in range(-radius,radius+1) for y in range(-radius,radius+1)
               if abs(x)+abs(y)<=radius for s in range(-time_radius,time_radius+1)]
    values = []
    for (x,y),t in zip(path,times):
        total = 0
        for dx,dy,ds in offsets:
            key=(x+dx,y+dy,int(t)+ds)
            total += occupancy.get(key,0) - (own.get(key,0) if own is not None else 0)
        values.append(total/len(offsets))
    return values


def gaussian_from_records(grid, records):
    tickets = TicketManager()
    updater = ConflictFieldUpdater(grid,tickets)
    planner = SegmentPlanner(grid,tickets,updater)
    for aid,item in records.items():
        path=[tuple(p) for p in item["path"]]
        if not planner._reserve_tickets(aid,path,item["times"],1.0):
            raise AssertionError("Evaluation received conflicting node or directed-edge reservations")
        updater.accumulate_path(path,item["times"],aid)
    updater.batch_update_from_paths()
    return updater.smoothed_dict


def validate_paths(grid,paths):
    """Independent node, reverse-edge, timing, and obstacle validator."""
    nodes,edges={},{}
    for aid,item in paths.items():
        path=[tuple(p) for p in item["path"]];times=item["times"]
        assert len(path)==len(times) and path
        for i,(p,t) in enumerate(zip(path,times)):
            assert 0<=p[0]<grid.width and 0<=p[1]<grid.height and grid.grid[p[1],p[0]]==0
            assert float(t).is_integer() and t>=0
            assert (p,t) not in nodes, f"node conflict: {aid} and {nodes.get((p,t))}"
            nodes[(p,t)]=aid
            if i:
                prev=path[i-1];start=times[i-1]
                assert t-start==1, "Only speed=delta=1 is validated by this protocol"
                assert abs(p[0]-prev[0])+abs(p[1]-prev[1])<=1
                if p!=prev:
                    assert (p,prev,start) not in edges, f"reverse-edge conflict: {aid}"
                    assert (prev,p,start) not in edges
                    edges[(prev,p,start)]=aid
    return dict(node_conflicts=0,edge_conflicts=0,checked_agents=len(paths))


def evaluate(grid,tasks,planned,config):
    validation=validate_paths(grid,planned)
    all_raw=raw_occupancy(planned)
    fixed_gaussian=gaussian_from_records(grid,planned)
    rows=[]
    ac_values=[]
    for task in tasks:
        aid=task["agv_id"]
        row=dict(agv_id=aid,success=int(aid in planned))
        if aid in planned:
            item=planned[aid];path=[tuple(p) for p in item["path"]];times=item["times"]
            assert path[0]==tuple(task["agv_position"]) and path[-1]==tuple(task["destination"])
            assert tuple(task["source"]) in path
            moves=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(path,path[1:])]
            nonzero=[d for d in moves if d!=(0,0)]
            own=raw_occupancy({aid:item})
            neutral=exposure_values(path,times,all_raw,config.neutral_radius,config.neutral_time_radius,own)
            path_ac=[fixed_gaussian.get((x,y,int(t)),0.0) for (x,y),t in zip(path,times)]
            ac_values.extend(path_ac)
            row.update(path_length=sum(abs(x)+abs(y) for x,y in moves),
                       path_duration=float(times[-1]-times[0]),wait_steps=sum(d==(0,0) for d in moves),
                       turns=sum(a!=b for a,b in zip(nonzero,nonzero[1:])),
                       neutral_congestion_exposure=float(np.mean(neutral)))
        else:
            row.update({m:None for m in PATH_METRICS})
        rows.append(row)
    def avg(key):
        values=[r[key] for r in rows if r[key] is not None]
        return float(np.mean(values)) if values else None
    summary=dict(success_count=len(planned),success_rate=len(planned)/len(tasks),
                 avg_path_length=avg("path_length"),avg_path_duration=avg("path_duration"),
                 avg_wait_steps=avg("wait_steps"),avg_turns=avg("turns"),
                 neutral_congestion_exposure=avg("neutral_congestion_exposure"),
                 gaussian_AC=float(np.mean(ac_values)) if ac_values else None)
    return summary,rows,validation
