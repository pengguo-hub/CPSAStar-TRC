#!/usr/bin/env python3
"""Behavioral oracle: unedited original modules vs instrumented original baseline."""
import argparse
import ast
import contextlib
import copy
import importlib.util
import io
import json
import sys
from pathlib import Path
import numpy as np
from workload import grid_for,build_workload,case,write_json
from observations import Recorder
from CPS_A_lifelong.path_planner_lifelong import LifelongPlanner
from CPS_A_lifelong.Segment_Planner import SegmentPlanner
from CPS_A_lifelong.Ticket_Manager import TicketManager
from CPS_A_lifelong.Conflict_Field_Updater import ConflictFieldUpdater

ROOT=Path(__file__).resolve().parent

def load_original():
    sys.path.insert(0,str(ROOT/'original/CPS_A_lifelong'))
    try:
        spec=importlib.util.spec_from_file_location('unaltered_source_planner',ROOT/'original/CPS_A_lifelong/path_planner_lifelong.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.LifelongPlanner
    finally:sys.path.pop(0)

def canonical(value):
    if isinstance(value,dict):return sorted((repr(k),canonical(v)) for k,v in value.items() if k!='_request_id')
    if isinstance(value,(tuple,list)):return [canonical(v) for v in value]
    if isinstance(value,set):return sorted((canonical(v) for v in value),key=repr)
    if isinstance(value,np.ndarray):return value.tolist()
    return value

def state(p):
    return canonical(dict(time=p.current_time,positions=p.agv_positions,tasks=p.agv_tasks,queue=list(p.task_queue),
        completed=p.completed_tasks,assigned=p.total_assigned_tasks,pending=p.pending_agv_paths,
        committed=p.committed_agvs,planned_count=p.planned_count,retries=p.replan_attempts,
        nodes=p.ticket_manager.node_reservations,edges=p.ticket_manager.edge_reservations,
        raw=p.conflict_updater.path_conflict_dict,field=p.conflict_updater.smoothed_dict,
        agv_reservations=p.ticket_manager.agv_reservations,committed_reservations=p.ticket_manager.committed_reservations,
        pending_field=p.conflict_updater.pending_paths,last_field=p.conflict_updater.last_path_conflict_dict,USE_CON=p.USE_CON))

def attach_trace(p):
    trace=[];old=p._clean_completed_tasks
    def clean():old();trace.append(state(p))
    p._clean_completed_tasks=clean
    return trace

def check():
    original=load_original();reports=[]
    for name,fleet,horizon,backlog in [('STANDARD',6,30,20),('FRANSEN',6,30,20),('RING',6,30,20),('STANDARD',30,40,80)]:
        c=case('oracle',name,fleet,horizon,mode='backlog',backlog=backlog)
        w=build_workload(c,39);positions={a:tuple(pos) for a,pos in w['initial_positions'].items()}
        info={a:{'speed':1.} for a in positions}
        queue=[(tuple(r['pickup']),tuple(r['dropoff'])) for r in w['requests']]
        a=original(grid_for(name),copy.deepcopy(info),positions,queue,use_priority_replan=True)
        recorder=Recorder(w)
        b=LifelongPlanner(grid_for(name),copy.deepcopy(info),positions,recorder.initial_queue(),use_priority_replan=True,experiment=recorder)
        ta,tb=attach_trace(a),attach_trace(b)
        with contextlib.redirect_stdout(io.StringIO()):a.run_lifelong(horizon);b.run_lifelong(horizon)
        assert ta==tb,(name,'cycle states differ')
        assert state(a)==state(b)
        if fleet==30:assert recorder.rollbacks>0
        reports.append(dict(check='original_baseline_exact_cycle_states',map=name,fleet=fleet,cycles=len(ta),completed=len(a.completed_tasks),rollbacks=recorder.rollbacks,passed=True))
    # Search body and ticket code must remain unchanged: no one-shot cost, limits or endpoint holding.
    for method in ['_plan_segment','plan_agv','_reserve_tickets','_has_node_conflict','_has_edge_conflict']:
        def get(path):
            tree=ast.parse(path.read_text(encoding="utf-8"));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
            return ast.dump(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method),include_attributes=False)
        assert get(ROOT/'CPS_A_lifelong/Segment_Planner.py')==get(ROOT/'original/CPS_A_lifelong/Segment_Planner.py')
    assert (ROOT/'CPS_A_lifelong/Ticket_Manager.py').read_bytes()==(ROOT/'original/CPS_A_lifelong/Ticket_Manager.py').read_bytes()
    reports.append(dict(check='five_search_methods_AST_identical_and_tickets_byte_identical',passed=True))
    # Independent hand calculation: three path visits in the same delta=3 slot => count 3, not occupancy 1.
    grid=grid_for('STANDARD');tm=TicketManager()
    revision=(ROOT/'REVISION_ID').read_text(encoding='utf-8').strip()
    f=ConflictFieldUpdater(grid,tm,**({'smoothing':False} if revision=='R2-07' else {}))
    f.accumulate_path([(0,0)]*3,[0,1,2],'test');f.batch_update_from_paths()
    assert f.delta==3 and f.path_conflict_dict[(0,0,0)]==3
    if revision=='R2-07':assert f.smoothed_dict[(0,0,0)]==3
    reports.append(dict(check='slot_count_is_three_visits_not_one_exact_time_owner',passed=True))
    search=SegmentPlanner(grid,tm,f);search.congestion_dict={(0,0,1):2.}
    before=search._heuristic((0,0),(4,0),0,1)
    search.use_lookahead=True;after=search._heuristic((0,0),(4,0),0,1)
    assert before==4 and (after>4 if revision=='R2-07' else after==4)
    reports.append(dict(check='lookahead_new_toggle_only_in_R2_07_others_original_Manhattan',passed=True))
    return reports

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'verification/original_equivalence.json');a=p.parse_args()
    reports=check();write_json(a.output,reports);print(json.dumps(reports,indent=2))
