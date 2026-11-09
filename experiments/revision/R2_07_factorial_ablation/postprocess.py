"""Audit, analyze and plot existing files only. Never launches simulation workers."""
import argparse,json
from pathlib import Path
from experiments.revision.R2_07_factorial_ablation.audit_results import collect
from experiments.revision.R2_07_factorial_ablation.analysis import analyze
from experiments.revision.R2_07_factorial_ablation.plot_results import plot
from experiments.revision.R2_07_factorial_ablation.verify_sources import verify
from experiments.revision.R2_07_factorial_ablation.make_response import make
from experiments.revision.R2_07_factorial_ablation.workload import write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--validation-preview',action='store_true');a=p.parse_args()
    checks=verify();out=a.output.resolve();plan=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'))['plan']
    assert plan['code_hash']==checks['source_fingerprint'],'Source changed; retain old sources with their results'
    if plan['smoke'] and not a.validation_preview:p.error('Use --validation-preview for smoke; never use smoke as formal evidence')
    df,plan,status=collect(out);analyze(df,plan,out,plan['bootstrap']);plot(out,a.validation_preview)
    if not plan['smoke'] and status['eligible_trials']==1440:make(out)
    write_json(out/'postprocess_status.json',dict(success=True,smoke=plan['smoke'],eligible=status['eligible_trials'],expected=plan['expected_trials'],
        numeric_formal_notes=(out/'Reviewer2_7_numerical_notes.md').exists(),input_fingerprint=status['input_fingerprint']))
    print('POSTPROCESS COMPLETE',flush=True)

if __name__=='__main__':main()
