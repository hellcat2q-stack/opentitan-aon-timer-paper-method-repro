#!/usr/bin/env python3
"""Real VCS/URG execution for NOVASelectionVCS; no UCB or replay backend."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
from nova_common import PACKAGE, REPO, load_inputs, module, read, sha, source_manifest, verify_backend, write


class VCSBackend:
    def __init__(self, inputs, server_root):
        self.inputs = inputs
        self.paths = verify_backend(inputs, server_root)
        self.corpus = module(inputs['paths']['corpus_source'], 'nova_corpus')
        self.converter = module(inputs['paths']['conversion_source'], 'nova_converter')
        schema = module(inputs['paths']['stable_schema'], 'nova_schema')
        self.checker = module(inputs['paths']['uvm_checker'], 'nova_uvm_checker')
        self.schema = schema.StableCoverageSchema(self.converter, self.paths['canonical_report'], inputs['names'])

    def __call__(self, run, run_id, arm, seed):
        entry = self.inputs['entries'][arm]
        base = run / 'batches' / f'batch_{run_id // 10}' / str(run_id)
        base.mkdir(parents=True, exist_ok=False)
        job = dict(result_root=str(base / 'raw'), test_name=entry['official_test'], index=0,
                   global_run_id=run_id, seed=seed, sequence=entry['sequence'],
                   simv=str(self.paths['simv']), dv_root=str(self.paths['dv_root']),
                   test_run_options=entry['run_options'], timeout_seconds=entry['timeout_seconds'], extra_plusargs=[])
        result = dict(run_id=run_id, test_id=arm, test_description=arm, official_test=entry['official_test'],
                      test_name=entry['official_test'], sequence=entry['sequence'], seed=seed, status='failed',
                      test_run_options=entry['run_options'], worker_start_time=time.time())
        counts = None
        try:
            execution = self.corpus.run_one(job)
            result.update(execution)
            raw = base / 'raw' / entry['official_test'] / '0'
            check = self.checker.inspect_log((raw / 'run.log').read_text(errors='replace'), execution['vcs_return_code'])
            result['strict_uvm_check'] = check
            if check['status'] != 'pass' or execution['urg_return_code'] != 0:
                raise RuntimeError('Strict UVM or URG check failed')
            cpu = execution['simulator_cpu_seconds']
            if cpu is None or not math.isfinite(cpu) or cpu < 0:
                raise ValueError('Missing/nonfinite simulator CPU time')
            report, _, _ = self.converter.run_urg(dict(source_root=str(base / 'raw'),
                    relative_run_dir=str(raw.relative_to(base / 'raw')), source='online', global_run_id=run_id),
                    base / 'reports', 'urg', 300)
            counts = self.schema.parse(report, raw / 'coverage/default.vdb')
            if set(counts) != set(self.inputs['names']) or any(v < 0 for v in counts.values()):
                raise ValueError('Coverage identity/count mismatch')
            write(base / 'coverage_counts.json', counts)
            result.update(status='success', parsed_bin_count=len(counts), run_covered_bins=sum(v > 0 for v in counts.values()))
        except Exception as exc:
            # This diagnostic and raw files stay on the server. It is never
            # transformed into a successful zero-gain observation.
            result['error'] = f'{type(exc).__name__}: {exc}'
        result['worker_end_time'] = time.time()
        result['worker_wall_seconds'] = result['worker_end_time'] - result['worker_start_time']
        write(base / 'execution.json', result)
        vector = [int(counts[n] > 0) for n in self.inputs['names']] if result['status'] == 'success' else None
        return result, vector


def run_scheduler(inputs, run, phase, backend, manifest):
    """Count all attempts; stop submissions on failure and drain active jobs."""
    config, selector, names = inputs['config'], inputs['selector'], inputs['names']
    budget = config['smoke_budget' if phase == 'smoke' else 'formal_budget']
    seed_rng = random.Random(config['seed'])
    seeds = [seed_rng.randint(1, 2**31 - 1) for _ in range(budget)]
    protocol = dict(schema='nova-vcs-run-v1', method=config['method'], phase=phase, budget=budget,
                    workers=config['workers'], logical_batch_size=config['logical_batch_size'], seed=config['seed'], seeds=seeds,
                    initial_runs=39, initial_union=508, bin_count=4507, cluster_count=751,
                    sequence_pool=list(inputs['entries']), test_catalog_entries=list(inputs['entries'].values()),
                    policy=config['policy'], source_sha256=manifest, refill_mode='continuous', retried=0,
                    initial_csv_sha256=config['expected_sha256']['initial_csv'],
                    conversion_source_sha256=config['expected_sha256']['conversion_source'],
                    simv_sha256=config['expected_sha256']['simv'], mapping_sha256=config['expected_sha256']['mapping'],
                    catalog_sha256=config['expected_sha256']['catalog'], steering={'enabled':False},
                    solver_optimization=config['solver_optimization'], cold_start_counts_in_formal_budget=True,
                    clustering='reuse frozen 751-cluster partition; no NOVA reclustering',
                    walltime='first submission through last completed feedback',
                    coverage_stop='stop new submissions if all bins covered; drain active jobs')
    write(run / 'protocol.json', protocol)
    protocol_hash = sha(run / 'protocol.json')
    chain, event_index = '0' * 64, 0
    results, curve = [], []
    submitted = failed = max_active = 0
    cpu = selector_seconds = 0.0
    missing_cpu = 0
    first = None
    futures = {}

    def emit(kind, **fields):
        nonlocal chain, event_index
        record = dict(event_index=event_index, event=kind, timestamp=time.time(), previous_hash=chain,
                      policy_hash=protocol_hash, **fields)
        chain = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        record['event_hash'] = chain
        with (run / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
        event_index += 1
        return record

    def submit(executor):
        nonlocal submitted, max_active, first, selector_seconds
        if submitted >= budget or failed:
            return False
        start = time.perf_counter()
        arm, decision = selector.choose()
        selector_seconds += time.perf_counter() - start
        if arm is None:
            return False
        selector.reserve(arm)
        run_id = submitted
        submitted += 1
        event = emit('submit', run_id=run_id, seed=seeds[run_id], test_id=arm, decision=decision,
                     feedback_count=len(results), active=len(futures) + 1)
        if first is None:
            first = event['timestamp']
        futures[executor.submit(backend, run, run_id, arm, seeds[run_id])] = (run_id, arm)
        max_active = max(max_active, len(futures))
        return True

    with (run / 'vectors.csv').open('w', newline='', encoding='utf-8') as vectors:
        vector_writer = csv.writer(vectors)
        vector_writer.writerow(['run_id', 'accepted', *names])
        with ThreadPoolExecutor(max_workers=config['workers']) as executor:
            for _ in range(min(config['workers'], budget)):
                if not submit(executor):
                    break
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                # Stable ordering when multiple futures return in the same poll.
                for future in sorted(done, key=lambda f: futures[f][0]):
                    run_id, arm = futures.pop(future)
                    try:
                        result, vector = future.result()
                    except Exception as exc:
                        result, vector = dict(run_id=run_id,test_id=arm,test_description=arm,seed=seeds[run_id],
                                              status='failed',error=f'{type(exc).__name__}: {exc}'), None
                    if result['run_id'] != run_id or result['test_id'] != arm or result['seed'] != seeds[run_id]:
                        result.update(status='failed',error='Worker identity/seed mismatch')
                        vector = None
                    accepted = result['status'] == 'success' and vector is not None
                    before = selector.union.copy()
                    selector.feedback(arm, vector if accepted else None)
                    failed += int(not accepted)
                    encoded = [int(v) for v in vector] if accepted else [0] * len(names)
                    covered = int(selector.union.sum())
                    gain = covered - int(before.sum())
                    runtime = result.get('simulator_cpu_seconds')
                    if runtime is not None and math.isfinite(runtime) and runtime >= 0:
                        cpu += runtime
                    else:
                        missing_cpu += 1
                    result.update(status='success' if accepted else 'failed', feedback_order=len(results) + 1,
                                  accumulated_covered=covered, coverage_percent=covered / len(names) * 100,new_bins=gain)
                    results.append(result)
                    vector_writer.writerow([run_id, accepted, *encoded]);vectors.flush()
                    event = emit('feedback', run_id=run_id,test_id=arm,accepted=accepted,active=len(futures),
                                 feedback_count=len(results),new_bins=gain,accumulated_covered=covered,
                                 simulator_cpu_seconds=runtime,vector_sha256=hashlib.sha256(bytes(encoded)).hexdigest())
                    curve.append(dict(feedback_order=len(results),run_id=run_id,accepted=accepted,
                                      accumulated_simulator_cpu_seconds=cpu,wall_seconds=event['timestamp'] - first,
                                      covered_bins=covered,coverage_percent=covered / len(names) * 100,new_bins=gain))
                    write(run / 'progress.json',dict(submitted=submitted,completed=len(results),failed=failed,
                          active=len(futures),coverage_bins=covered,denominator=len(names),event_head=chain))
                    print(f'NOVA_PROGRESS {len(results)}/{budget} failed={failed} covered={covered}/{len(names)}',flush=True)
                    submit(executor)
    emit('finished', submitted=submitted,completed=len(results),failed=failed)
    status = 'stopped_for_diagnosis' if failed else 'completed' if len(results)==budget else 'coverage_closed'
    summary = dict(method=config['method'],status=status,submitted=submitted,completed=len(results),failed=failed,retried=0,
                   accepted=len(results)-failed,max_active_workers=max_active,bin_count=len(names),initial_union_bins=508,
                   final_covered_bins=int(selector.union.sum()),final_coverage_percent=float(selector.union.mean()*100),
                   accumulated_simulator_cpu_seconds_all_attempts=cpu,missing_cpu_time_count=missing_cpu,
                   wall_seconds=curve[-1]['wall_seconds'] if curve else 0,selection_wall_seconds=selector_seconds,
                   policy_sha256=protocol_hash,event_chain_head=chain,steering_enabled=False)
    write(run / 'summary.json', summary);write(run / 'run_results.json', results)
    if curve:
        with (run / 'coverage_curve.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(curve[0]));writer.writeheader();writer.writerows(curve)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir',type=Path,required=True)
    parser.add_argument('--phase',choices=['smoke','formal'],default='smoke')
    parser.add_argument('--server-root',type=Path,default=REPO)
    parser.add_argument('--preflight-only',action='store_true')
    args = parser.parse_args()
    inputs = load_inputs()
    manifest = source_manifest(inputs)
    if args.result_dir.exists():
        parser.error('Output must be a new directory; earlier results are never overwritten')
    # Preflight can verify the actual server build without executing a simulator.
    backend = VCSBackend(inputs,args.server_root)
    args.result_dir.mkdir(parents=True,exist_ok=False)
    if args.preflight_only:
        arm,decision=inputs['selector'].choose()
        write(args.result_dir/'preflight.json',dict(status='pass',simulation_executed=False,
              initial_runs=39,initial_bins=508,bin_count=4507,cluster_count=751,test_count=17,
              first_test_id=arm,decision=decision,source_sha256=manifest,simv_sha256=sha(backend.paths['simv'])))
        print('NOVA_PREFLIGHT_PASS simulation_executed=False')
        return 0
    summary = run_scheduler(inputs,args.result_dir,args.phase,backend,manifest)
    return 0 if summary['status']=='completed' and summary['failed']==0 else 1


if __name__=='__main__':
    sys.exit(main())
