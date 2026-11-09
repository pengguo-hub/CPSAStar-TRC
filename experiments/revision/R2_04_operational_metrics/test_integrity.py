"""Small rejection tests for tampered records; no new experiment is run."""
import argparse,copy,gzip,json
from pathlib import Path
from experiments.revision.R2_04_operational_metrics.workload import ROOT, build_workload, plan_cases, validate_workload, write_json
from experiments.revision.R2_04_operational_metrics.analyze import audit_one
def must_reject(name,fn,results):
    try:fn()
    except (AssertionError,ValueError,RuntimeError) as ex:results.append(dict(test=name,passed=True,rejection=type(ex).__name__))
    else:raise AssertionError('Tampered evidence was accepted: '+name)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();checks=[]
    r=json.loads(gzip.decompress((ROOT/'validation/smoke_evidence/STANDARD_N30_dispersed_7_full.json.gz').read_bytes()))
    c=next(c for c in plan_cases() if c['name']==r['row']['case']);w=build_workload(c,7)
    audit_one(r,w);checks.append(dict(test='untampered complete record accepted',passed=True))
    bad=copy.deepcopy(r);bad['requests'][0]['queue_wait']+=1
    must_reject('changed task waiting ledger',lambda:audit_one(bad,w),checks)
    bad=copy.deepcopy(r);bad['settings']['wait_penalty_coefficient']=0
    must_reject('wrong Full intervention label',lambda:audit_one(bad,w),checks)
    bad=copy.deepcopy(w);bad['requests'][0]['release']=1
    must_reject('changed input without matching identity',lambda:validate_workload(bad),checks)
    bad=copy.deepcopy(r);bad['row']['throughput']+=.1
    must_reject('changed throughput summary',lambda:audit_one(bad,w),checks)
    write_json(a.output,dict(simulations_executed=0,passed=all(x['passed'] for x in checks),checks=checks));print('PASS:',len(checks),'integrity checks; ZERO simulations.')
if __name__=='__main__':main()
