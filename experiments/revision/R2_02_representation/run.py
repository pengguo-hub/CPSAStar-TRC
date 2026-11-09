#!/usr/bin/env python3
"""R2-02 wrapper. Primary analysis keeps rollback OFF to isolate congestion representation."""
import argparse
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--seeds',type=int,default=5)
    p.add_argument('--seed-start',type=int,default=42)
    p.add_argument('--suite',choices=['primary','confirmation','both'],default='primary')
    p.add_argument('--output',type=Path)
    p.add_argument('--references',type=Path)
    p.add_argument('--prepare-references',action='store_true',help='Prepare disjoint historical/learned artifacts before running')
    a=p.parse_args()
    if a.seeds<1:p.error('seeds must be positive')
    out=(a.output or ROOT/('smoke_results' if a.smoke else 'results_formal')).resolve()
    refs=(a.references or ROOT/('reference_smoke' if a.smoke else 'reference_artifacts')).resolve()
    if a.prepare_references:
        prep=[sys.executable,str(ROOT/'prepare_reference_artifacts.py'),'--output',str(refs)]
        if a.smoke: prep+=['--smoke']
        subprocess.run(prep,cwd=ROOT,check=True)
    cmd=[sys.executable,str(ROOT/'run_representation_experiment.py'),'--suite',a.suite,
         '--seeds',str(1 if a.smoke else a.seeds),'--seed-start',str(a.seed_start),
         '--instances',str(out/'shared_instances'),'--references',str(refs),'--output',str(out/'direct')]
    if a.smoke:cmd+=['--smoke']
    if a.dry_run:cmd+=['--dry-run']
    subprocess.run(cmd,cwd=ROOT,check=True)

if __name__=='__main__':main()
