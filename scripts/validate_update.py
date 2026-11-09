"""Read-only checks of 2026-11-02 additions; never executes a planner."""
from pathlib import Path
import json,zipfile,hashlib,math,subprocess,sys
import pandas as pd
R=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
    m=json.loads((R/'provenance/extraction_map.json').read_text());rows=[]
    for a in ['R2-02.zip','R2-03.zip']:
        with zipfile.ZipFile(R/'provenance/source_archives'/a) as z:
            assert z.testzip() is None
            for row in m:
                if row['source']!=a or not row['member']:continue
                p=R/row['destination'];good=sha(z.read(row['member']))==sha(p.read_bytes())
                rows.append(dict(path=row['destination'],byte_identical=good));assert good
    omega=R/'results/revision/R2_03_parameter_interactions/omega'
    d=pd.read_csv(omega/'omega_interactions_raw_results.csv');s=pd.read_csv(omega/'omega_interactions_summary.csv')
    assert len(d)==390 and d.seed.nunique()==5
    keys=['map','task_count','seed','alpha','beta','gamma','omega','L','T','sigma_l','sigma_t','update_interval']
    unique=d.drop_duplicates(keys);assert len(unique)==330
    payloads=[json.loads(p.read_text()) for p in (omega/'runs').glob('*.json')];assert len(payloads)==330
    payload=pd.DataFrame(payloads);matched=unique.merge(payload,on=keys,suffixes=('_csv','_json'),validate='one_to_one');assert len(matched)==330
    metrics=['success_count','success_rate','planning_time','average_path_length','average_waits','average_congestion_fixed','average_turns','rollbacks','failed_searches','field_updates','search_expansions','lookahead_evaluations']
    for metric in metrics:
        assert all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-9) for a,b in zip(matched[metric+'_csv'],matched[metric+'_json']))
    assert (matched.task_hash_csv==matched.task_hash_json).all()
    groups=d.groupby(['study','map','task_count','cell']);summary_checks=0
    for row in s.itertuples():
        vals=groups.get_group((row.study,row.map,row.task_count,row.cell))[row.metric]
        assert int(row.n)==len(vals)==5
        assert math.isclose(row.mean,vals.mean(),rel_tol=1e-10,abs_tol=1e-9)
        assert math.isclose(row.std,vals.std(ddof=1),rel_tol=1e-10,abs_tol=1e-9)
        summary_checks+=1
    existing=[]
    for p in (R/'results/revision/R2_03_parameter_interactions').rglob('*.csv'):
        if p.name in ['joint_raw_results.csv','cross_raw_results.csv']:existing.append(pd.read_csv(p))
    old=pd.concat(existing);old=old[old['map']=='A'][['map','task_count','seed','task_hash']].drop_duplicates()
    current=d[['map','task_count','seed','task_hash']].drop_duplicates();assert len(current)==10
    joined=current.merge(old,on=['map','task_count','seed'],suffixes=('_omega','_original'),validate='one_to_one');assert len(joined)==10 and (joined.task_hash_omega==joined.task_hash_original).all()
    code=R/'experiments/revision/R2_02_representation'
    proc=subprocess.run([sys.executable,'-c','import run_representation_experiment as r; print(r.source_digest())'],cwd=code,capture_output=True,text=True,check=True)
    current_digest=proc.stdout.strip();stored=json.loads((R/'results/revision/R2_02_representation/run_manifest.json').read_text())['plan']['source_digest']
    report={'unchanged_extracted_files':len(rows),'all_byte_identical':True,'omega_logical_rows':390,'omega_unique_runs':330,'omega_run_csv_metric_checks':330*len(metrics),'omega_summary_mean_sd_checks':summary_checks,'omega_shared_task_blocks_match_main_R2_03':10,'R2_02_source_digest_current':current_digest,'R2_02_source_digest_recorded':stored,'R2_02_code_digest_matches_run_manifest':current_digest==stored,'new_experiment_invocations':0}
    (R/'validation/update_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
