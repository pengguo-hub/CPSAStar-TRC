"""Audit retained source archives, byte identity and planner ASTs without running planners."""
from pathlib import Path
import zipfile,json,hashlib,ast,math,pandas as pd
ROOT=Path(__file__).resolve().parents[1];V=ROOT/'validation';P=ROOT/'provenance'
def archive(n):
 return next(p for p in P.rglob(n+'-*.zip') if 'archives' in str(p))
class StripImports(ast.NodeTransformer):
 def visit_Import(self,n):return None
 def visit_ImportFrom(self,n):return None
def funcs(b):
 t=StripImports().visit(ast.parse(b.decode('utf-8-sig')))
 return [(n.name,ast.dump(n,include_attributes=False)) for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
def main():
 mapping=json.loads((P/'extraction_map.json').read_text());out=[]
 for row in mapping:
  p=ROOT/row['destination']
  if p.name not in ['path_planner.py','path_planner_lifelong.py','Segment_Planner.py','Ticket_Manager.py','Conflict_Field_Updater.py'] or not row['destination'].startswith(('src/','experiments/')):continue
  with zipfile.ZipFile(P/'source_archives'/row['source'] if (P/'source_archives'/row['source']).exists() else archive(row['source'][:2])) as z:a=funcs(z.read(row['member']))
  b=funcs(p.read_bytes());out.append(dict(file=row['destination'],functions=len(a),unchanged_function_ast=a==b))
 pd.DataFrame(out).to_csv(V/'planner_function_ast_comparison.csv',index=False);assert all(x['unchanged_function_ast'] for x in out)
 z=zipfile.ZipFile(archive('18'));ss=zipfile.ZipFile(archive('15'));rows=[]
 for m in ss.namelist():
  if m.endswith('/'):continue
  k='R2_04_OD_backlog_ready_to_run/'+m.split('/',1)[1];rows.append(dict(snapshot_member=m,code_member=k,byte_identical=ss.read(m)==z.read(k)))
 pd.DataFrame(rows).to_csv(V/'R2_04_snapshot_comparison.csv',index=False);assert all(x['byte_identical'] for x in rows)
 orig=zipfile.ZipFile(archive('20'));rows=[]
 for n,root,pre in [('18','R2_04_OD_backlog_ready_to_run','vendor/SRTP/experiment/Lifelong/CPS_A_lifelong/'),('11','R2-05','vendor/SRTP/experiment/Lifelong/CPS_A_lifelong/'),('12','R2-07_original_Lifelong_verified','original/CPS_A_lifelong/')]:
  z=zipfile.ZipFile(archive(n))
  for f in ['Conflict_Field_Updater.py','path_planner_lifelong.py','Segment_Planner.py','Ticket_Manager.py','test_lifelong.py','benchmark_loader.py','__init__.py']:
   m=root+'/'+pre+f;a='experiment/Lifelong/CPS_A_lifelong/'+f;rows.append(dict(source=n,member=m,authority_member=a,byte_identical=z.read(m)==orig.read(a)))
 pd.DataFrame(rows).to_csv(V/'baseline_core_identity.csv',index=False);assert all(x['byte_identical'] for x in rows)
 z=zipfile.ZipFile(archive('19'));bad=[]
 for m in z.infolist():
  if not m.is_dir():continue
  try:z.read(m)
  except Exception as e:bad.append(dict(member=m.filename,error=str(e)))
 (V/'damaged_directory_entries.json').write_text(json.dumps(bad,indent=2))
 df=pd.read_csv(ROOT/'results/revision/R2_04_operational_metrics/raw_results.csv').set_index(['case','seed','variant']);z=zipfile.ZipFile(archive('17'));rows=[]
 for m in z.namelist():
  if not m.endswith('selected_result.json'):continue
  obj=json.loads(z.read(m));a=obj['row'];key=(a['case'],a['seed'],a['variant']);b=df.loc[key]
  good=all(math.isclose(float(a[k]),float(b[k]),rel_tol=1e-10,abs_tol=1e-9) for k in ['completed','throughput','waiting_time','flow_time','queue_length','planning_seconds','rollbacks','arrived'])
  rows.append(dict(member=m,case=key[0],seed=key[1],variant=key[2],matches=good))
 pd.DataFrame(rows).to_csv(V/'R2_04_selected_payload_crosscheck.csv',index=False);assert all(x['matches'] for x in rows)
 print('Planner AST, snapshot, baseline and R2.04 payload comparisons passed')
if __name__=='__main__':main()
