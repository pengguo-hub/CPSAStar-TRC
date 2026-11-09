from pathlib import Path
import hashlib
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
def main():
 good=0;bad=[]
 for line in (R/'SHA256SUMS.txt').read_text().splitlines():
  digest,name=line.split('  ',1);p=R/name
  if not p.is_file() or sha(p)!=digest:bad.append(name)
  else:good+=1
 print({'verified':good,'mismatches':bad})
 if bad:raise SystemExit(1)
if __name__=='__main__':main()
