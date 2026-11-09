import unittest,tempfile
from pathlib import Path
from collections import Counter
import numpy as np
from experiments.revision.R2_05_scalability.common import ROOT, read_json, digest, execution_hash, write_json
from experiments.revision.R2_05_scalability.original_runtime import load_original, build_original_inputs
from experiments.revision.R2_05_scalability.protocol import build_workload, cases, make_loader
from experiments.revision.R2_05_scalability.recorder import Recorder
load_original()
from experiments.revision.R2_05_scalability.integration.path_planner_lifelong import LifelongPlanner
from experiments.revision.R2_05_scalability.vendor.portable_vendor.experiment.Lifelong.benchmark_loader import GridMap

class IntegrationTests(unittest.TestCase):
    def test_exact_baseline_inputs(self):
        for fleet in (10,30,50):
            c=next(x for x in cases() if x['name']=='A_fleet'+str(fleet));w=build_workload(c,39)
            (grid,info,pos,q),_,_=build_original_inputs(fleet,39)
            self.assertEqual(w['grid'],grid.grid.tolist());self.assertEqual(w['initial_positions'],{a:list(v) for a,v in pos.items()})
            self.assertEqual([(tuple(r['pickup']),tuple(r['dropoff'])) for r in w['requests']],list(q))

    def test_late_arrival_and_empty_stream(self):
        for requests in ([],[dict(id=1,release=100,pickup=[1,0],dropoff=[3,0])]):
            with tempfile.TemporaryDirectory() as tmp:
                grid=GridMap(5,1,1);c=dict(name='unit_release',map='unit',fleet=1,tiles=1,mode='poisson',arrival_rate=.25,horizon=500,warmup=0,traffic_coupling=None)
                w=dict(case=c,seed=0,requests=requests,initial_positions={'agv_0':[0,0]},width=5,height=1)
                obs=Recorder(w,Path(tmp));p=LifelongPlanner(grid,{'agv_0':{'speed':1.}},{'agv_0':(0,0)},[],True,experiment=obs)
                p.run_lifelong(max_time=500);r=obs.results(p,'completed')
                self.assertTrue(r['eligible']);self.assertEqual(p.current_time,500)
                self.assertEqual(r['completed'],len(requests))
                if requests:self.assertEqual(obs.ledger[1]['completion'],103);self.assertEqual(r['flow_time'],3)
                else:self.assertIsNone(r['completion_fraction'])

    def test_original_zero_distance_failure_keeps_same_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            grid=GridMap(5,1,1);c=dict(name='unit_zero',map='unit',fleet=1,tiles=1,mode='poisson',arrival_rate=.25,horizon=500,warmup=0,traffic_coupling=None)
            w=dict(case=c,seed=0,requests=[dict(id=3,release=0,pickup=[0,0],dropoff=[3,0])],initial_positions={'agv_0':[0,0]},width=5,height=1)
            obs=Recorder(w,Path(tmp));p=LifelongPlanner(grid,{'agv_0':{'speed':1.}},{'agv_0':(0,0)},[],True,experiment=obs)
            p.run_lifelong(max_time=500);r=obs.results(p,'completed')
            self.assertTrue(r['eligible']);self.assertEqual(r['completed'],0);self.assertGreater(r['requeues'],0)
            self.assertEqual(obs.ledger[3]['queue_wait']+obs.ledger[3]['assigned_wait'],500)

    def test_tiles_use_actual_arrays_and_stations(self):
        g0=make_loader('STANDARD').load_map().grid
        for k,n in [(1,30),(2,120),(3,270)]:
            l=make_loader('STANDARD',k);g=l.load_map()
            self.assertTrue(np.array_equal(g.grid,np.tile(g0,(k,k))))
            p=l.load_initial_positions(g,n,seed=901)
            self.assertEqual(len(p),n);self.assertTrue(all(g.grid[y,x]==0 for x,y in p.values()))
            self.assertEqual(sum(len(v) for v in l.outbound_map.values()),5*k*k)

    def test_traffic_couplings_release_marginals(self):
        group=[build_workload(c,901) for c in cases() if c['traffic_coupling']]
        for key in ('release_hash','pickup_hash','initial_positions_hash','map_hash'):
            self.assertEqual(len({w[key] for w in group}),1)
        self.assertTrue(all(Counter(tuple(r['dropoff']) for r in w['requests'])==Counter(tuple(r['dropoff']) for r in group[0]['requests']) for w in group))
        self.assertTrue(all([r['intrinsic_distance'] for r in w['requests']]==[r['intrinsic_distance'] for r in group[0]['requests']] for w in group))
        self.assertEqual(len(cases()),14)

    def test_saved_native_parity(self):
        a=read_json(ROOT/'validation/native_baseline/N30_s39/final_native_state.json')
        b=read_json(ROOT/'validation/integration_parity_final/N30_s39/final_native_state.json')
        self.assertEqual(a,b)

if __name__=='__main__':unittest.main()
