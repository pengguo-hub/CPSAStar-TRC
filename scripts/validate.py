"""Import/compile validation only. Does not invoke experiment mains."""
from pathlib import Path
import sys,json,subprocess,compileall,platform,importlib.metadata,ast,re
ROOT=Path(__file__).resolve().parents[1]
MODULES=['src.original_paper.experiment.CPS_A.path_planner','src.original_paper.experiment.Lifelong.CPS_A_lifelong.path_planner_lifelong','src.original_paper.experiment.Lifelong.RHCR.rhcr_lifelong','src.original_paper.experiment.Lifelong.PIBT.plain_pibt_lifelong','src.original_paper.experiment.Lifelong.Guide_Paths.guided_pibt.lifelong_runner','src.original_paper.experiment.Lifelong.CMPP.lifelong_cmpp_planner','src.original_paper.experiment.MCCP.path_planner','experiments.revision.R1_03_dmin.run_R1_3_dmin_sensitivity','experiments.revision.R1_05_06_gaussian.test_r1_gaussian_sensitivity','experiments.revision.R1_07_08_delta.r1_delta_sensitivity','experiments.revision.R1_09_retry_limit.run_R1_9_R_sensitivity','experiments.revision.R2_04_operational_metrics.worker','experiments.revision.R2_05_scalability.worker','experiments.revision.R2_07_factorial_ablation.worker']
def main():
 v=ROOT/'validation';v.mkdir(exist_ok=True);compiled=all(compileall.compile_dir(ROOT/p,quiet=1) for p in ['src','experiments','plotting','scripts'])
 rows=[]
 for m in MODULES:
  p=subprocess.run([sys.executable,'-c','import importlib; importlib.import_module('+repr(m)+')'],cwd=ROOT,capture_output=True,text=True,timeout=45);rows.append(dict(module=m,passed=p.returncode==0,error=p.stderr if p.returncode else ''))
 for e,mods in [('R2_02_representation',['run_representation_experiment','statistics_analysis','learned_prediction']),('R2_03_parameter_interactions',['run','run_parameter_interactions']),('R2_03_parameter_interactions/R2_03_omega_interactions',['run_omega_interactions'])]:
  for mod in mods:
   proc=subprocess.run([sys.executable,'-c','import compat; import importlib; importlib.import_module('+repr(mod)+')'],cwd=ROOT/'experiments/revision'/e,capture_output=True,text=True,timeout=60)
   rows.append(dict(module=e+'/'+mod,passed=proc.returncode==0,error=proc.stderr if proc.returncode else ''))
 (v/'import_checks.json').write_text(json.dumps(rows,indent=2))
 audits=[]
 for e in ['R2_04_operational_metrics','R2_05_scalability','R2_07_factorial_ablation']:
  p=subprocess.run([sys.executable,'-m','experiments.revision.'+e+'.verify_sources'],cwd=ROOT,capture_output=True,text=True,timeout=45);audits.append(dict(experiment=e,passed=p.returncode==0,stdout=p.stdout,stderr=p.stderr))
 (v/'source_verifiers.json').write_text(json.dumps(audits,indent=2));issues=[]
 for folder in ['src','experiments','plotting']:
  for p in (ROOT/folder).rglob('*.py'):
   standalone_vendor=any(x in p.parts for x in ['R2_02_representation','R2_03_parameter_interactions']) and 'vendor' in p.parts
   for n in ast.walk(ast.parse(p.read_text(encoding='utf-8-sig'))):
    if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('SRTP') and not standalone_vendor:issues.append(str(p.relative_to(ROOT))+': SRTP import')
    if isinstance(n,ast.Import) and any(x.name.startswith('SRTP') for x in n.names) and not standalone_vendor:issues.append(str(p.relative_to(ROOT))+': SRTP import')
    if isinstance(n,ast.Constant) and isinstance(n.value,str) and (re.match(r'^[A-Z]:[/\\]',n.value) or re.search(r'\bsk-[A-Za-z0-9_-]{15,}',n.value)):issues.append(str(p.relative_to(ROOT))+': path/credential candidate, value withheld')
 (v/'portability_scan.json').write_text(json.dumps(issues,indent=2));versions={}
 for p in ['numpy','pandas','scipy','matplotlib','Pillow','PyMuPDF','torch','networkx','scikit-learn']:
  try:versions[p]=importlib.metadata.version(p)
  except importlib.metadata.PackageNotFoundError:versions[p]='not installed'
 (v/'environment.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'packages':versions,'role':'audit environment; not historical execution environment'},indent=2))
 summary={'compileall_passed':compiled,'imports_passed':sum(x['passed'] for x in rows),'import_modules':len(rows),'source_verifiers_passed':sum(x['passed'] for x in audits),'portability_issues':len(issues),'experiment_main_invocations':0}
 (v/'validation_summary.json').write_text(json.dumps(summary,indent=2));print(summary)
 if not compiled or not all(x['passed'] for x in rows+audits) or issues:raise SystemExit(1)
if __name__=='__main__':main()
