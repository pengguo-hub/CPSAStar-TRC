"""Maintainer-only: regenerate hashes/diffs after a reviewed source edit; not a validation bypass."""
import difflib,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for base in ['CPS_A_lifelong','reference_inputs']:
 for f in sorted((ROOT/base).glob('*.py')):
  original=ROOT/'original'/('CPS_A_lifelong' if base=='CPS_A_lifelong' else 'Lifelong_inputs')/f.name
  if original.exists():
   text=''.join(difflib.unified_diff(original.read_text(encoding='utf-8').splitlines(True),f.read_text(encoding='utf-8').splitlines(True),fromfile=str(original.relative_to(ROOT)),tofile=str(f.relative_to(ROOT))))
   (ROOT/'source_diffs'/f'{base}__{f.name}.diff').write_text(text,encoding='utf-8')
paths=[*ROOT.glob('*.py'),*ROOT.glob('requirements*.txt'),ROOT/'REVISION_ID',*(ROOT/'configs').glob('*.json')]
for base in ['CPS_A_lifelong','reference_inputs','original','tests','tools']:paths.extend((ROOT/base).rglob('*.py'))
for p in sorted(set(paths)):
 rows.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
authority=json.loads((ROOT/'audit/authority_files.json').read_text())
runtime_names={'run.py','worker.py','workload.py','observations.py','verify_sources.py','requirements.txt','requirements-tested.txt','REVISION_ID'}
execution={r['path']:r['sha256'] for r in rows if r['path'] in runtime_names or r['path'].startswith(('CPS_A_lifelong/','reference_inputs/','original/','configs/'))}
h=hashlib.sha256(json.dumps(execution,sort_keys=True,separators=(',',':')).encode()).hexdigest()
value=dict(revision='R2-07',baseline='S1_L0_P1_R1',authority_archive=json.loads((ROOT/'audit/authority_archive.json').read_text()),authority_files=authority,files=rows,execution_hash=h)
(ROOT/'source_manifest.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print('Updated',len(rows),'files; execution hash',h)
