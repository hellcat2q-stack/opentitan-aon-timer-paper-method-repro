"""Behavioral verification; synthetic vectors never count as VCS evidence."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

import numpy as np
TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from nova_policy import NovaSelector, Parameters
from nova_common import load_inputs
from run_nova_vcs import run_scheduler
from nova_common import source_manifest, write
from audit_nova import audit


class PolicyTests(unittest.TestCase):
    def test_nearest_neighbor_sum_and_top_fraction(self):
        # Distances to [000]: 0, 1, sqrt(2), sqrt(3); top 50% is
        # evaluated per category. Two ensemble members sum, not average.
        h=[('a',[0,0,0]),('a',[1,0,0]),('b',[1,1,0]),('b',[1,1,1])]
        p=NovaSelector(['a','b'],{'g':[0,1,2]},h,parameters=Parameters(top_fraction=.5))
        scores=p.novelty_scores('g',[[0],[0]])
        self.assertAlmostEqual(scores['a'],2)
        self.assertAlmostEqual(scores['b'],2*np.sqrt(3))

    def test_score_uses_only_target_cluster(self):
        p=NovaSelector(['a','b'],{'g':[0],'other':[1,2]},[('a',[0,0,0]),('b',[0,1,1])])
        self.assertEqual(p.novelty_scores('g',[[0]]),{'a':0.0,'b':0.0})

    def test_largest_uncovered_space_includes_never_hit_bins(self):
        p=NovaSelector(['a'],{'large':[0,1,2],'small':[3]},[('a',[1,0,0,0])])
        self.assertEqual(p.target_cluster(),'large')

    def test_bin_balancing_rare_bin_is_always_represented(self):
        h=[('a',[1,0]) for _ in range(100)]+[('a',[0,1])]
        p=NovaSelector(['a'],{'g':[0,1]},h,parameters=Parameters(ensemble_size=20,sample_size=2))
        ensemble,fallback=p.sample_ensemble('g')
        self.assertEqual(fallback,0)
        self.assertTrue(all(100 in s and len(s)==2 for s in ensemble))

    def test_empty_ensemble_fallback_is_recorded(self):
        p=NovaSelector(['a'],{'g':[0,1]},[('a',[0,0])],parameters=Parameters(ensemble_size=3))
        sets,fallback=p.sample_ensemble('g')
        self.assertEqual((sets,fallback),([[0],[0],[0]],3))

    def test_cold_start_reserves_distinct_shared_class_arms(self):
        arms=['a','intr','csr','reset']
        p=NovaSelector(arms,{'g':[0,1]},[('a',[1,0])])
        seen=[]
        for _ in range(3):
            arm,decision=p.choose();p.reserve(arm);seen.append(arm)
            self.assertEqual(decision['rule'],'cold_start_empty_history')
        self.assertEqual(set(seen),set(arms[1:]))
        p.feedback(seen[0],None)
        self.assertEqual(len(p.by_arm[seen[0]]),0)
        self.assertEqual(p.active[seen[0]],0)

    def test_reproducible_seeded_ties_and_feedback_changes_history(self):
        def decisions():
            p=NovaSelector(['a','b'],{'g':[0,1]},[('a',[1,0]),('b',[1,0])],seed=42)
            chosen=[]
            for _ in range(6):
                arm,d=p.choose();p.reserve(arm);p.feedback(arm,[1,0]);chosen.append((arm,d))
            self.assertEqual(len(p.vectors),8)
            return chosen
        self.assertEqual(decisions(),decisions())

    def test_invalid_partition_and_binary_values_are_rejected(self):
        for clusters in ({'a':[0,0]},{'a':[1]},{'a':[]}):
            with self.assertRaises(ValueError):NovaSelector(['a'],clusters,[('a',[0])])
        with self.assertRaises(ValueError):NovaSelector(['a'],{'g':[0]},[('a',[2])])
        for kwargs in ({'top_fraction':0},{'sample_size':0},{'ensemble_size':1.5}):
            with self.assertRaises(ValueError):Parameters(**kwargs)

    def test_closed_coverage_does_not_spend_budget_on_empty_categories(self):
        p=NovaSelector(['a','b'],{'g':[0]},[('a',[1])])
        arm,decision=p.choose()
        self.assertIsNone(arm)
        self.assertEqual(decision['rule'],'coverage_closed')

    def test_existing_input_hashes_and_13_cold_start_categories(self):
        inputs=load_inputs()
        self.assertEqual((len(inputs['names']),len(inputs['history']),int(inputs['selector'].union.sum())),(4507,39,508))
        missing=[arm for arm,rows in inputs['selector'].by_arm.items() if not rows]
        self.assertEqual(len(missing),13)
        self.assertEqual(len(inputs['clusters']),751)


class SchedulerTests(unittest.TestCase):
    def inputs(self):
        arms={'a':{},'b':{},'c':{}}
        config={'method':'NOVASelectionVCS','seed':42,'workers':2,'logical_batch_size':10,
                'smoke_budget':6,'formal_budget':8,'policy':{'ensemble_size':2},'solver_optimization':{'enabled':False},
                'expected_sha256':{k:'0'*64 for k in ['initial_csv','conversion_source','simv','mapping','catalog']}}
        selector=NovaSelector(arms,{'g':[0,1,2]},[('a',[1,0,0])],parameters=Parameters(ensemble_size=2))
        return {'entries':arms,'config':config,'selector':selector,'names':['x','y','z']}

    def test_scheduler_budget_seeds_and_continuous_refill(self):
        captured=[]
        def backend(run,run_id,arm,seed):
            captured.append((run_id,arm,seed));time.sleep(.001)
            return dict(run_id=run_id,test_id=arm,seed=seed,status='success',simulator_cpu_seconds=1.25),[1,0,0]
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            summary=run_scheduler(self.inputs(),run,'smoke',backend,{})
            self.assertEqual((summary['completed'],summary['submitted'],summary['failed'],summary['retried']),(6,6,0,0))
            self.assertEqual(summary['accumulated_simulator_cpu_seconds_all_attempts'],7.5)
            self.assertEqual(summary['max_active_workers'],2)
            events=[json.loads(x) for x in (run/'events.jsonl').read_text().splitlines()]
            submits=[x for x in events if x['event']=='submit']
            self.assertEqual([e['run_id'] for e in submits],list(range(6)))
            self.assertTrue(all(e['feedback_count']>0 for e in submits[2:]))
            protocol=json.loads((run/'protocol.json').read_text())
            self.assertEqual([e['seed'] for e in submits],protocol['seeds'])
            self.assertEqual({arm for _,arm,_ in captured[:2]},{'b','c'})

    def test_failure_stops_replenishment_counts_attempt_and_preserves_outputs(self):
        def backend(run,run_id,arm,seed):
            time.sleep(.001 if run_id==0 else .04)
            success=run_id!=0
            return dict(run_id=run_id,test_id=arm,seed=seed,status='success' if success else 'failed',simulator_cpu_seconds=.5),[1,0,0] if success else None
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory);inputs=self.inputs()
            summary=run_scheduler(inputs,run,'smoke',backend,{})
            self.assertEqual(summary['status'],'stopped_for_diagnosis')
            self.assertEqual((summary['submitted'],summary['completed'],summary['failed'],summary['retried']),(2,2,1,0))
            self.assertEqual(len(inputs['selector'].vectors),2) # initial plus only the success
            self.assertTrue((run/'vectors.csv').exists() and (run/'run_results.json').exists())

    def test_smoke_audit_replays_decisions_and_rejects_tampering(self):
        # Synthetic execution writes only into TemporaryDirectory. It tests the
        # exact scheduler/auditor, not simulator correctness or coverage gains.
        inputs=load_inputs()
        names=inputs['names']; entries=inputs['entries']
        vector=inputs['history'][0][1].tolist()
        def backend(run,run_id,arm,seed):
            entry=entries[arm];start=time.time()
            base=run/'batches'/f'batch_{run_id//10}'/str(run_id)
            raw=base/'raw'/entry['official_test']/'0';raw.mkdir(parents=True)
            (raw/'run.log').write_text('Time: 10 ps\n--- UVM Report Summary ---\nUVM_ERROR : 0\nUVM_FATAL : 0\nTEST PASSED CHECKS\n')
            write(base/'coverage_counts.json',dict(zip(names,vector)))
            result=dict(run_id=run_id,test_id=arm,test_description=arm,seed=seed,status='success',
                        sequence=entry['sequence'],test_run_options=entry['run_options'],
                        vcs_return_code=0,urg_return_code=0,uvm_error=0,uvm_fatal=0,uvm_pass=True,
                        run_covered_bins=sum(vector),simulator_cpu_seconds=1.0,
                        worker_start_time=start,worker_end_time=time.time())
            write(base/'execution.json',result)
            return result,vector
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            summary=run_scheduler(inputs,run,'smoke',backend,source_manifest(inputs))
            self.assertEqual(summary['completed'],30)
            self.assertEqual(audit(run)['status'],'pass')
            results=json.loads((run/'run_results.json').read_text())
            results[0]['seed']+=1
            write(run/'run_results.json',results)
            with self.assertRaises(AssertionError):audit(run)


if __name__=='__main__':unittest.main()
