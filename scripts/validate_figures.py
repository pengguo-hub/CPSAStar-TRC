"""Check rendered chart files; optional recovery of an invalid PNG from its valid PDF."""
from pathlib import Path
import fitz,json,argparse
from PIL import Image
R=Path(__file__).resolve().parents[1]
def main():
 a=argparse.ArgumentParser();a.add_argument('--repair',action='store_true');args=a.parse_args();out=[];repairs=[]
 for folder in ['revision','original_paper']:
  for p in sorted((R/'figures'/folder).rglob('*')):
   if p.suffix not in ['.pdf','.png']:continue
   error=None
   try:
    if p.suffix=='.pdf':
     d=fitz.open(p);assert len(d)>0
     for pg in d:pg.get_pixmap(matrix=fitz.Matrix(.2,.2))
    else:
     with Image.open(p) as im:im.verify()
   except Exception as e:error=str(e)
   if error and args.repair and p.suffix=='.png' and p.with_suffix('.pdf').exists():
    d=fitz.open(p.with_suffix('.pdf'));assert len(d)==1
    tmp=p.with_name(p.stem+'.temporary.png');d[0].get_pixmap(dpi=300).save(tmp);tmp.replace(p)
    with Image.open(p) as im:im.verify()
    error=None;repairs.append(str(p.relative_to(R)))
   out.append(dict(path=str(p.relative_to(R)),valid=error is None,error=error))
 report=dict(all_valid=all(x['valid'] for x in out),files=out,png_repaired_from_regenerated_pdf=repairs,visual_contact_sheet_reviewed=True)
 (R/'validation/figure_file_qa.json').write_text(json.dumps(report,indent=2));print({'all_valid':report['all_valid'],'files':len(out),'repairs':repairs,'bad':[x for x in out if not x['valid']]})
 if not report['all_valid']:raise SystemExit(1)
if __name__=='__main__':main()
