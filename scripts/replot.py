"""Replot supplied results only. Does not import experiment runners."""
from pathlib import Path
import sys,json,subprocess,os,argparse
ROOT=Path(__file__).resolve().parents[1]
COMMANDS={
'R2_03_omega':['experiments/revision/R2_03_parameter_interactions/R2_03_omega_interactions/plot_omega_interactions.py','--input','results/revision/R2_03_parameter_interactions/omega','--output','figures/revision/R2_03_omega_interactions'],
'R2_02_CI':['scripts/replot_R2_02_CI.py'],
'R1_03':['plotting/revision/R1/R1_03_dmin/final/plot_R1_3_dmin_sensitivity_2x3_response_v2.py'],
'R1_05_06':['plotting/revision/R1/R1_05_06_gaussian/final/plot_R1_gaussian_sensitivity_3x4_response.py'],
'R1_07_08':['plotting/revision/R1/R1_07_08_delta/final/plot_R1_delta_sensitivity_1x3_response.py'],
'R1_09':['plotting/revision/R1/R1_09_retry_limit/final/plot_R1_09_response_2x3.py'],
'R2_03':['plotting/revision/R2/R2_3/final/plot_R2_03_publication_package.py','--input','results/revision/R2_03_parameter_interactions','--output','figures/revision/R2_03_parameter_interactions'],
'R2_04_main':['plotting/revision/R2/R2_4/final/plot_r2_04_compact_full_HM_HL.py','--data','results/revision/R2_04_operational_metrics/raw_results.csv','--inputs','data/derived/R2_04_plot_inputs.json','--out','figures/revision/R2_04_operational_metrics/main'],
'R2_04_pooled':['plotting/revision/R2/R2_4/final/plot_r2_04_compact_all_conditions.py','--data','results/revision/R2_04_operational_metrics/raw_results.csv','--inputs','data/derived/R2_04_plot_inputs.json','--out','figures/revision/R2_04_operational_metrics/pooled'],
'R2_05':['plotting/revision/R2/R2_5/final/plot_r2_05_compact_reordered.py','--results-zip','provenance/source_archives/10-R2_5_results_formal_FRANSEN200_replaced.zip','--output','figures/revision/R2_05_scalability'],
'R2_07':['plotting/revision/R2/R2_7/final/plot_r2_07.py','--results','provenance/data_archives/19-R2_7_results_merged_seed42_46.zip','--out','figures/revision/R2_07_factorial_ablation']
}
def prepare():
 fleets={'STANDARD':50,'FRANSEN':200,'RING':160};maps={};provenance={}
 for m,n in fleets.items():
  p=ROOT/f'results/revision/R2_04_operational_metrics/workloads/{m}_N{n}_dispersed_39.json';d=json.loads(p.read_text())
  maps[m]={'grid':d['map_grid'],'origins':d['origins'],'destinations':d['destinations']};provenance[m]=str(p.relative_to(ROOT))
 out=ROOT/'data/derived';out.mkdir(parents=True,exist_ok=True)
 (out/'R2_04_plot_inputs.json').write_text(json.dumps({'fleets':fleets,'maps':maps,'source_files':provenance},indent=2))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('target',choices=['all']+list(COMMANDS));a=ap.parse_args();prepare()
 logs=ROOT/'validation/plot_logs';logs.mkdir(parents=True,exist_ok=True);results=[]
 for name in COMMANDS if a.target=='all' else [a.target]:
  cmd=COMMANDS[name]
  if name=='R2_07' and not (ROOT/cmd[2]).exists():cmd=['-m','plotting.revision.R2.R2_7.final.replot_from_core_csv']
  print(name,flush=True)
  with (logs/(name+'.txt')).open('w') as f:res=subprocess.run([sys.executable,*cmd],cwd=ROOT,env={**os.environ,'MPLBACKEND':'Agg'},stdout=f,stderr=subprocess.STDOUT)
  results.append({'target':name,'command':'python '+' '.join(cmd),'returncode':res.returncode,'passed':res.returncode==0})
  print(name,res.returncode,flush=True)
 p=ROOT/'validation/plot_checks.json'
 old=json.loads(p.read_text()) if p.exists() else []
 old=[x for x in old if x['target'] not in {x['target'] for x in results}]
 p.write_text(json.dumps(old+results,indent=2))
 if any(not x['passed'] for x in results):raise SystemExit(1)
if __name__=='__main__':main()
