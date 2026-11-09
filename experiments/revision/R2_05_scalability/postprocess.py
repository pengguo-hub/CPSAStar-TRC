"""Audit, plot and draft the response after the user finishes formal trials."""
import argparse,subprocess,sys
from pathlib import Path
from experiments.revision.R2_05_scalability.common import ROOT, read_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    a=p.parse_args();base=a.input.resolve()
    if read_json(base/'manifest.json')['spec']['purpose']!='formal':p.error('This command is for formal results only.')
    subprocess.run([sys.executable,str(ROOT/'analyze.py'),'--input',str(base)],check=True)
    analysis=base/'analysis';status=read_json(analysis/'analysis_status.json')
    if not status['full_formal_matrix_planned']:p.error('This is a subset; run the full matrix before generating the complete reply.')
    subprocess.run([sys.executable,str(ROOT/'plot_results.py'),'--analysis',str(analysis)],check=True)
    subprocess.run([sys.executable,str(ROOT/'make_response.py'),'--analysis',str(analysis)],check=True)
    print('Formal raw audit passed; figures and a numerical reply draft are saved. Review scientific interpretation and manuscript references before submission.')

if __name__=='__main__':main()
