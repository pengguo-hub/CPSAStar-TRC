"""Write numerical response notes only for the full, audited 1440-trial formal design."""
import argparse,json
from pathlib import Path
import pandas as pd

def require_formal(plan,status):
    assert not plan['smoke'],'Smoke cannot supply paper conclusions'
    assert plan['seeds']==list(range(39,69)) and plan['expected_trials']==1440
    assert plan['horizon']==500 and plan['warmup']==0 and plan['wall_timeout'] is None
    assert status['eligible_trials']==1440,'Incomplete formal data: report reliability first; no complete-design response generated'

def make(out):
    out=Path(out);plan=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'))['plan'];status=json.loads((out/'completion_status.json').read_text(encoding='utf-8'));require_formal(plan,status)
    tab=pd.read_csv(out/'significance_tests.csv');tab=tab[tab.family.isin(['main_effect_primary','two_factor_interaction_primary'])]
    lines=['# Reviewer 2, item 7: numerical response notes','',
      'The complete design contains 16 variants × 3 maps × 30 matched seeds (1,440 trials), each observed for 500 steps without warm-up. The implemented original baseline is S1_L0_P1_R1. L1 is an added experimental treatment, not an enabled component of the supplied original implementation.',
      '', 'The estimates below are conditional on the declared source implementation and backlogged workloads. Priority scoring and priority exchange form the P treatment; the rollback retry ordering remains when P=0. We therefore report interactions and conditional effects instead of assuming additive independent benefits.',
      '', 'Waiting and flow means below condition on completed tasks; interpret them together with completion fraction and all-arrived restricted outcomes. Source-field units change with S. Runtime includes the stated observation overhead.',
      '', '| Map / condition | Outcome | Contrast | n | Mean difference | 95% CI | Holm p |', '|---|---|---|---:|---:|---|---:|']
    for _,r in tab.iterrows():lines.append(f'| {r["case"]} | {r.metric} | {r.contrast} | {int(r.n_pairs)} | {r.mean_difference:.6g} | [{r.ci95_low:.6g}, {r.ci95_high:.6g}] | {r.p_holm:.6g} |')
    lines+=['','Baseline contrasts and P|R / S|L conditional effects are in significance_tests.csv. Report each map separately, disclose all missing metrics, and do not infer universal Gaussian superiority, real-time suitability, physical safety, optimality, or completeness from these ablations.']
    (out/'Reviewer2_7_numerical_notes.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();make(a.output)
