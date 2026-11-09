import unittest,tempfile
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
import json
import torch
import compat
from config import Config,REPRESENTATIONS,PRIMARY_REPRESENTATIONS,MAPS,KERNEL_FAMILY,SOURCE_FAMILY
from field_strategies import kernel_diagnostics,make_field
from reference_fields import gaussian_smooth_dense
from learned_prediction import LearnedOccupancyPredictor
from instances import get_instance,generate_tasks,canonical_hash,write_json
from run_representation_experiment import trial
from evaluation import exposure_values,validate_paths
from vendor.CPS_A.path_planner import GridMap
from vendor.CPS_A.Ticket_Manager import TicketManager
from vendor.CPS_A.Segment_Planner import SegmentPlanner
from controlled_search import Budget,ControlledSegmentPlanner
from statistics_analysis import paired_result,holm,analyze

class ProtocolTests(unittest.TestCase):
 def test_invalid_config(self):
  for d in [dict(L=1.2),dict(gamma=float('nan')),dict(alpha=0),dict(omega=-1),dict(delta=2),dict(timeout=0),dict(update_interval=True)]:
   with self.assertRaises(ValueError):replace(Config(),**d).validate()
 def test_kernel_matching(self):
  for config in [Config(),replace(Config(),L=2,T=2),replace(Config(),L=0,T=0)]:
   k=kernel_diagnostics(config)['kernels'];g=k['gaussian']
   for name in ['exponential','linear']:
    for metric in ['spatial_second_moment','temporal_second_moment']:self.assertAlmostEqual(k[name][metric],g[metric],12)
  k=kernel_diagnostics(Config())['kernels'];self.assertGreater(k['uniform']['l1_from_gaussian'],0);self.assertGreater(k['linear']['l1_from_gaussian'],0)
 def test_uniform_boundary_oracle(self):
  grid=GridMap(4,4);tickets=TicketManager();field=make_field('uniform',grid,tickets,Config());seg=SegmentPlanner(grid,tickets,field)
  self.assertTrue(seg._reserve_tickets('a',[(0,0)],[0],1))
  field.accumulate_path([(0,0)],[0],'a');field.batch_update_from_paths()
  self.assertAlmostEqual(field.smoothed_dict[(0,0,0)],1/27)
  self.assertAlmostEqual(field.smoothed_dict.get((1,1,1),0),1/27)
 def test_omega(self):
  grid=GridMap(4,4);t=TicketManager();f=make_field('gaussian',grid,t,Config())
  values=[]
  for w in [0,25,50]:
   s=ControlledSegmentPlanner(grid,t,f,replace(Config(),omega=w),Budget(10),use_lookahead_congestion=True);s.congestion_dict={(x,y,k):.2 for x in range(4) for y in range(4) for k in range(4)}
   values.append(s._heuristic((1,1),(3,3),0,.5))
  self.assertAlmostEqual(values[1]-values[0],(values[2]-values[0])/2)
 def test_deterministic_tasks(self):self.assertEqual(generate_tasks('A',5,101,'X'),generate_tasks('A',5,101,'X'))
 def _reference_dir(self, root, config, load=3):
  root=Path(root); root.mkdir(parents=True,exist_ok=True)
  arr=np.zeros((config.reference_horizon+1,11,16),dtype=np.float32);arr[1,1,1]=1.0
  np.savez_compressed(root/f"historical_A_{load}.npz",raw_expected_occupancy=arr)
  write_json(root/f"historical_A_{load}.json",dict(map="A",load=load,calibration_seeds=[10000],
      generator="collision_only_controlled_planner",reference_horizon=config.reference_horizon))
  model=LearnedOccupancyPredictor(11,16,hidden=24)
  torch.save(dict(state_dict=model.state_dict(),metadata=dict(map="A",height=11,width=16,hidden=24,
      calibration_seeds=[10000],label_generator="collision_only_controlled_planner"),history=[]),root/"learned_A.pt")
  return root
 def test_cache_and_pairing(self):
  with tempfile.TemporaryDirectory() as d:
   c=replace(Config(),reference_horizon=16)
   refs=self._reference_dir(Path(d)/"refs",c,3)
   a=get_instance(Path(d)/"inst",'A',73005,3,c);b=get_instance(Path(d)/"inst",'A',73005,3,replace(c,gamma=2,omega=0))
   self.assertEqual(a,b)
   hashes=[];signatures=[]
   for rep in PRIMARY_REPRESENTATIONS:
    r=trial(a,3,rep,'off',c,reference_dir=refs);hashes.append(r['row']['task_hash']);signatures.append(r['row']['common_planner_signature']);self.assertEqual(len(r['task_rows']),3)
    self.assertEqual(r['validation']['node_conflicts'],0)
   self.assertEqual(len(set(hashes)),1);self.assertEqual(len(set(signatures)),1)
   f=Path(d)/'inst'/ 'A_seed_73005.json';a['tasks'][0]['agv_id']='altered';write_json(f,a)
   with self.assertRaises(ValueError):get_instance(Path(d)/"inst",'A',73005,3,c)
 def test_two_orthogonal_families(self):
  self.assertEqual(SOURCE_FAMILY,("gaussian","historical_gaussian","learned_gaussian"))
  self.assertEqual(KERNEL_FAMILY,("raw","gaussian","exponential","linear","uniform"))
  self.assertEqual(set(SOURCE_FAMILY)&set(KERNEL_FAMILY),{"gaussian"})
 def test_external_gaussian_uses_same_kernel(self):
  c=replace(Config(),reference_horizon=8)
  raw=np.zeros((9,5,5),dtype=np.float32);raw[4,2,2]=1
  dense=gaussian_smooth_dense(raw,c)
  # Center is kernel center divided by the same full 3D normalizer used by CPS-A.
  k=kernel_diagnostics(c)['kernels']['gaussian']['normalized_weights']
  center=next(x['weight'] for x in k if x['dx']==0 and x['dy']==0 and x['dt']==0)
  self.assertAlmostEqual(float(dense[4,2,2]),float(center),6)
 def test_timeout(self):
  with tempfile.TemporaryDirectory() as d:
   a=get_instance(d,'A',73005,3,Config());r=trial(a,3,'gaussian','off',replace(Config(),timeout=1e-9))
   self.assertEqual(r['row']['timed_out'],1)
 def test_neutral_hand_calculation(self):
  self.assertAlmostEqual(exposure_values([(1,1)],[1],{(1,1,1):1,(2,1,2):1},1,1)[0],2/15)
 def test_invalid_paths(self):
  for bad in [
    {'a':dict(path=[(0,0),(1,0)],times=[0,1]),'b':dict(path=[(1,0),(0,0)],times=[0,1])},
    {'a':dict(path=[(0,0)],times=[0]),'b':dict(path=[(0,0)],times=[0])},
    {'a':dict(path=[(0,1),(1,1)],times=[0,2])}
  ]:
   with self.assertRaises(AssertionError):validate_paths(GridMap(2,2),bad)
 def test_effect_intervals(self):
  for d in [[0,0,0],[1,1,1],[1],[1,2,3]]:
   r=paired_result(d,np.random.default_rng(1),100)
   self.assertEqual(r['n_pairs'],len(d));self.assertIn('rank_biserial_ci95_low',r)
  self.assertTrue(np.isnan(paired_result([1,1,1],np.random.default_rng(1),100)['cohen_dz']))
 def test_missing_family(self):
  self.assertAlmostEqual(holm([.01],5)[0],.05)
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'raw_results.csv';rows=[]
   for seed in [1,2]:
    for rep in ['gaussian','raw']:rows.append(dict(protocol='direct',map='A',task_count=5,representation=rep,rollback_mode='off',seed=seed,success_rate=.5,planning_time=1,timed_out=0))
   pd.DataFrame(rows).to_csv(f,index=False)
   write_json(Path(d)/'run_manifest.json',dict(plan=dict(seeds=[1,2,3],maps=['A','B'],loads={'A':[5],'B':[5]},representations=['gaussian','raw','exponential'])))
   summary,pairs=analyze(f,100,1);self.assertTrue((summary.n_expected==3).all());self.assertTrue((pairs.predeclared_family_size==4).all())
 def test_r1_aligned_protocol(self):
  self.assertEqual(MAPS["A"]["loads"],[50,70]);self.assertEqual(MAPS["B"]["loads"],[250,280]);self.assertEqual(MAPS["C"]["loads"],[150,200])
  for m in "ABC":
   inst=get_instance(tempfile.mkdtemp(),m,42,max(MAPS[m]["loads"]),Config())
   self.assertEqual(len(inst["tasks"]),max(MAPS[m]["loads"]))
   self.assertTrue(set(inst)=={'map','seed','task_seed','tasks','task_pool_hash','task_order_rule','protocol_note','instance_config_hash'})
 def test_map_specific_heuristic(self):
  grid=GridMap(4,4); tickets=TicketManager(); field=make_field("gaussian",grid,tickets,Config())
  for use in [False,True]:
   s=ControlledSegmentPlanner(grid,tickets,field,Config(),Budget(10),use_lookahead_congestion=use)
   s.congestion_dict={(x,y,t):0.2 for x in range(4) for y in range(4) for t in range(5)}
   h=s._heuristic((1,1),(3,3),0,1.0)
   if use:self.assertGreater(h,4.0)
   else:self.assertEqual(h,4.0)
 def test_fixed_turn_penalty_matches_original_source(self):
  self.assertFalse(hasattr(Config(), "beta"))
  grid=GridMap(4,4); tickets=TicketManager(); field=make_field("gaussian",grid,tickets,Config())
  s=ControlledSegmentPlanner(grid,tickets,field,Config(),Budget(10),use_lookahead_congestion=False)
  s.enable_turn_penalty=True
  self.assertEqual(s._calculate_turn_penalty((1,1),(1,2),(1,0)),0.5)
  self.assertEqual(s._calculate_turn_penalty((1,1),(2,1),(1,0)),0.0)

if __name__=='__main__':unittest.main()
