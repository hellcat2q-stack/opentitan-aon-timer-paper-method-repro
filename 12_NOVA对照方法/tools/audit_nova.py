#!/usr/bin/env python3
"""Audit selection replay, identities, raw logs, counts, union and time totals."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
from nova_common import load_inputs, module, read, sha, verify_sources, write


def audit(run):
    run = Path(run)
    inputs = load_inputs()
    selector = inputs['selector']
    p, s = read(run/'protocol.json'), read(run/'summary.json')
    verify_sources(p['source_sha256'])
    config = inputs['config']
    budget = config['smoke_budget' if p['phase']=='smoke' else 'formal_budget']
    assert p['budget']==budget and p['workers']==config['workers']
    assert p['method']==s['method']==config['method'] and p['seed']==config['seed']
    assert p['policy']==config['policy'] and p['steering']=={'enabled':False}
    assert p['simv_sha256']==config['expected_sha256']['simv']
    assert p['initial_csv_sha256']==config['expected_sha256']['initial_csv']
    assert p['mapping_sha256']==config['expected_sha256']['mapping']
    assert p['catalog_sha256']==config['expected_sha256']['catalog']
    assert p['test_catalog_entries']==list(inputs['entries'].values())
    assert p['sequence_pool']==list(inputs['entries'])
    rng=random.Random(config['seed'])
    assert p['seeds']==[rng.randint(1,2**31-1) for _ in range(budget)]
    assert s['policy_sha256']==sha(run/'protocol.json')
    checker=module(inputs['paths']['uvm_checker'],'nova_audit_uvm')
    with (run/'vectors.csv').open(newline='',encoding='utf-8') as f:
        reader=csv.reader(f)
        assert next(reader)==['run_id','accepted',*inputs['names']]
        rows=list(reader)
    results=read(run/'run_results.json')
    assert len(rows)==len(results)==s['completed']
    previous='0'*64
    submits,feedback={},{}
    active=max_active=failures=0
    last_event=None
    total_cpu=0.0
    checked_logs=[]
    first=None
    curves=[]
    for i,line in enumerate((run/'events.jsonl').read_text(encoding='utf-8').splitlines()):
        e=json.loads(line)
        claimed=e.pop('event_hash')
        assert e['event_index']==i and e['previous_hash']==previous and e['policy_hash']==sha(run/'protocol.json')
        previous=hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert previous==claimed
        if e['event']=='submit':
            run_id=e['run_id'];assert run_id==len(submits) and run_id<budget
            assert e['feedback_count']==len(feedback) and failures==0
            if run_id>=p['workers']:
                assert last_event=='feedback', 'Continuous refill must follow feedback'
            assert active<p['workers'] and e['seed']==p['seeds'][run_id]
            arm,decision=selector.choose()
            assert (arm,decision)==(e['test_id'],e['decision']), f'NOVA decision mismatch at {run_id}'
            selector.reserve(arm);active+=1
            max_active=max(active,max_active)
            assert e['active']==active
            submits[run_id]=e
            first=e['timestamp'] if first is None else first
        elif e['event']=='feedback':
            run_id=e['run_id'];order=len(feedback)
            assert run_id in submits and run_id not in feedback
            r=results[order];row=rows[order]
            accepted=e['accepted'];vector=np.asarray(row[2:],dtype=np.uint8)
            assert len(vector)==4507 and np.isin(vector,(0,1)).all()
            assert row[0]==str(run_id) and row[1]==str(accepted)
            assert e['feedback_count']==r['feedback_order']==order+1
            arm=submits[run_id]['test_id']
            assert e['test_id']==r['test_id']==r['test_description']==arm
            assert r['seed']==p['seeds'][run_id] and r['run_id']==run_id
            assert accepted==(r['status']=='success')
            assert hashlib.sha256(bytes(vector)).hexdigest()==e['vector_sha256']
            base=run/'batches'/f'batch_{run_id//10}'/str(run_id)
            execution=read(base/'execution.json')
            entry=inputs['entries'][arm]
            assert execution['test_id']==arm and execution['sequence']==entry['sequence']
            assert execution['test_run_options']==entry['run_options']
            assert execution['worker_start_time']>=submits[run_id]['timestamp']
            assert execution['worker_end_time']<=e['timestamp']
            if accepted:
                raw=base/'raw'/entry['official_test']/'0'
                check=checker.inspect_log((raw/'run.log').read_text(errors='replace'),r['vcs_return_code'])
                assert check['status']=='pass' and r['urg_return_code']==0
                assert r['uvm_error']==r['uvm_fatal']==0 and r['uvm_pass']
                counts=read(base/'coverage_counts.json')
                assert set(counts)==set(inputs['names'])
                assert vector.tolist()==[int(counts[n]>0) for n in inputs['names']]
                assert int(vector.sum())==r['run_covered_bins']
                checked_logs.append(dict(run_id=run_id,log_sha256=sha(raw/'run.log'),**check))
            else:
                assert not vector.any()
                failures+=1
            before=int(selector.union.sum());selector.feedback(arm,vector if accepted else None)
            gain=int(selector.union.sum())-before
            assert e['new_bins']==r['new_bins']==gain
            assert e['accumulated_covered']==r['accumulated_covered']==int(selector.union.sum())
            runtime=r.get('simulator_cpu_seconds')
            assert runtime is not None and math.isfinite(runtime) and runtime>=0
            assert runtime==e['simulator_cpu_seconds']
            total_cpu+=runtime
            active-=1;assert e['active']==active
            feedback[run_id]=e
            curves.append(dict(feedback_order=order+1,run_id=run_id,accepted=accepted,
                               accumulated_simulator_cpu_seconds=total_cpu,wall_seconds=e['timestamp']-first,
                               covered_bins=int(selector.union.sum()),coverage_percent=float(selector.union.mean()*100),new_bins=gain))
        elif e['event']=='finished':
            assert e['submitted']==len(submits) and e['completed']==len(feedback) and e['failed']==failures
        else:
            raise ValueError('Unknown run event')
        last_event=e['event']
    assert last_event=='finished'
    assert active==0 and s['event_chain_head']==previous
    assert s['submitted']==len(submits) and s['completed']==len(feedback)
    assert s['max_active_workers']==max_active and s['failed']==failures and s['retried']==0
    assert s['accepted']==len(feedback)-failures
    assert s['missing_cpu_time_count']==0
    assert math.isclose(total_cpu,s['accumulated_simulator_cpu_seconds_all_attempts'],abs_tol=1e-6)
    assert s['final_covered_bins']==int(selector.union.sum())
    assert math.isclose(s['final_coverage_percent'],float(selector.union.mean()*100),abs_tol=1e-8)
    with (run/'coverage_curve.csv').open(newline='',encoding='utf-8') as f:actual=list(csv.DictReader(f))
    assert len(actual)==len(curves)
    for row,expected in zip(actual,curves):
        for key,value in expected.items():
            if isinstance(value,bool):assert row[key]==str(value)
            else:assert math.isclose(float(row[key]),value,abs_tol=1e-7),key
    assert math.isclose(curves[-1]['wall_seconds'],s['wall_seconds'],abs_tol=1e-7)
    assert len(submits)==len(feedback)==budget and failures==0 and s['status']=='completed'
    write(run/'raw_uvm_audit.json',dict(status='pass',checked_runs=len(checked_logs),cases=checked_logs,raw_logs_exported=False))
    result=dict(status='pass',method=p['method'],budget=budget,completed=budget,failed=0,retried=0,
                initial_covered_bins=508,bin_count=4507,final_covered_bins=int(selector.union.sum()),
                hash_chain_verified=True,all_nova_decisions_replayed=True,all_vectors_match_raw_counts=True,
                official_test_ids_preserved=True,all_seeds_match_protocol=True,all_rewards_match_union_deltas=True,
                all_accepted_runs_have_uvm_pass=True,protocol_sha256=sha(run/'protocol.json'),event_chain_head=previous)
    write(run/'audit.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    print(json.dumps(audit(parser.parse_args().run_dir)),flush=True)
