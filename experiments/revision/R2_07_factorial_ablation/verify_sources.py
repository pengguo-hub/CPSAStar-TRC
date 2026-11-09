"""Verify delivered code hashes, source snapshots, runtime imports and baseline guards."""
import ast
import hashlib
import importlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def method(path,name):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    return ast.dump(next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)

def verify():
    manifest=json.loads((ROOT/'source_manifest.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        assert sha(ROOT/row['path'])==row['sha256'],('Hash mismatch',row['path'])
    for row in manifest['authority_files']:
        assert sha(ROOT/row['path'])==row['sha256'],('Source snapshot mismatch',row['path'])
    search=ROOT/'CPS_A_lifelong/Segment_Planner.py';orig=ROOT.parents[2]/'provenance/experiment_records/R2_07_factorial_ablation/original/CPS_A_lifelong/Segment_Planner.py'
    for name in ['plan_agv','_plan_segment','_reserve_tickets','_has_node_conflict','_has_edge_conflict','_calculate_turn_penalty','_is_valid_neighbor']:
        assert method(search,name)==method(orig,name),('Original search changed',name)
    assert sha(ROOT/'CPS_A_lifelong/Ticket_Manager.py')==sha(ROOT.parents[2]/'provenance/experiment_records/R2_07_factorial_ablation/original/CPS_A_lifelong/Ticket_Manager.py')
    for name in ['_simulate_one_step','_release_start_reservation_if_unused','_rollback_agv','_find_blocker','_commit_pending_paths','get_throughput']:
        assert method(ROOT/'CPS_A_lifelong/path_planner_lifelong.py',name)==method(ROOT.parents[2]/'provenance/experiment_records/R2_07_factorial_ablation/original/CPS_A_lifelong/path_planner_lifelong.py',name)
    imports={}
    for name in ['path_planner_lifelong','Segment_Planner','Ticket_Manager','Conflict_Field_Updater']:
        module=importlib.import_module(__package__+'.CPS_A_lifelong.'+name)
        actual=Path(module.__file__).resolve();assert actual==ROOT/'CPS_A_lifelong'/f'{name}.py'
        imports[name]=str(actual.relative_to(ROOT))
    # Inspect executable AST; dormant original comments/constants are preserved.
    forbidden={'set_persistent_hold','reserve_with_terminal_hold','_has_static_route_around_active_holds','alarm','setitimer','wait_for','terminate_after','physical_valid','node_collision_pairs','reverse_edge_pairs'}
    paths=[*ROOT.glob('*.py'),*(ROOT/'CPS_A_lifelong').glob('*.py')]
    for path in paths:
        if path.name in ['verify_sources.py','verify_original.py']:continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call):
                call=node.func.attr if isinstance(node.func,ast.Attribute) else getattr(node.func,'id','')
                assert call not in forbidden,(path.name,call)
                assert not any(k.arg in {'timeout','time_limit'} for k in node.keywords),(path.name,'call limit')
            if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load):
                assert node.id not in {'MAX_EXPAND','max_expansions'},(path.name,node.id)
    cfg=json.loads((ROOT/'configs/experiment.json').read_text(encoding='utf-8'))
    assert cfg['baseline']=='S1_L0_P1_R1' and cfg['warmup']==0 and cfg['wall_timeout'] is None
    assert cfg['seeds']==list(range(39,69)) and cfg['expected_trials']==1440
    assert [(c['map'],c['fleet'],c['horizon'],c['backlog'],c['warmup']) for c in cfg['cases']]==[(m,n,500,3000,0) for m,n in [('STANDARD',50),('FRANSEN',150),('RING',120)]]
    return dict(passed=True,verified_files=len(manifest['files']),authority_files=len(manifest['authority_files']),imports=imports,
        original_search_ast=True,ticket_manager_byte_identical=True,active_expansion_cap=False,trial_wall_timeout=False,warmup=0,physical_checks=False,source_fingerprint=manifest['execution_hash'])

if __name__=='__main__':print(json.dumps(verify(),indent=2))
