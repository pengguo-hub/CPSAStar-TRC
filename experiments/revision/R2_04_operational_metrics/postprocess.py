"""Run offline audit, statistics and plotting; never starts an experiment."""
from pathlib import Path
import argparse,subprocess,sys
ROOT=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('results',type=Path);a=p.parse_args()
    for script in ['analyze.py','plot_results.py']:
        subprocess.run([sys.executable,str(ROOT/script),str(a.results.resolve())],check=True,cwd=ROOT.parents[2])
if __name__=='__main__':main()
