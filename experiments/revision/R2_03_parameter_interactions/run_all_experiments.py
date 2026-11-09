#!/usr/bin/env python3
"""Run the two executable R2-03 evidence layers; R1 single-factor evidence is reused, not rerun."""
import argparse, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['joint','cross','all'],default='all');p.add_argument('--smoke',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--seeds',type=int,default=5);p.add_argument('--seed-start',type=int,default=10000);p.add_argument('--output',type=Path,default=Path('results_R2_03'));a=p.parse_args()
    common=['--seed-start',str(a.seed_start),'--seeds',str(1 if a.smoke else a.seeds)]
    if a.smoke:common+=['--smoke']
    if a.dry_run:common+=['--dry-run']
    def run(script,target):
        cmd=[sys.executable,str(ROOT/script),'--output',str(target),*common];print('COMMAND:',' '.join(cmd),flush=True);subprocess.run(cmd,check=True,cwd=ROOT)
    out=a.output.resolve()
    if a.stage in ('joint','all'):run('run.py',out/'joint_spatiotemporal_sensitivity')
    if a.stage in ('cross','all'):run('run_parameter_interactions.py',out/'cross_parameter_interactions')
if __name__=='__main__':main()
