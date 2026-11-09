#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path
from config import Config, MAPS, KERNEL_FAMILY, SOURCE_FAMILY
from instances import get_instance
from controlled_search import Budget, ControlledSegmentPlanner
from field_strategies import make_field
from vendor.CPS_A.path_planner import GridMap
from vendor.CPS_A.Ticket_Manager import TicketManager

passed_items=[]
def passed(name):
    passed_items.append(name)


def main():
    c=Config().validate()
    assert not hasattr(c,'beta')
    passed('fixed_turn_penalty_not_parameterized')
    assert MAPS['A']['loads']==[50,70]
    assert MAPS['B']['loads']==[250,280]
    assert MAPS['C']['loads']==[150,200]
    passed('r1_aligned_loads')
    run_text=Path('run_representation_experiment.py').read_text(encoding='utf-8')
    prep_text=Path('prepare_reference_artifacts.py').read_text(encoding='utf-8')
    assert '(1 if a.smoke else 5)' in run_text
    assert 'FORMAL_TEST_SEEDS' not in prep_text
    passed('five_formal_runs_and_runtime_seed_disjointness')
    assert SOURCE_FAMILY == ('gaussian','historical_gaussian','learned_gaussian')
    assert KERNEL_FAMILY == ('raw','gaussian','exponential','linear','uniform')
    assert set(SOURCE_FAMILY) & set(KERNEL_FAMILY) == {'gaussian'}
    passed('orthogonal_information_source_and_kernel_families')
    with tempfile.TemporaryDirectory() as d:
        for m in 'ABC':
            inst=get_instance(d,m,42,max(MAPS[m]['loads']),c)
            assert len(inst['tasks'])==max(MAPS[m]['loads'])
            assert set(inst)=={'map','seed','task_seed','tasks','task_pool_hash','task_order_rule','protocol_note','instance_config_hash'}
    passed('direct_instances_have_no_preexisting_schedule_fields')
    grid=GridMap(4,4);tickets=TicketManager();field=make_field('gaussian',grid,tickets,c)
    for m in 'ABC':
        s=ControlledSegmentPlanner(grid,tickets,field,c,Budget(10),use_lookahead_congestion=(m=='A'))
        s.congestion_dict={(x,y,t):0.2 for x in range(4) for y in range(4) for t in range(5)}
        h=s._heuristic((1,1),(3,3),0,1.0)
        assert (h>4.0) if m=='A' else (h==4.0)
    passed('map_specific_heuristic')
    Path('validation').mkdir(exist_ok=True)
    Path('validation/regression_report.json').write_text(json.dumps({'passed':passed_items},indent=2))
    print(f'{len(passed_items)} regression checks passed')

if __name__=='__main__':main()
