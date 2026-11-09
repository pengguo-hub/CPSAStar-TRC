"""Replot core CSV only; uses supplied effect/figure functions, no payload audit."""
from pathlib import Path
import pandas as pd
from plotting.revision.R2.R2_7.final.plot_r2_07 import calculate_effects,make_figure
R=Path(__file__).resolve().parents[5]
def main():
 d=pd.concat([pd.read_csv(R/f'results/revision/R2_07_factorial_ablation/merge_sources/seed{s}/raw_results.csv') for s in range(42,47)],ignore_index=True)
 assert len(d)==240 and d.trial_id.nunique()==240 and d.groupby(['map','seed']).variant.nunique().eq(16).all()
 assert d.status.eq('completed').all() and d.eligible.eq(True).all()
 e,s=calculate_effects(d);o=R/'figures/revision/R2_07_factorial_ablation/core_csv_replot';o.mkdir(parents=True,exist_ok=True)
 e.to_csv(o/'factor_effects.csv',index=False);s.to_csv(o/'seed_effects.csv',index=False)
 make_figure(e[e.contrast.isin(['S','L','P','R'])&e.metric.isin(['throughput','waiting_time','queue_length','planning_seconds'])],o/'R2_07_from_core_csv.pdf')
if __name__=='__main__':main()
