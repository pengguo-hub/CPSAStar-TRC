import unittest
from pathlib import Path
from experiments.revision.R2_05_scalability.analyze import statistics, traffic_from_trace, audit_trial

class AnalysisTests(unittest.TestCase):
    def test_seed_uncertainty_and_missing_values(self):
        self.assertEqual(statistics([])['n'],0)
        self.assertIsNone(statistics([2])['ci_low'])
        s=statistics([1,2,3,4,5,None,float('nan')])
        self.assertEqual(s['n'],5);self.assertEqual(s['mean'],3)
        self.assertAlmostEqual(s['std'],1.58113883008419)
        self.assertAlmostEqual(s['ci_low'],1.03675684,places=7)
        self.assertAlmostEqual(s['ci_high'],4.96324316,places=7)

    def test_offline_traffic_boundary_buffer_and_different_agents(self):
        def f(t,aid,target,old=(9,9)):
            return dict(next_time=t,assigned={aid:dict(request=0)},positions={aid:list(old)},next_positions={aid:list(target)})
        trace=[f(1,'a',(2,2)),f(3,'b',(2,2)),f(4,'c',(2,2)),f(5,'c',(3,3)),
               f(6,'c',(3,3)),f(6,'d',(4,4)),f(6,'e',(4,4)),f(6,'z',(5,5),(5,5)),f(9,'a',(2,2))]
        evidence=traffic_from_trace(trace,[(4,4)],2,10)
        # t=1 and 9 are excluded as targets; t=1 is still valid context for t=3.
        # Same-agent revisits, excluded endpoint cells and stationary agents do not count.
        self.assertEqual(len(evidence),4)
        self.assertEqual([e['encounter'] for e in evidence],[True,True,False,False])
        self.assertEqual(evidence[0]['other_arrivals'],[dict(agent='a',time=1),dict(agent='c',time=4)])

    def test_incomplete_not_accepted_as_full_run(self):
        from experiments.revision.R2_05_scalability.common import digest
        w=dict(requests=[]);w['workload_hash']=digest(w)
        row=dict(workload_hash=w['workload_hash'],status='interrupted',eligible=False,partial_throughput=.4)
        self.assertIn('not a complete eligible trial',audit_trial(Path('unused'),w,row))

if __name__=='__main__':unittest.main()
