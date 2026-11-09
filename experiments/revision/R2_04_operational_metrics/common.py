"""Small serialization and provenance utilities; no simulation logic."""
import hashlib,json,platform,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    q.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');q.replace(p)

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def native_state(p):
    return dict(current_time=p.current_time,completed_tasks=p.completed_tasks,agv_tasks=p.agv_tasks,
                task_queue=list(p.task_queue),agv_positions=p.agv_positions,total_assigned_tasks=p.total_assigned_tasks)
