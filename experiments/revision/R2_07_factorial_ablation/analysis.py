"""Matched seed contrasts. Each seed contributes one value to each map/contrast."""
from pathlib import Path
import hashlib,itertools,json,warnings
import numpy as np
import pandas as pd
from scipy import stats
from experiments.revision.R2_07_factorial_ablation.workload import BASELINE, write_json
from experiments.revision.R2_07_factorial_ablation.audit_results import KEYS

METRICS=KEYS
PRIMARY=['throughput','waiting_time','flow_time','queue_length']
FACTORS=['S','L','P','R']

def rng(label):return np.random.default_rng(int.from_bytes(hashlib.sha256(str(label).encode()).digest()[:8],'little'))

def summary(x,label,reps):
    x=np.asarray(x,float);x=x[np.isfinite(x)];n=len(x)
    r=dict(n=n,mean=float(x.mean()) if n else np.nan,std=float(x.std(ddof=1)) if n>1 else np.nan,
           ci95_low=np.nan,ci95_high=np.nan,bootstrap95_low=np.nan,bootstrap95_high=np.nan)
    if n>1:
        half=float(stats.t.ppf(.975,n-1)*x.std(ddof=1)/np.sqrt(n));r.update(ci95_low=x.mean()-half,ci95_high=x.mean()+half)
        b=x[rng(label).integers(0,n,size=(reps,n))].mean(axis=1)
        r['bootstrap95_low'],r['bootstrap95_high']=np.quantile(b,[.025,.975])
    return r

def paired(d,label,reps):
    d=np.asarray(d,float);d=d[np.isfinite(d)];r=summary(d,label,reps)
    r['n_pairs']=r.pop('n');r['mean_difference']=r.pop('mean');r.update(p_value=np.nan,p_wilcoxon=np.nan)
    if len(d)>1:
        if not np.any(np.abs(d)>1e-12):r['p_value']=r['p_wilcoxon']=1.
        else:
            n=len(d);obs=abs(d.mean());gen=rng(('signflip',label))
            if n<=16:
                signs=np.array(list(itertools.product([-1,1],repeat=n)),dtype=float)
                r['p_value']=float(np.mean(abs(signs@d/n)>=obs-1e-12))
            else:
                null=abs(gen.choice([-1,1],size=(reps,n))@d/n)
                r['p_value']=float((1+np.sum(null>=obs-1e-12))/(reps+1))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');r['p_wilcoxon']=float(stats.wilcoxon(np.round(d,12),zero_method='wilcox',method='auto').pvalue)
    return r

def holm(values,family_size):
    v=np.asarray(values,float);out=np.full(len(v),np.nan);ids=np.flatnonzero(np.isfinite(v));order=ids[np.argsort(v[ids])];running=0.
    for rank,i in enumerate(order):running=max(running,(family_size-rank)*v[i]);out[i]=min(1.,running)
    return out

def definitions(vv):
    """Linear weights define estimands; ALL nonzero cells are required for each seed."""
    ds=[]
    for v in vv:
        if v['name']!=BASELINE:ds.append((v['name']+' minus '+BASELINE,'vs_original',{v['name']:1.,BASELINE:-1.}))
    for f in FACTORS:
        ds.append((f+'_on-minus-off','main_effect',{v['name']:(1 if v[f] else -1)/8 for v in vv}))
    for a,b in itertools.combinations(FACTORS,2):
        ds.append((a+'x'+b,'two_factor_interaction',{v['name']:(1 if v[a] else -1)*(1 if v[b] else -1)/4 for v in vv}))
    # Predeclared conditional effects clarify the two coupled pairs.
    for a,b in [('P','R'),('R','P'),('S','L'),('L','S')]:
        for level in [0,1]:
            ds.append((f'{a}_on-minus-off_at_{b}{level}','conditional_effect',
                       {v['name']:(1 if v[a] else -1)/4 for v in vv if v[b]==level}))
    return ds

def seed_contrasts(g,plan,metric,weights):
    rows=[]
    for seed in plan['seeds']:
        block=g[g.seed==seed].set_index('variant');needed=list(weights);reason=''
        if not set(needed)<=set(block.index):reason='missing_variant'
        elif not block.loc[needed,'eligible'].all():reason='failed_missing_or_invalid_variant'
        elif block.loc[needed,'workload_hash'].nunique()!=1:reason='unmatched_workload'
        elif not np.isfinite(pd.to_numeric(block.loc[needed,metric],errors='coerce').to_numpy(float)).all():reason='undefined_metric'
        value=np.nan if reason else float(sum(weights[v]*block.loc[v,metric] for v in needed))
        rows.append(dict(seed=seed,difference=value,eligible=not reason,exclusion_reason=reason,required_cells=len(needed)))
    return rows

def analyze(df,plan,out,reps=10000):
    out=Path(out);expected=len(plan['seeds']);summ=[];pairs=[];seed_rows=[]
    defs=definitions(plan['variants'])
    for c in plan['cases']:
        g=df[df.case==c['name']]
        for v in plan['variants']:
            block=g[g.variant==v['name']]
            for metric in METRICS:
                row=dict(case=c['name'],variant=v['name'],metric=metric,n_expected=expected,
                    eligible_trials=int(block.eligible.sum()),not_run=int((block.status=='not_run').sum()),
                    failed_or_incomplete=int((~block.status.isin(['completed','not_run'])).sum()))
                row.update(summary(pd.to_numeric(block[metric],errors='coerce').where(block.eligible),(c['name'],v['name'],metric),reps));summ.append(row)
        for metric in METRICS:
            for contrast,family,weights in defs:
                values=seed_contrasts(g,plan,metric,weights)
                seed_rows.extend(dict(case=c['name'],metric=metric,contrast=contrast,**r) for r in values)
                row=dict(case=c['name'],metric=metric,contrast=contrast,family=family+('_primary' if metric in PRIMARY else '_secondary'),n_expected=expected)
                row.update(paired([v['difference'] for v in values],(c['name'],contrast,metric),reps));row['n_excluded']=expected-row['n_pairs'];pairs.append(row)
    pd.DataFrame(summ).to_csv(out/'summary_results.csv',index=False)
    result=pd.DataFrame(pairs);result['p_holm']=np.nan;result['family_size']=0
    # Families include ALL maps and outcomes of the declared primary/secondary tier.
    for family,idx in result.groupby('family').groups.items():
        result.loc[idx,'p_holm']=holm(result.loc[idx,'p_value'],len(idx));result.loc[idx,'family_size']=len(idx)
    result.to_csv(out/'significance_tests.csv',index=False);pd.DataFrame(seed_rows).to_csv(out/'seed_contrasts.csv',index=False)
    status=json.loads((out/'completion_status.json').read_text(encoding='utf-8'))
    write_json(out/'analysis_manifest.json',dict(source_input_fingerprint=status['input_fingerprint'],smoke=plan['smoke'],
        ci='Student t interval on independent seed mean differences; percentile bootstrap sensitivity',
        test='two-sided sign-flip of seed mean differences, exact n<=16; Monte Carlo otherwise; symmetry/exchangeability assumption',
        alternative_test='Wilcoxon signed-rank sensitivity, not Holm-adjusted',
        family_definition='Each contrast type x outcome tier, across all planned maps. Undefined tests remain in family size.',
        tables={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['summary_results.csv','significance_tests.csv','seed_contrasts.csv','data_quality.csv']}))
    return result
