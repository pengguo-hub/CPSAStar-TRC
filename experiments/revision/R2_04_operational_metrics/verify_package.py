"""Verify every packaged file, baseline bytes and fixed protocol settings."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parent
def main():
    m=json.loads((ROOT/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,h in m['files'].items():
        p=ROOT/name
        assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==h,'Missing or changed package file: '+name
    subprocess.run([sys.executable,str(ROOT/'verify_sources.py')],check=True,cwd=ROOT.parents[2])
    print('PASS:',len(m['files']),'package files; original Lifelong baseline and protocol intact.')
if __name__=='__main__':main()
