import contextlib,io,itertools,unittest,ast
import numpy as np
import pandas as pd
from experiments.revision.R2_07_factorial_ablation.CPS_A_lifelong.path_planner_lifelong import LifelongPlanner
from experiments.revision.R2_07_factorial_ablation.CPS_A_lifelong.Conflict_Field_Updater import ConflictFieldUpdater
from experiments.revision.R2_07_factorial_ablation.CPS_A_lifelong.Ticket_Manager import TicketManager
from experiments.revision.R2_07_factorial_ablation.CPS_A_lifelong.Segment_Planner import SegmentPlanner
from experiments.revision.R2_07_factorial_ablation.workload import grid_for, build_workload, case, plan_cases, variants, BASELINE, ROOT
from experiments.revision.R2_07_factorial_ablation.observations import Recorder
from experiments.revision.R2_07_factorial_ablation.analysis import paired, holm, definitions, seed_contrasts

class Checks(unittest.TestCase):
 def fixture(self):
  return dict(case=case('manual','STANDARD',1,4,backlog=1),seed=1,initial_positions={'agv_0':[0,0]},requests=[dict(id=0,release=0,pickup=[1,0],dropoff=[2,0])],width=16,height=11,free_cells=100,workload_hash='manual')
 def test_initial_backlog_two_phase(self):
  w=self.fixture();rec=Recorder(w);p=LifelongPlanner(grid_for('STANDARD'),{'agv_0':{'speed':1.}},{'agv_0':(0,0)},rec.initial_queue(),experiment=rec)
  self.assertEqual(len(p.task_queue),1)
  with contextlib.redirect_stdout(io.StringIO()):p.run_lifelong(4)
  result=rec.results(p);r=result['requests'][0]
  self.assertEqual(r['second_phase_count'],1);self.assertEqual(r['flow_time'],2);self.assertEqual(r['waiting_time'],0)
  self.assertEqual(result['row']['status'],'incomplete')
 def test_requeue_preserves_request_identity(self):
  w=self.fixture();rec=Recorder(w);p=LifelongPlanner(grid_for('STANDARD'),{'agv_0':{'speed':1.}},{'agv_0':(0,0)},rec.initial_queue(),experiment=rec)
  real=p.segment_planner.plan_agv;calls=[0]
  def once(*a,**k):
   calls[0]+=1;return (None,None) if calls[0]==1 else real(*a,**k)
  p.segment_planner.plan_agv=once
  with contextlib.redirect_stdout(io.StringIO()):p.run_lifelong(4)
  r=rec.results(p)['requests'][0]
  self.assertEqual((r['requeues'],r['assignments'],r['release']),(1,2,0));self.assertEqual((r['flow_time'],r['waiting_time']),(3,1))
 def test_P0_retains_R1_blocker_rollback_and_retry(self):
  for priority in [False,True]:
   p=LifelongPlanner(grid_for('STANDARD'),{'a':{'speed':1.},'b':{'speed':1.}}, {'a':(0,0),'b':(2,0)},[],use_priority_replan=True,use_priority=priority)
   p.agv_tasks={a:dict(start=start,waypoints=[start,(1,0)],path=[start,(1,0)] if a=='a' else [],times=[0,1] if a=='a' else [],status='planned' if a=='a' else 'pending',last_plan_time=0) for a,start in [('a',(0,0)),('b',(2,0))]}
   p.pending_agv_paths={'a':([(0,0),(1,0)],[0,1])};p.planned_count=1;p.conflict_updater.pending_paths=[([(0,0),(1,0)],[0,1],'a')]
   priorities={'a':1.,'b':1.};queue=[];p._handle_failure_with_replan('b',1.,queue,priorities)
   self.assertEqual(queue,['b','a']);self.assertEqual(p.agv_tasks['a']['path'],[]);self.assertEqual(bool(priorities['b']!=1.),priority)
   self.assertEqual(p.MAX_REPLAN_PER_AGV,5);self.assertEqual(p.replan_attempts['b'],1)
 def test_P_changes_scoring_R_changes_failure_branch(self):
  for P,R in itertools.product([False,True],repeat=2):
   p=LifelongPlanner(grid_for('STANDARD'),{'a':{'speed':1.},'b':{'speed':1.}},{'a':(0,0),'b':(2,0)},[((1,0),(3,0)),((2,0),(3,0))],use_priority=P,use_priority_replan=R)
   p._assign_new_tasks();p.current_time=10;p.USE_CON=True;p.conflict_updater.smoothed_dict={(0,0,3):2.}
   seen=[];failure=[]
   def fail(**kwargs):seen.append(kwargs['priority']);return None,None
   p.segment_planner.plan_agv=fail;p._handle_failure_direct=lambda aid:failure.append('direct');p._handle_failure_with_replan=lambda *args:failure.append('rollback')
   p._plan_one_batch();self.assertEqual(failure,['rollback' if R else 'direct']*2);self.assertEqual(sorted(seen),[2.,3.] if P else [1.,1.])
 def test_S_raw_counts_and_original_gaussian(self):
  fs=[ConflictFieldUpdater(grid_for('STANDARD'),TicketManager(),smoothing=s) for s in [False,True]]
  for f in fs:f.accumulate_path([(0,0)]*3,[0,1,2],'a');f.batch_update_from_paths();f.finalize_batch_update()
  self.assertEqual(fs[0].path_conflict_dict,fs[1].path_conflict_dict);self.assertEqual(fs[0].smoothed_dict,{(0,0,0):3})
  self.assertAlmostEqual(fs[1].smoothed_dict[(0,0,0)],3/sum(fs[1].gaussian_kernel.values()));self.assertGreater(fs[1].smoothed_dict[(1,0,0)],0)
 def test_L_literal_formula_and_Manhattan_base(self):
  f=ConflictFieldUpdater(grid_for('STANDARD'),TicketManager());s=SegmentPlanner(f.grid,f.ticket_manager,f)
  s.congestion_dict={(x,y,t):2. for x in range(16) for y in range(11) for t in range(1,7)}
  self.assertEqual(s._heuristic((0,0),(4,0),0,1),4);s.use_lookahead=True
  self.assertAlmostEqual(s._heuristic((0,0),(4,0),0,1),104);self.assertEqual(s._heuristic((0,0),(0,0),0,1),0)
  s.congestion_dict={(0,0,7):1000.};self.assertEqual(s._heuristic((0,0),(4,0),0,1),4)
 def test_workload_original_input_bodies_and_matching(self):
  for filename in ['custom_benchmark_loader.py','task_generator.py']:
   def body(path):
    t=ast.parse(path.read_text(encoding='utf-8'));t.body=[n for n in t.body if not isinstance(n,(ast.Import,ast.ImportFrom))];return ast.dump(t,include_attributes=False)
   self.assertEqual(body(ROOT/'original/Lifelong_inputs'/filename),body(ROOT/'reference_inputs'/filename))
  for c in plan_cases():
   w=build_workload(c,39);self.assertEqual(w,build_workload(c,39));self.assertEqual(len(w['requests']),3000)
   self.assertEqual(set(r['release'] for r in w['requests']),{0});self.assertEqual(c['horizon'],500)
   self.assertNotEqual(w['workload_hash'],build_workload(c,40)['workload_hash'])
  self.assertEqual(len(variants())*len(plan_cases())*30,1440)
 def test_factorial_estimands_and_independent_seed_unit(self):
  vv=variants();plan={'variants':vv,'seeds':[1,2]};rows=[]
  for seed in [1,2]:
   for v in vv:rows.append(dict(variant=v['name'],seed=seed,workload_hash=str(seed),eligible=True,y=seed+2*v['S']+3*v['L']+4*v['P']+5*v['R']+6*v['P']*v['R']+8*v['S']*v['L']))
  df=pd.DataFrame(rows);defs={n:w for n,_,w in definitions(vv)}
  for contrast,value in [('S_on-minus-off',6),('P_on-minus-off',7),('PxR',6),('SxL',8),('P_on-minus-off_at_R0',4),('P_on-minus-off_at_R1',10)]:
   self.assertEqual([x['difference'] for x in seed_contrasts(df,plan,'y',defs[contrast])],[value,value])
  df.loc[(df.seed==1)&(df.variant==BASELINE),'eligible']=False
  self.assertEqual(sum(x['eligible'] for x in seed_contrasts(df,plan,'y',defs['P_on-minus-off'])),1)
 def test_unmatched_workload_not_paired(self):
  df=pd.DataFrame([dict(variant=v['name'],seed=1,workload_hash=v['name'],eligible=True,y=1.) for v in variants()])
  self.assertFalse(seed_contrasts(df,{'seeds':[1]},'y',definitions(variants())[0][2])[0]['eligible'])
 def test_smoke_cannot_create_formal_response(self):
  from experiments.revision.R2_07_factorial_ablation.make_response import require_formal
  with self.assertRaises(AssertionError):require_formal({'smoke':True},{'eligible_trials':16})
 def test_small_sample_and_multiple_testing(self):
  self.assertEqual(paired([0,0,0],'zero',100)['p_value'],1)
  self.assertTrue(np.isnan(paired([1],'one',100)['ci95_low']));self.assertTrue(np.isnan(paired([1],'one',100)['p_value']))
  self.assertAlmostEqual(paired([1]*5,'signs',100)['p_value'],.0625);self.assertAlmostEqual(holm([.01,.04,np.nan],3)[0],.03)

if __name__=='__main__':unittest.main()
