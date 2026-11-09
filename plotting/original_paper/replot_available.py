"""Use supplied plotting functions on the available original-paper data only."""
from pathlib import Path
import os,json
import pandas as pd
from src.original_paper.experiment import plot_results as one
from src.original_paper.experiment.Lifelong import plot_throughput as bench
from src.original_paper.experiment.Lifelong import plot_throughput_ourmaps as custom
ROOT=Path(__file__).resolve().parents[2]
def main():
 data=ROOT/'results/original_paper';out=ROOT/'figures/original_paper';out.mkdir(parents=True,exist_ok=True)
 dst=out/'one_shot';dst.mkdir(exist_ok=True)
 groups={}
 for p in (data/'one_shot').glob('*.json'):
  a=json.loads(p.read_text());groups.setdefault(a['map_key'],[]).append(a['task_count'])
 for m,counts in groups.items():one.plot_map(str(data/'one_shot'),m,sorted(counts),str(dst))
 dst=out/'lifelong';dst.mkdir(exist_ok=True);os.chdir(dst)
 for p in (data/'lifelong').glob('*.csv'):
  d=pd.read_csv(p)
  if 'map_name' in d.columns:
   custom.CSV_FILE=str(p);custom.main()
  else:
   bench.CSV_FILE=str(p);bench.OUT_PNG=str(dst/(p.stem+'_3subplots.png'));bench.main()
if __name__=='__main__':main()
