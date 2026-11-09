"""Produce a result-grounded draft after formal analysis; no invented outcomes."""
import argparse,csv
from pathlib import Path
from experiments.revision.R2_05_scalability.common import read_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();status=read_json(a.analysis/'analysis_status.json')
    if status['purpose']!='formal':p.error('A response with numerical claims requires formal data, not smoke.')
    rows=list(csv.DictReader((a.analysis/'summary_long.csv').open(encoding='utf-8-sig')));lookup={(r['case'],r['metric']):r for r in rows}
    def val(name,metric):
        r=lookup.get((name,metric))
        if r is None or not r['mean']:return 'not available'
        ci=f" (95% CI {float(r['ci_low']):.3f}–{float(r['ci_high']):.3f})" if r['ci_low'] and r['ci_high'] else ' (CI unavailable)'
        return f"{float(r['mean']):.3f}"+ci+f", n={r['n']}"
    text=['# Reviewer 2, Comment 5 — response draft', '', '**Draft for author review. Insert final figure/table identifiers and manuscript line numbers.**', '',
          '> Strengthen the scalability analysis by systematically varying fleet size, map size, task arrival rate, and congestion level.', '',
          'Thank you for this suggestion. We added a controlled scalability study based on the archived Lifelong CPS-A* implementation. The original search, task matching, pickup–delivery phases, failure requeueing, and reservation rules are retained. An explicit input-release interface is used only for the open-demand experiments; passive records do not select or modify paths.', '',
          f"Each formal trial spans 500 simulation steps with no warm-up. The analyzed seeds are {', '.join(map(str,status['seeds']))}."+' No search-expansion cap or trial wall-clock timeout is imposed. We first checked the original backlogged fleet baseline on Map A (16×11). The added experiments vary: (i) fleet size, 10/30/50 AGVs; (ii) map dimensions, 16×11/32×22/48×33 with 30 AGVs and fixed arrival intensity; (iii) proportional expansion to 30/120/270 AGVs with demand scaled by area; (iv) arrival intensity, 0.25/0.5/1.0/2.0 requests per step; and (v) three matched OD couplings on the unchanged 20×20 FRANSEN map.', '',
          'The fleet baseline has 3000 requests available initially. Open-demand conditions are reported separately: they cannot reuse that backlogged baseline. We report both completed/released fraction and the original completed/net-assigned success percentage, explicitly distinguishing the denominators. Planning time, assignment time, the original pure-time formula, and end-to-end wall time are recorded separately. Cumulative planning time excludes measured observer callback work.', '',
          f"The audit contains {status['valid_trials']} complete valid trials out of {status['planned_trials']} planned trials. Unfinished or invalid runs are retained in the audit and excluded from full-run averages. All reported sample sizes are explicit. Error intervals are 95% Student t intervals across independent seeds, not across tasks or frames.", '',
          '| Fleet on Map A | Throughput (tasks/step) | Completed/released fraction | Planning time (s) |','|---|---|---|---|']
    for n in [10,30,50]:text.append(f"| {n} | {val('A_fleet'+str(n),'throughput')} | {val('A_fleet'+str(n),'completion_fraction')} | {val('A_fleet'+str(n),'planning_seconds')} |")
    text+=['','| Extension condition | Throughput (tasks/step) | Planning time (s) |','|---|---|---|']
    for name in ['A_open_base','A_map2_fixed','A_map3_fixed','A_map2_density','A_map3_density','A_rate0.25','A_rate1.0','A_rate2.0']:
        text.append(f"| {name} | {val(name,'throughput')} | {val(name,'planning_seconds')} |")
    text+=['','For traffic demand, the origin sequence, release stream, initial positions, origin-specific shortest transport lengths, and destination marginal counts are matched. Only the OD pairing changes. We measure the resulting short-headway cell-sharing exposure outside service-point neighbourhoods rather than assuming that the three input labels constitute ordered realized congestion levels.','',
           '| OD pairing | Realized encounter fraction | Throughput |','|---|---|---|']
    for level in ['dispersed','intermediate','shared']:text.append(f"| {level} | {val('B_traffic_'+level,'traffic_encounter_rate')} | {val('B_traffic_'+level,'throughput')} |")
    tr=[lookup.get(('B_traffic_'+x,'traffic_encounter_rate'),{}) for x in ['dispersed','intermediate','shared']]
    if all(r.get('mean') for r in tr) and float(tr[0]['mean'])<float(tr[1]['mean'])<float(tr[2]['mean']):
        text+=['','The observed mean exposure follows the input ordering in this dataset. We report the paired uncertainty and individual-seed results; ordered means alone are not proof of three statistically distinct congestion levels.']
    else:text+=['','The realized interaction measurements do not establish a strictly increasing three-level congestion gradient. We therefore present this part as a controlled traffic-demand structure experiment and disclose the non-monotonic or unresolved response, rather than relabelling the inputs as validated low/medium/high congestion.']
    text+=['','The study concerns the behavior of the archived simulation implementation. It does not constitute a new physical collision-correctness validation, and it does not establish large-scale real-time operation. Timing is hardware dependent, and the paper’s Figure 9 pure-time scale is not treated as an end-to-end wall-time guarantee. With five paired seeds, the minimum attainable two-sided exact sign-flip p-value is 0.0625; we avoid unsupported significance claims.', '',
           'The manuscript figures and tables should be cited here after final layout: [Figure …], [Table …], [Section … / lines …].']
    if status['incomplete_or_invalid'] or not status.get('full_formal_matrix_planned'):text.insert(4,'**INCOMPLETE DATA: some planned trials lack valid results. This is not a completed-matrix claim.**')
    out=a.output or a.analysis/'Reviewer_2_5_response_draft.md';out.write_text('\n'.join(text)+'\n',encoding='utf-8');print(out)

if __name__=='__main__':main()
