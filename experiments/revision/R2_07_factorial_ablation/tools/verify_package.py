"""Standard-library byte verification of the delivered ZIP contents after extraction."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
for row in m['files']:
 p=ROOT/row['path'];assert p.is_file(),row['path'];assert p.stat().st_size==row['size'],row['path']
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
for name in ['run.py','worker.py','verify_sources.py','source_manifest.json','configs/experiment.json','README.md','CPS_A_lifelong/path_planner_lifelong.py','original/CPS_A_lifelong/path_planner_lifelong.py']:
 assert (ROOT/name).is_file(),name
print('PACKAGE PASS:',len(m['files']),'files; required runtime/config/source files present')
