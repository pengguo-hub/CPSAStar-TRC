import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import Config,TASK_COUNTS,LOOKAHEAD_BY_MAP,GAMMA_INTERACTION_VALUES,SIGMA_INTERACTION_VALUES,UPDATE_INTERVAL_INTERACTION_VALUES
from instances import get_task_instance

def test_r1_task_counts(): assert TASK_COUNTS=={"A":(50,70),"B":(250,280),"C":(150,200)}
def test_lookahead_switch(): assert LOOKAHEAD_BY_MAP=={"A":True,"B":False,"C":False}
def test_baseline():
    c=Config(); assert (c.alpha,c.beta,c.gamma,c.omega,c.L,c.T,c.sigma_l,c.sigma_t,c.update_interval)==(1.0,0.5,5.0,50.0,1,1,2.0,2.0,20)
def test_cross_unique_count():
    from dataclasses import replace
    from instances import canonical_hash
    b=Config(); cfg=[]
    for g in GAMMA_INTERACTION_VALUES:
        for s in SIGMA_INTERACTION_VALUES: cfg.append(replace(b,gamma=g,sigma_l=s))
    for g in GAMMA_INTERACTION_VALUES:
        for s in SIGMA_INTERACTION_VALUES: cfg.append(replace(b,gamma=g,sigma_t=s))
    for g in GAMMA_INTERACTION_VALUES:
        for k in UPDATE_INTERVAL_INTERACTION_VALUES: cfg.append(replace(b,gamma=g,update_interval=k))
    assert len({canonical_hash(c.to_dict()) for c in cfg})==33
def test_no_astar_base_tree(): assert not (ROOT/'vendor'/'Astar_base').exists()
def test_pair_cache(tmp_path):
    a=get_task_instance(tmp_path,'A',5,10000); b=get_task_instance(tmp_path,'A',5,10000); assert a['task_hash']==b['task_hash']
