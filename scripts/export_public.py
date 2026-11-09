"""Build a public source-only export, omitting private/large audit archives."""
from pathlib import Path
import zipfile,hashlib,argparse
R=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=R.parent/'CPS-Astar-public-source-only.zip');a=ap.parse_args()
 sums=[]
 with zipfile.ZipFile(a.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted(R.rglob('*')):
   if not p.is_file() or '__pycache__' in p.parts or p.suffix in ['.pyc','.pyo'] or (p.name!='.gitignore' and any(x.startswith('.') for x in p.relative_to(R).parts)):continue
   rel=str(p.relative_to(R))
   if rel.startswith(('provenance/private_source_archives/','provenance/data_archives/','outputs/')) or rel=='SHA256SUMS.txt':continue
   b=p.read_bytes();z.writestr(R.name+'/'+rel,b,compress_type=zipfile.ZIP_DEFLATED);sums.append(hashlib.sha256(b).hexdigest()+'  '+rel)
  z.writestr(R.name+'/SHA256SUMS.txt','\n'.join(sums)+'\n')
 print(a.output.resolve(),a.output.stat().st_size)
if __name__=='__main__':main()
