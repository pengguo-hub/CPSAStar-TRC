"""Prepare all frozen task lists and initial states. Executes zero simulations."""
from pathlib import Path
import gzip,json
from experiments.revision.R2_04_operational_metrics.workload import ROOT, plan_cases, build_workload, validate_workload, write_json
from experiments.revision.R2_04_operational_metrics.provenance import file_hash, execution_hash
def main():
    out=ROOT/'prepared_inputs';out.mkdir(exist_ok=True);rows=[]
    for c in plan_cases():
        for seed in [7,8,39,40,41,42,43]:
            w=build_workload(c,seed);validate_workload(w)
            p=out/f'{c["name"]}_{seed}.json.gz'
            data=json.dumps(w,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
            p.write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
            rows.append(dict(file=p.name,sha256=file_hash(p),workload_hash=w['workload_hash'],case=c['name'],seed=seed,
                             purpose='smoke' if seed<39 else 'formal',requests=len(w['requests'])))
    write_json(out/'index.json',dict(simulations_executed=0,execution_code_hash=execution_hash(),files=rows))
    print('Prepared',len(rows),'complete workloads;',len(rows)*3000,'request records; ZERO simulations.')
if __name__=='__main__':main()
