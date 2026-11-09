"""Run supplied CI plotting on a temporary copy of saved results; no experiments."""
from pathlib import Path
import os,sys,json,shutil,tempfile,subprocess
import pandas as pd
R=Path(__file__).resolve().parents[1]
def main():
    src=R/'results/revision/R2_02_representation'
    out=R/'figures/revision/R2_02_representation/supplied_CI'
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cps_r202_analysis_') as td:
        data=Path(td)/'data';data.mkdir()
        for name in ['raw_results.csv','task_results.csv','run_manifest.json','kernel_calibration.json']:
            shutil.copy2(src/name,data/name)
        rows=[]
        for p in sorted((src/'runs').glob('*.json')):
            j=json.loads(p.read_text());rows.append({**{k:j['row'][k] for k in ['protocol','map','task_count','seed','representation','rollback_mode']},**j['validation']})
        raw=pd.read_csv(src/'raw_results.csv');validation=pd.DataFrame(rows)
        keys=['protocol','map','task_count','seed','representation','rollback_mode']
        assert len(validation)==len(raw)==240 and not validation.duplicated(keys).any()
        assert len(raw[keys].merge(validation[keys],on=keys,validate='one_to_one'))==240
        validation.to_csv(data/'run_validation.csv',index=False)
        env={**os.environ,'MPLBACKEND':'Agg','PYTHONPATH':str(R/'experiments/revision/R2_02_representation')}
        subprocess.run([sys.executable,str(R/'plotting/revision/R2/R2_2/final/plot_R2_02_results.py'),'--data-dir',str(data),'--output-dir',str(out/'figures')],cwd=R,env=env,check=True)
        checks=json.loads((out/'validation_summary.json').read_text());assert checks['all_checks_pass']
        target=R/'statistics/R2_02_supplied_CI';target.mkdir(exist_ok=True)
        for p in data.glob('*.csv'):
            if p.name not in ['raw_results.csv','task_results.csv']:shutil.copy2(p,target/p.name)
        (target/'README.md').write_text('Derived from unchanged saved data with the newly supplied statistics_analysis.py. run_validation.csv extracts stored validation records from 240 source run JSON files; it is not a newly executed collision test. Raw inputs are never overwritten. Figures preserve the supplied bootstrap-CI convention and fixed axis limits; the separately labeled SD reconstruction remains available.\n')
if __name__=='__main__':main()
