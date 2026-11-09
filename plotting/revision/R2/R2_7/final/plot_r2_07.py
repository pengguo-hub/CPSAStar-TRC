from __future__ import annotations
import argparse, csv, hashlib, io, itertools, json, math, zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats

ROOT = 'results_merged_seed42_46'
SEEDS = [42, 43, 44, 45, 46]
MAP_ORDER = ['STANDARD', 'FRANSEN', 'RING']
FACTOR_ORDER = ['S', 'L', 'P', 'R']
METRIC_UNITS = {
    'throughput':'tasks / step', 'throughput_fixed_window':'tasks / step',
    'waiting_time':'steps / completed request', 'flow_time':'steps / completed request',
    'waiting_all_arrived':'steps / supplied request',
    'restricted_flow_all_arrived':'steps / supplied request',
    'queue_length':'unassigned tasks', 'source_field_exposure':'S-dependent field units',
    'source_raw_slot_exposure':'raw slot visit counts', 'completion_fraction':'fraction',
    'planning_seconds':'seconds / trial', 'planning_p95':'seconds / planning step',
    'loop_wall_seconds':'seconds / trial', 'instrumented_pure_seconds':'seconds / trial',
    'queue_wait_all_arrived':'steps / supplied request',
    'assigned_wait_all_arrived':'steps / supplied request',
}
ALL_METRICS = list(METRIC_UNITS)
PRIMARY_METRICS = ['throughput', 'waiting_time', 'flow_time', 'queue_length']
FIGURE_METRICS = {
    'throughput': ('Throughput', 'tasks / step'),
    'waiting_time': ('Waiting time\n(steps/request)', 'steps / completed request'),
    'queue_length': ('Mean task queue\n(unassigned requests)', 'unassigned requests'),
    'planning_seconds': ('Planning time\n(s)', 'seconds / trial'),
}
COLORS = {'S':'#16718D', 'L':'#C27B22', 'P':'#67835A', 'R':'#96618C'}
MARKERS = {'S':'o', 'L':'s', 'P':'^', 'R':'D'}
MAP_COLORS = {'line': '#267BA5', 'shelf': '#AEB4BA', 'shelf_edge': '#777F87', 'station': '#9345BA', 'station_edge': '#7B379E'}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def load_and_audit(src: Path, out: Path):
    zf=zipfile.ZipFile(src, 'r')
    manifest=json.loads(zf.read(f'{ROOT}/run_manifest.json').decode('utf-8'))
    plan=manifest['plan']
    assert plan['seeds']==SEEDS and plan['expected_trials']==240 and plan['horizon']==500
    assert plan['wall_timeout'] is None and plan['baseline']=='S1_L0_P1_R1'
    assert len(plan['variants'])==16 and len(plan['cases'])==3
    frames=[]; csv_hashes={}; raw_bytes={}; quality_frames=[]; statuses={}
    for seed in SEEDS:
        member=f'{ROOT}/merge_sources/seed{seed}/raw_results.csv'
        raw=zf.read(member); raw_bytes[seed]=raw; csv_hashes[member]=sha256(raw)
        frames.append(pd.read_csv(io.BytesIO(raw)))
        qmember=f'{ROOT}/merge_sources/seed{seed}/data_quality.csv'
        quality_frames.append(pd.read_csv(io.BytesIO(zf.read(qmember))))
        smember=f'{ROOT}/merge_sources/seed{seed}/completion_status.json'
        statuses[seed]=json.loads(zf.read(smember).decode('utf-8'))
    df=pd.concat(frames, ignore_index=True)
    quality=pd.concat(quality_frames, ignore_index=True)

    # Hard completeness and pairing checks.
    assert len(df)==240 and df.trial_id.nunique()==240
    assert df.status.eq('completed').all() and df.eligible.eq(True).all()
    assert df.task_ledger_valid.eq(True).all() and df.completed_horizon.eq(True).all()
    assert df.console_summary_present.eq(True).all()
    assert df.arrived.eq(3000).all() and df.observed_time.eq(500).all()
    assert set(df.seed.astype(int))==set(SEEDS)
    assert df.groupby(['map','seed']).size().eq(16).all()
    assert df.groupby(['map','seed']).variant.nunique().eq(16).all()
    assert df.groupby(['map','seed']).workload_hash.nunique().eq(1).all()
    assert df.code_hash.nunique()==1 and df.code_hash.iloc[0]==plan['code_hash']
    assert len(quality)==240 and quality.eligible.eq(True).all() and quality.status.eq('completed').all()
    for seed in SEEDS:
        st=statuses[seed]
        assert st['expected_trials']==st['recorded_trials']==st['eligible_trials']==48
        assert st['status_counts']=={'completed':48} and st['console_missing']==0

    # Verify every readable run JSON against the CSV row; keep all CSV rows regardless.
    json_good=[]; json_bad=[]; compare_metrics=ALL_METRICS + ['completed','unfinished','arrived','observed_time','rollback_count','priority_swaps']
    for r in df.itertuples(index=False):
        member=f'{ROOT}/runs/{r.trial_id}.json'
        try:
            raw=zf.read(member); obj=json.loads(raw.decode('utf-8')); jr=obj['row']
            if jr.get('trial_id') != r.trial_id: raise ValueError('trial_id mismatch')
            for m in compare_metrics:
                a=float(getattr(r,m)); b=float(jr[m])
                if not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10):
                    raise ValueError(f'{m}: CSV={a}, JSON={b}')
            json_good.append(r.trial_id)
        except Exception as exc:
            json_bad.append({'trial_id':r.trial_id,'member':member,'error':type(exc).__name__+': '+str(exc)})
    assert len(json_good)==237 and len(json_bad)==3

    # Copy source CSV members byte-for-byte, without rewriting them.
    source_dir=out/'source_raw_csvs'; source_dir.mkdir(parents=True,exist_ok=True)
    for seed,raw in raw_bytes.items():
        target=source_dir/f'seed{seed}_raw_results.csv'; target.write_bytes(raw)
        assert sha256(target.read_bytes())==csv_hashes[f'{ROOT}/merge_sources/seed{seed}/raw_results.csv']
    # A convenience concatenation, in original seed-file order and original row order.
    df.to_csv(out/'R2_07_raw_results_240.csv',index=False,lineterminator='\n')
    quality.to_csv(out/'R2_07_data_quality_240.csv',index=False,lineterminator='\n')

    audit={
        'source_zip':src.name,'source_zip_sha256':sha256_file(src),
        'plan_revision':plan['revision'],'code_hash':plan['code_hash'],
        'seeds':SEEDS,'maps':MAP_ORDER,'variants_per_map_seed':16,
        'expected_trials':240,'csv_trials_used':int(len(df)),
        'eligible_trials':int(df.eligible.sum()),'completed_trials':int(df.status.eq('completed').sum()),
        'complete_map_seed_blocks':int(df.groupby(['map','seed']).ngroups),
        'trials_per_map':{m:int((df['map']==m).sum()) for m in MAP_ORDER},
        'trials_per_seed':{str(s):int((df.seed==s).sum()) for s in SEEDS},
        'all_3000_requests_and_500_steps':bool(df.arrived.eq(3000).all() and df.observed_time.eq(500).all()),
        'all_task_ledgers_valid':bool(df.task_ledger_valid.eq(True).all()),
        'all_horizons_complete':bool(df.completed_horizon.eq(True).all()),
        'all_console_summary_flags_present':bool(df.console_summary_present.eq(True).all()),
        'readable_run_json_metric_crosschecks':len(json_good),
        'unreadable_run_json_count':len(json_bad),'unreadable_run_json':json_bad,
        'source_raw_csv_sha256':csv_hashes,
        'seed_completion_status':{str(k):v for k,v in statuses.items()},
        'decision':'All 240 eligible raw_results.csv rows are used. Three unreadable final run JSON members do not remove their complete, eligible aggregate CSV rows. The other 237 JSON rows match CSV values for all checked metrics.',
        'limitations':'For the three unreadable JSON members, request-level event/trajectory payloads cannot be independently re-read from this archive. Their aggregate metrics are retained from the source raw_results.csv and are marked completed/eligible in the archived data_quality.csv and completion_status.json.'
    }
    (out/'R2_07_source_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    return zf, plan, df, audit


def factor_values(block: pd.DataFrame, metric: str):
    vals={tuple(int(getattr(r,f)) for f in FACTOR_ORDER):float(getattr(r,metric)) for r in block.itertuples(index=False)}
    if len(vals)!=16: raise ValueError('Expected exactly 16 unique factorial cells')
    return vals


def effect_vector(vals, contrast):
    # For a main factor S/L/P/R, average [outcome with factor enabled -
    # outcome with factor disabled] over all 8 settings of the other factors.
    if contrast in FACTOR_ORDER:
        fidx=FACTOR_ORDER.index(contrast); others=[i for i in range(4) if i!=fidx]; diffs=[]
        for bits in itertools.product([0,1],repeat=3):
            z=[0,0,0,0]
            for j,b in zip(others,bits): z[j]=b
            z1=z.copy(); z1[fidx]=1
            diffs.append(vals[tuple(z1)]-vals[tuple(z)])
        return float(np.mean(diffs))
    if 'x' in contrast:
        a,b=contrast.split('x'); ia,ib=FACTOR_ORDER.index(a),FACTOR_ORDER.index(b)
        other=[i for i in range(4) if i not in (ia,ib)]; diffs=[]
        for bits in itertools.product([0,1],repeat=2):
            z=[0,0,0,0]
            for j,v in zip(other,bits):z[j]=v
            z11=z.copy();z11[ia]=1;z11[ib]=1
            z10=z.copy();z10[ia]=1;z10[ib]=0
            z01=z.copy();z01[ia]=0;z01[ib]=1
            z00=z.copy();z00[ia]=0;z00[ib]=0
            diffs.append(vals[tuple(z11)]-vals[tuple(z10)]-vals[tuple(z01)]+vals[tuple(z00)])
        return float(np.mean(diffs))
    if '|' in contrast:
        a,cond=contrast.split('|'); fixed_factor=cond[0]; fixed_level=int(cond[1]); ia=FACTOR_ORDER.index(a); ic=FACTOR_ORDER.index(fixed_factor)
        others=[i for i in range(4) if i not in (ia,ic)]; diffs=[]
        for bits in itertools.product([0,1],repeat=2):
            z=[0,0,0,0];z[ic]=fixed_level
            for j,b in zip(others,bits):z[j]=b
            z1=z.copy();z1[ia]=1
            diffs.append(vals[tuple(z1)]-vals[tuple(z)])
        return float(np.mean(diffs))
    raise ValueError(contrast)


def exact_signflip(values):
    x=np.asarray(values,float); obs=abs(float(x.mean()))
    stats0=[abs(float(np.mean(x*np.asarray(s)))) for s in itertools.product([-1.,1.],repeat=len(x))]
    return float(sum(v>=obs-1e-12 for v in stats0)/len(stats0))


def holm_adjust(pvalues):
    p=np.asarray(pvalues,float);n=len(p);order=np.argsort(p);out=np.empty(n);running=0.
    for rank,idx in enumerate(order):
        running=max(running,(n-rank)*p[idx]);out[idx]=min(1.,running)
    return out


def calculate_effects(df: pd.DataFrame):
    contrasts=FACTOR_ORDER + [a+'x'+b for a,b in itertools.combinations(FACTOR_ORDER,2)] + [
        'P|R0','P|R1','R|P0','R|P1','S|L0','S|L1','L|S0','L|S1']
    rows=[];seed_rows=[]
    for map_name in MAP_ORDER:
        mdf=df[df['map']==map_name]
        for metric in ALL_METRICS:
            for contrast in contrasts:
                vals=[]
                for seed,block in mdf.groupby('seed'):
                    fvals=factor_values(block,metric)
                    effect=effect_vector(fvals,contrast)
                    vals.append((int(seed),effect))
                    seed_rows.append({'map':map_name,'metric':metric,'contrast':contrast,'seed':int(seed),'effect':effect})
                arr=np.array([x[1] for x in vals],float);n=len(arr);mean=float(arr.mean());sd=float(arr.std(ddof=1));se=sd/math.sqrt(n)
                crit=float(stats.t.ppf(.975,n-1))
                # Deterministic nonparametric bootstrap of the five independent seed effects.
                seed_int=int(hashlib.sha256(f'{map_name}|{metric}|{contrast}'.encode()).hexdigest()[:8],16)
                rng=np.random.default_rng(seed_int);boot=arr[rng.integers(0,n,size=(20000,n))].mean(axis=1)
                blo,bhi=np.quantile(boot,[.025,.975])
                try: pw=float(stats.wilcoxon(np.round(arr,12),zero_method='wilcox',method='auto').pvalue) if np.any(np.abs(arr)>1e-12) else 1.
                except Exception: pw=np.nan
                family_type='main_effect' if contrast in FACTOR_ORDER else ('two_factor_interaction' if 'x' in contrast else 'conditional_effect')
                tier='primary' if metric in PRIMARY_METRICS else 'secondary'
                rows.append({'map':map_name,'metric':metric,'unit':METRIC_UNITS[metric],'contrast':contrast,
                    'contrast_type':family_type,'outcome_tier':tier,'n_seeds':n,'seeds_used':';'.join(str(s) for s,_ in vals),
                    'estimate':mean,'sd_across_seed_effects':sd,'se':se,'ci95_low':mean-crit*se,'ci95_high':mean+crit*se,
                    'bootstrap95_low':float(blo),'bootstrap95_high':float(bhi),'p_exact_signflip':exact_signflip(arr),
                    'p_wilcoxon_sensitivity':pw,'seed_effects':';'.join(f'{s}:{v:.15g}' for s,v in vals)})
    effects=pd.DataFrame(rows)
    effects['holm_family']=effects['contrast_type']+'_'+effects['outcome_tier']
    effects['holm_family_size']=0;effects['p_holm']=np.nan
    for fam,idx in effects.groupby('holm_family').groups.items():
        effects.loc[idx,'holm_family_size']=len(idx)
        effects.loc[idx,'p_holm']=holm_adjust(effects.loc[idx,'p_exact_signflip'].to_numpy(float))
    seed_effects=pd.DataFrame(seed_rows)
    return effects,seed_effects


def variant_summary(df):
    cols=['throughput','waiting_time','flow_time','waiting_all_arrived','restricted_flow_all_arrived','queue_length',
          'source_raw_slot_exposure','source_field_exposure','planning_seconds','loop_wall_seconds','completion_fraction']
    rows=[]
    for (m,v),g in df.groupby(['map','variant'],sort=False):
        row={'map':m,'variant':v,'n_trials':len(g),'seeds':';'.join(map(str,sorted(g.seed.unique())))}
        for c in cols:
            row[c+'_mean']=float(g[c].mean());row[c+'_sd']=float(g[c].std(ddof=1))
        rows.append(row)
    return pd.DataFrame(rows)


def map_layouts():
    """Return the exact shelf/workstation cells from the R2-07 map_config.py."""
    # 16 x 11 standard layout
    standard_shelves = {
        (x, y)
        for x in range(1, 14, 2)
        for y in (*range(1, 5), *range(6, 10))
    }
    standard_stations = {(15, y) for y in range(3, 8)}

    # 20 x 20 Fransen layout
    fransen_shelves = {
        (x, y)
        for y in (2, 5, 8, 11, 14, 17)
        for x in (2, 5, 8, 11, 14, 17)
    }
    fransen_stations = {
        (0, 5), (0, 14), (5, 0), (5, 19),
        (14, 0), (14, 19), (19, 5), (19, 14),
    }

    # 20 x 20 three-ring layout, including the two-cell entrances on each side.
    ring_shelves = set()
    outer_x0, outer_x1, outer_y0, outer_y1 = 2, 17, 2, 17
    mid_x0, mid_x1, mid_y0, mid_y1 = 5, 14, 5, 14
    entrances = (9, 10)
    for x in range(outer_x0, outer_x1 + 1):
        if x not in entrances:
            ring_shelves.add((x, outer_y0))
            ring_shelves.add((x, outer_y1))
    for y in range(outer_y0 + 1, outer_y1):
        if y not in entrances:
            ring_shelves.add((outer_x0, y))
            ring_shelves.add((outer_x1, y))
    for x in range(mid_x0, mid_x1 + 1):
        if x not in entrances:
            ring_shelves.add((x, mid_y0))
            ring_shelves.add((x, mid_y1))
    for y in range(mid_y0 + 1, mid_y1):
        if y not in entrances:
            ring_shelves.add((mid_x0, y))
            ring_shelves.add((mid_x1, y))
    ring_stations = {
        (x, y)
        for x in range(8, 12)
        for y in range(8, 12)
        if x in (8, 11) or y in (8, 11)
    }

    return [
        (16, 11, standard_shelves, standard_stations),
        (20, 20, fransen_shelves, fransen_stations),
        (20, 20, ring_shelves, ring_stations),
    ]


def draw_map(ax, width, height, shelves, stations, map_label):
    """Draw map cells using the palette and grid style of plot_r2_05_compact."""
    from matplotlib.patches import Rectangle

    ax.set_facecolor("white")
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.set_aspect("equal", adjustable="box")

    # Match R2-05: fine one-cell grid, stronger guide lines every five cells.
    for x in range(0, width + 1):
        ax.axvline(
            x,
            color=MAP_COLORS["shelf_edge"] if x % 5 == 0 else "#E6E9EC",
            linewidth=0.48 if x % 5 == 0 else 0.25,
            alpha=0.9,
            zorder=0,
        )
    for y in range(0, height + 1):
        ax.axhline(
            y,
            color=MAP_COLORS["shelf_edge"] if y % 5 == 0 else "#E6E9EC",
            linewidth=0.48 if y % 5 == 0 else 0.25,
            alpha=0.9,
            zorder=0,
        )

    # Shelves: the same grey palette used in the R2-05 map schematics.
    for x, y in sorted(shelves):
        ax.add_patch(
            Rectangle(
                (x, y), 1, 1,
                facecolor=MAP_COLORS["shelf"],
                alpha=0.78,
                edgecolor=MAP_COLORS["shelf_edge"],
                linewidth=0.22,
                zorder=2,
            )
        )

    # Workstations / outbound cells: the same purple palette as R2-05.
    for x, y in sorted(stations):
        ax.add_patch(
            Rectangle(
                (x, y), 1, 1,
                facecolor=MAP_COLORS["station"],
                alpha=0.60,
                edgecolor=MAP_COLORS["station_edge"],
                linewidth=0.45,
                zorder=3,
            )
        )

    # Match the five-cell coordinate ticks in the R2-05 reference map.
    xstep = max(5, int(math.ceil(width / 5 / 5)) * 5)
    ystep = max(5, int(math.ceil(height / 5 / 5)) * 5)
    ax.set_xticks(list(range(0, width + 1, xstep)))
    ax.set_yticks(list(range(0, height + 1, ystep)))
    ax.tick_params(axis="both", length=0, pad=1.5, labelsize=6.5)

    ax.set_title(f"{map_label} ({width}×{height})", pad=4, fontsize=8.5)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#AEB4BA")
        spine.set_linewidth(0.55)


def make_figure(effects: pd.DataFrame, out_path: Path):
    # A dedicated top row holds the three actual map layouts.
    n_metrics = len(FIGURE_METRICS)
    fig = plt.figure(figsize=(15.4, 2.0 + 2.2 * n_metrics))
    gs = fig.add_gridspec(
        n_metrics + 1, 3,
        height_ratios=[1.05] + [1.45] * n_metrics,
        left=0.185, right=0.985, top=0.91, bottom=0.085,
        hspace=0.58, wspace=0.18
    )

    layouts = map_layouts()
    map_labels = ['Map A', 'Map B', 'Map C']
    for col, (width, height, shelves, stations) in enumerate(layouts):
        map_ax = fig.add_subplot(gs[0, col])
        draw_map(map_ax, width, height, shelves, stations, map_labels[col])
        pos = map_ax.get_position()
        map_ax.set_position([
            pos.x0,
            pos.y0 - 0.05,
            pos.width,
            pos.height
        ])

    axes = np.empty((n_metrics, 3), dtype=object)
    offsets = {'S': 0.0, 'L': 1.0, 'P': 2.0, 'R': 3.0}

    for r, (metric, (title, unit)) in enumerate(FIGURE_METRICS.items()):
        for c, map_name in enumerate(MAP_ORDER):
            # Every map panel has the same physical size but an independent x scale.
            ax = fig.add_subplot(gs[r + 1, c])
            axes[r, c] = ax

            sub = effects[(effects['map'] == map_name) & (effects['metric'] == metric)]
            if len(sub) != len(FACTOR_ORDER) or set(sub.contrast) != set(FACTOR_ORDER):
                raise ValueError(
                    f'Panel data mismatch for map={map_name}, metric={metric}: '
                    f'found contrasts={sub.contrast.tolist()}'
                )
            for factor in FACTOR_ORDER:
                row = sub[sub.contrast == factor].iloc[0]
                y = offsets[factor]

                # Draw confidence intervals first, then the point estimate.
                ax.errorbar(
                    row.estimate, y,
                    xerr=[[row.estimate - row.ci95_low],
                          [row.ci95_high - row.estimate]],
                    fmt='none', ecolor=COLORS[factor],
                    elinewidth=2.0, capsize=3.2, capthick=1.35,
                    zorder=3
                )
                ax.plot(
                    row.estimate, y, marker=MARKERS[factor],
                    linestyle='none', color=COLORS[factor],
                    markersize=4.2, markeredgecolor='white',
                    markeredgewidth=0.35, zorder=4
                )

            ax.axvline(0, color='#929AA2', linewidth=0.9,
                       linestyle=(0, (3, 2)), zorder=0)
            ax.set_yticks([0, 1, 2, 3], labels=['S', 'L', 'P', 'R'] if c == 0 else [])
            ax.invert_yaxis()
            ax.grid(axis='x', color='#E5E8EB', linewidth=0.7)
            ax.set_axisbelow(True)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(True)
            ax.spines['left'].set_color('#AAB1B8')
            ax.spines['left'].set_linewidth(0.7)
            ax.spines['bottom'].set_color('#AAB1B8')
            ax.tick_params(axis='y', length=3, width=0.7, color='#AAB1B8', labelsize=9)
            ax.tick_params(axis='x', labelsize=8)

        # Compact two-line row label; no redundant "higher/lower is better" text.
        axes[r, 0].set_ylabel(
            title,
            fontsize=9, rotation=0, ha='right', va='center', labelpad=9
        )

    # Tight, independent x limits for every panel. Include zero so the
    # direction of each factor effect remains immediately visible.
    from matplotlib.ticker import MaxNLocator
    for r, metric in enumerate(FIGURE_METRICS):
        for c, map_name in enumerate(MAP_ORDER):
            sub = effects[(effects['map'] == map_name) & (effects['metric'] == metric)]
            lo = min(float(sub.ci95_low.min()), 0.0)
            hi = max(float(sub.ci95_high.max()), 0.0)
            span = max(hi - lo, 1e-9)
            pad = span * 0.08
            axes[r, c].set_xlim(lo - pad, hi + pad)
            axes[r, c].xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
            axes[r, c].tick_params(axis='x', labelbottom=True)

    handles = [
        plt.Line2D(
            [0], [0], marker=MARKERS[f], color='none',
            markerfacecolor=COLORS[f], markeredgecolor='none',
            markersize=7,
            label={
                'S': 'S  Gaussian smoothing',
                'L': 'L  Look-ahead congestion',
                'P': 'P  Priority adjustment',
                'R': 'R  Rollback',
            }[f]
        )
        for f in FACTOR_ORDER
    ]
    fig.legend(
        handles=handles, loc='upper center', ncol=4, frameon=False,
        bbox_to_anchor=(0.58, 0.90), fontsize=9
    )

    # This describes the plotted contrast without the less intuitive "on − off" notation.
    fig.text(0.585, 0.05, 'Mean outcome with factor enabled − mean outcome with factor disabled', ha='center', va='center', fontsize=10)

    for ext in ['png', 'pdf']:
        path = out_path.with_suffix('.' + ext)
        fig.savefig(path, dpi=600 if ext == 'png' else None, bbox_inches='tight')
    plt.close(fig)


def choose_results_zip(script_dir: Path):
    # 1) Prefer the expected result archive beside this script.
    expected = script_dir / 'R2_7_results_merged_seed42_46.zip'
    if expected.is_file():
        print(f'Using results archive: {expected}')
        return expected

    # 2) Accept a uniquely matching renamed/copy-suffixed archive.
    matches = sorted(script_dir.glob('R2_7_results_merged_seed42_46*.zip'))
    if len(matches) == 1:
        print(f'Using results archive: {matches[0]}')
        return matches[0]

    # 3) If it is not beside the script, ask the user to select it.
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askopenfilename(
            title='Select R2-07 results ZIP',
            initialdir=str(script_dir),
            filetypes=[('ZIP archives', '*.zip'), ('All files', '*.*')]
        )
        root.destroy()
        if selected:
            return Path(selected).resolve()
    except Exception as exc:
        print(f'Could not open the file-selection window: {exc}')

    return None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--results',default=None,
                    help='R2-07 results ZIP; if omitted, the script searches beside itself or opens a file picker')
    ap.add_argument('--out',default=None,
                    help='Output directory; defaults to R2_07_output beside this script')
    args=ap.parse_args()

    script_dir=Path(__file__).resolve().parent
    src=Path(args.results).resolve() if args.results else choose_results_zip(script_dir)
    if src is None:
        print('No results ZIP selected. Nothing was changed.')
        return
    if not src.is_file():
        raise FileNotFoundError(f'Results ZIP not found: {src}')

    out=Path(args.out).resolve() if args.out else script_dir/'R2_07_output'
    out.mkdir(parents=True,exist_ok=True)
    zf,plan,df,audit=load_and_audit(src,out)
    effects,seed_effects=calculate_effects(df)
    figure_effects=effects[effects.metric.isin(FIGURE_METRICS)&effects.contrast.isin(FACTOR_ORDER)].copy()

    # Validate the exact figure grid: 3 maps × 4 selected metrics × 4 factors = 48 rows.
    expected_keys = {
        (map_name, metric, factor)
        for map_name in MAP_ORDER
        for metric in FIGURE_METRICS
        for factor in FACTOR_ORDER
    }
    actual_keys = list(zip(
        figure_effects['map'], figure_effects['metric'], figure_effects['contrast']
    ))
    if len(actual_keys) != len(expected_keys) or set(actual_keys) != expected_keys:
        missing = sorted(expected_keys - set(actual_keys))
        unexpected = sorted(set(actual_keys) - expected_keys)
        raise ValueError(
            f'Figure data mapping check failed. Missing={missing}; unexpected={unexpected}'
        )
    if figure_effects.duplicated(['map', 'metric', 'contrast']).any():
        raise ValueError('Duplicate map × metric × factor rows in figure data.')

    effects.to_csv(out/'R2_07_factor_effects_240.csv',index=False,float_format='%.15g')
    seed_effects.to_csv(out/'R2_07_seed_effects_240.csv',index=False,float_format='%.15g')
    figure_effects.to_csv(out/'R2_07_figure_effects_240.csv',index=False,float_format='%.15g')
    variant_summary(df).to_csv(out/'R2_07_variant_summary_240.csv',index=False,float_format='%.15g')
    make_figure(figure_effects,out/'R2_07_compact_ablation_240')
    # Source-member archive: five raw CSVs copied byte-for-byte.
    with zipfile.ZipFile(out/'R2_07_raw_source_csvs_240.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zz:
        for seed in SEEDS:
            p=out/'source_raw_csvs'/f'seed{seed}_raw_results.csv'
            zz.write(p,arcname=f'seed{seed}/raw_results.csv')
    # A concise machine-readable record of statistical limitations.
    statnote={
      'independent_seed_n':5,'exact_two_sided_signflip_minimum_p':0.0625,
      'holm_adjustment':'Within predeclared contrast-type × outcome-tier families, matching the experiment package analysis.py design.',
      'ci':'Pointwise 95% Student t intervals across five independent seed-level factorial contrasts.',
      'bootstrap':'Percentile bootstrap sensitivity intervals across five independent seed-level effects; not a replacement for the t intervals.',
      'interpretation':'Descriptive effect estimates and interval patterns; exact sign-flip resolution at n=5 cannot reach p<0.05.'}
    (out/'R2_07_statistical_method_240.json').write_text(json.dumps(statnote,indent=2),encoding='utf-8')
    print(json.dumps({'source_zip':src.name,'trials_used':len(df),'map_seed_blocks':int(df.groupby(['map','seed']).ngroups),
       'readable_json':audit['readable_run_json_metric_crosschecks'],'unreadable_json':audit['unreadable_run_json_count'],
       'effects_rows':len(effects),'figure_effect_rows':len(figure_effects),'output':str(out)},indent=2))

if __name__=='__main__': main()
