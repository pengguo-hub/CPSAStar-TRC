"""Publication vector PDFs and 300-dpi PNGs; smoke outputs are visibly labelled."""
import argparse,hashlib,io,json,os
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiments.revision.R2_07_factorial_ablation.analysis import PRIMARY

LABELS={'throughput':'Throughput (tasks / step)','waiting_time':'Completed-task waiting (steps)',
'flow_time':'Completed-task flow time (steps)','queue_length':'Mean unassigned queue (tasks)',
'source_field_exposure':'Source field exposure (S-dependent units)','source_raw_slot_exposure':'Raw slot visit-count exposure',
'planning_seconds':'Batch planning time (s)','loop_wall_seconds':'Instrumented loop time (s)'}

def save(fig,path):
    for fmt in ['png','pdf']:
        buf=io.BytesIO();fig.savefig(buf,format=fmt,dpi=300,bbox_inches='tight');data=buf.getvalue()
        assert data.endswith(b'%%EOF\n') if fmt=='pdf' else b'IEND' in data[-16:]
        target=path.with_suffix('.'+fmt);tmp=target.with_suffix('.tmp')
        with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        assert tmp.read_bytes()==data;tmp.replace(target)
    plt.close(fig)

def plot(out,validation_preview=False):
    out=Path(out);plan=json.loads((out/'run_manifest.json').read_text(encoding='utf-8'))['plan']
    if plan['smoke'] and not validation_preview:raise ValueError('Smoke needs --validation-preview; it is not manuscript evidence')
    am=json.loads((out/'analysis_manifest.json').read_text(encoding='utf-8'))
    for name,h in am['tables'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==h,'Stale analysis'
    table=pd.read_csv(out/'significance_tests.csv');folder=out/'figures';folder.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
    specs=[('01_baseline','vs_original',PRIMARY),('02_main_effects','main_effect',PRIMARY),('03_interactions','two_factor_interaction',PRIMARY),
           ('04_conditional_effects','conditional_effect',PRIMARY),('05_field_and_runtime','main_effect',['source_field_exposure','source_raw_slot_exposure','planning_seconds','loop_wall_seconds'])]
    for filename,family,metrics in specs:
        cases=[c['name'] for c in plan['cases']];sub=table[table.family.str.startswith(family+'_')]
        contrasts=list(sub.contrast.drop_duplicates());height=max(3.2,.29*len(contrasts)+1.4)*len(cases)
        fig,axes=plt.subplots(len(cases),len(metrics),figsize=(15,height),squeeze=False)
        for i,c in enumerate(cases):
            for j,m in enumerate(metrics):
                ax=axes[i,j];g=sub[(sub.case==c)&(sub.metric==m)].set_index('contrast').reindex(contrasts)
                for k,(label,row) in enumerate(g.iterrows()):
                    y=len(contrasts)-1-k;mean=row.mean_difference
                    if np.isfinite(mean):
                        ax.plot(mean,y,'o',ms=4,color='#176b87')
                        if np.isfinite(row.ci95_low) and np.isfinite(row.ci95_high):ax.hlines(y,row.ci95_low,row.ci95_high,color='#176b87',lw=1.4)
                    else:ax.text(.5,y,'not estimable',transform=ax.get_yaxis_transform(),fontsize=7,color='#777777')
                labels=[x.replace(' minus S1_L0_P1_R1','').replace('_on-minus-off','').replace('_at_',' | ') for x in contrasts]
                ax.set_yticks(range(len(contrasts)),labels[::-1] if j==0 else ['']*len(contrasts))
                ax.axvline(0,color='#999999',lw=.8);ax.grid(axis='x',alpha=.2);ax.set_ylim(-.6,len(contrasts)-.4)
                ns=g.n_pairs.fillna(0).astype(int);ax.set_title(c.split('_N')[0]+' · '+LABELS.get(m,m)+'\nn = '+str(ns.min())+'–'+str(ns.max()))
                ax.set_xlabel('Mean difference; 95% t CI')
        title='SMOKE VALIDATION — NOT FOR MANUSCRIPT · one seed; CI / p unavailable' if plan['smoke'] else 'R2-07 · independent seed contrasts'
        fig.suptitle(title,fontsize=13,color='#a62828' if plan['smoke'] else '#111111')
        fig.tight_layout(rect=[0,.035,1,.96]);fig.text(.01,.008,'Signed effects: on − off; interactions: difference of differences. Exact definitions and adjusted p values: significance_tests.csv.',fontsize=9)
        save(fig,folder/(('VALIDATION_' if plan['smoke'] else '')+filename))
    print('Figures saved:',folder,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--validation-preview',action='store_true');a=p.parse_args();plot(a.output,a.validation_preview)
