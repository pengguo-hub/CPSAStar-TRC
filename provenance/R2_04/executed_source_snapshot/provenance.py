"""Portable source/input identities and verified reuse; no planning decisions."""
import hashlib,json,math
from pathlib import Path
from workload import digest,write_json,validate_workload
from original_runtime import source_audit
ROOT=Path(__file__).resolve().parent

def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def execution_sources():
    names=['original_runtime.py','common.py','run.py','worker.py','workload.py','recorder_base.py','observations.py',
           'exposure.py','mechanism.py','provenance.py','execution.py','integration/path_planner_lifelong.py','configs/experiment.json','configs/od_patterns.json']
    files=[ROOT/n for n in names]+sorted((ROOT/'vendor').rglob('*.py'))
    return {p.relative_to(ROOT).as_posix():file_hash(p) for p in files}
def execution_hash():return digest(execution_sources())
def identity(job):return {k:job[k] for k in ['case','seed','variant','purpose','code_hash','condition','workload_hash']}
def job_hash(job):return digest(identity(job))
def verify_job(job):
    sources=execution_sources()
    if digest(sources)!=job['code_hash']:raise RuntimeError('Runtime source changed')
    if job_hash(job)!=job['job_hash']:raise RuntimeError('Job identity mismatch')
    if not all(r['matches'] for r in source_audit()):raise RuntimeError('Original source bytes changed')
    w=json.loads(Path(job['workload_file']).read_text(encoding='utf-8'));validate_workload(w)
    if w['workload_hash']!=job['workload_hash'] or w['case']!=job['condition'] or w['seed']!=job['seed']:raise RuntimeError('Frozen input mismatch')
    if job['variant'] not in ('full','control'):raise ValueError('Unknown arm')
    return w,sources

def validate_completed(result,job):
    row=result['row']
    for k in ['case','seed','variant','purpose','code_hash','job_hash','workload_hash']:assert row[k]==job[k],k
    assert result['execution_sources']==execution_sources()
    if row['status']!='completed':return False
    H=job['condition']['horizon'];assert row['observed_time']==row['requested_horizon']==H==500
    assert row['eligible'] and row['ledger_valid'] and row['time_balance_valid'] and row['source_assigned_identity']
    assert len(result['executed_frames'])==H+1 and len(result['timeline'])==H
    w=json.loads(Path(job['workload_file']).read_text(encoding='utf-8'))
    assert result['executed_frames'][0]['positions']==w['initial_positions']
    assert len(result['requests'])==len(w['requests'])
    for metric in ['static_congestion_potential','throughput','queue_length']:assert math.isfinite(row[metric])
    for metric in ['waiting_time','flow_time']:assert row[metric] is None and row['cohort_n']==0 or isinstance(row[metric],(int,float)) and math.isfinite(row[metric])
    settings=result['settings'];assert settings['soft_congestion']==(job['variant']=='full')
    assert settings['original_reservations'] and settings['persistent_hold_fix_applied'] is False
    assert settings['max_expand_enabled'] is False and settings['trial_wall_timeout'] is None
    return True

def cached_result(out,key,job):
    out=Path(out);p=out/'runs'/f'{key}.json';rp=out/'receipts'/f'{key}.json'
    if not p.exists() and not rp.exists():return None
    assert p.exists() and rp.exists(),f'{key}: incomplete result/receipt; preserve and inspect'
    receipt=json.loads(rp.read_text(encoding='utf-8'));r=json.loads(p.read_text(encoding='utf-8'))
    assert receipt['job_hash']==job_hash(job) and receipt['result_sha256']==file_hash(p),'result identity/content differs'
    assert receipt['code_hash']==job['code_hash']
    attempt=out/receipt['attempt_directory'];meta=json.loads((attempt/'attempt.json').read_text(encoding='utf-8'))
    assert meta['status']==r['row']['status']==receipt['status']
    assert file_hash(attempt/'selected_result.json')==receipt['result_sha256']
    if r['row']['status']=='completed':validate_completed(r,job)
    return r

def result_fingerprint(out):
    out=Path(out);files=[out/x for x in ['run_manifest.json','raw_results.csv','data_quality.csv']]
    for sub in ['runs','workloads','receipts','jobs']:files+=sorted((out/sub).glob('*.json'))
    files+=sorted((out/'attempts').glob('*/*/attempt.json'))
    return digest({p.relative_to(out).as_posix():file_hash(p) for p in files})
def require_audit(out):
    out=Path(out);s=json.loads((out/'independent_replay_status.json').read_text(encoding='utf-8'))
    assert s['result_fingerprint']==result_fingerprint(out),'Changed data: rerun audit_results.py'
    assert s['audit_sha256']==file_hash(ROOT/'audit_results.py'),'Changed auditor: rerun audit_results.py'
    assert s['execution_code_hash']==execution_hash(),'Different runtime source'
    return s
