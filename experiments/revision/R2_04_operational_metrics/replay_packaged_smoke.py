"""Independently replay all packaged smoke evidence; launches no simulation."""
from pathlib import Path
import argparse,gzip,json,hashlib
from experiments.revision.R2_04_operational_metrics.analyze import audit_one, summarize_records
from experiments.revision.R2_04_operational_metrics.workload import ROOT, build_workload, plan_cases, validate_workload, digest
from experiments.revision.R2_04_operational_metrics.provenance import execution_sources, execution_hash, file_hash
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=True)
    base=ROOT/'validation/smoke_evidence';index=json.loads((base/'index.json').read_text())
    assert index['execution_code_hash']==execution_hash()
    cases={c['name']:c for c in plan_cases()};rows=[];audit=[]
    for item in index['records']:
        p=base/item['file'];assert file_hash(p)==item['gzip_sha256'];raw=gzip.decompress(p.read_bytes())
        assert hashlib.sha256(raw).hexdigest()==item['result_sha256']==item['receipt']['result_sha256']
        r=json.loads(raw);row=r['row'];assert row['purpose']=='smoke' and row['seed'] in [7,8]
        assert row['status']=='completed' and row['code_hash']==execution_hash() and r['execution_sources']==execution_sources()
        assert item['receipt']['attempt_id']==row['attempt_id']==item['attempt']['attempt_id']
        assert item['attempt']['result_sha256']==item['result_sha256']
        assert item['attempt']['status']==item['receipt']['status']==row['status']
        w=build_workload(cases[row['case']],row['seed']);validate_workload(w);assert w['workload_hash']==row['workload_hash']
        info=dict(case=row['case'],map=row['map'],fleet=row['fleet'],mode=row['od_mode'],seed=row['seed'],variant=row['variant'],
                  status='completed',attempt_count=1,reason='',**audit_one(r,w))
        audit.append(info);rows.append(row);print('REPLAY',row['case'],row['seed'],row['variant'],flush=True)
    assert len(rows)==72 and len({(r['case'],r['seed'],r['variant']) for r in rows})==72
    return summarize_records(audit,rows,out,'smoke',[7,8])
if __name__=='__main__':raise SystemExit(main())
