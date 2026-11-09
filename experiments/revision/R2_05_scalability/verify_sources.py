"""Verify frozen original bytes and the deliberately small integration diff."""
import ast,hashlib
from experiments.revision.R2_05_scalability.common import ROOT, read_json, execution_hash, write_json
from experiments.revision.R2_05_scalability.original_runtime import source_audit

def main():
    audit=source_audit();assert all(x['matches'] for x in audit)
    p=ROOT/'vendor/portable_vendor/experiment/Lifelong/CPS_A_lifelong'
    tree=ast.parse((p/'Segment_Planner.py').read_text())
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id=='MAX_EXPAND']
    allowed={'__init__','run_lifelong','_assign_new_tasks','_assign_second_phase','_handle_failure_direct',
             '_handle_failure_with_replan','_clean_completed_tasks'}
    def functions(path):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef)}
    a=functions(p/'path_planner_lifelong.py');b=functions(ROOT/'integration/path_planner_lifelong.py')
    assert set(a)==set(b)
    changed={name for name in a if a[name]!=b[name]};assert changed==allowed
    spec=read_json(ROOT/'provenance/integration_fingerprint.json')
    assert hashlib.sha256((ROOT/'integration/path_planner_lifelong.py').read_bytes()).hexdigest()==spec['sha256']
    print('PASS:',len(audit),'unchanged original files; bounded integration diff; MAX_EXPAND disabled.')
    return 0
if __name__=='__main__':raise SystemExit(main())
