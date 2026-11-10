#!/usr/bin/env python3
"""Real VCS probes for wide unsteered jump and zero-valued watchdog targets."""
import argparse
import csv
import importlib.util
import json
import re
from pathlib import Path

from stage08_stable_coverage_v20 import StableCoverageSchema
from aon_timer_coverage_steering_v22 import confirmed_in_log, map_feature, plusargs


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root
    build = root / 'scratch/stage08_v22_20261110'
    output = root / 'runs/stage08_v22_parameter_probe_verified_20261110'
    output.mkdir(exist_ok=False)
    converter = module(root / 'scratch/stage08_v20_20261110/tools/run_stage06_conversion_stable.py', 'probe_converter')
    corpus = module(root / 'scratch/stage08_vcs_paper_ucb_20261109_v19/source/run_aon_timer_initial_corpus.py', 'probe_corpus')
    with (root / 'runs/stage07_recluster_xml_20261110_v20/bin_to_cluster.csv').open() as handle:
        names = sorted(row['feature_name'] for row in csv.DictReader(handle))
    schema = StableCoverageSchema(converter, root / 'runs/stage06_conversion_20261101T_v10/reports/original_g0', names)
    cases = [
        ('jump_unsteered', 'aon_timer_jump_vseq', [], 42, None),
        ('smoke_safe', 'aon_timer_smoke_vseq', [], 42, None),
        ('bark_zero', 'aon_timer_jump_vseq', ['+aon_steer_field=2', '+aon_steer_value=0'], 43, None),
        ('bite_zero', 'aon_timer_jump_vseq', ['+aon_steer_field=3', '+aon_steer_value=0'], 44, None),
    ]
    for offset, field in enumerate(('wkup_thold', 'wdog_bark_thold', 'wdog_bite_thold', 'prescaler')):
        target = next(t for name in names if (t := map_feature(name)) is not None
                      and t['field'] == field and t.get('range_low', 0) > 10)
        target['status'] = 'targeted'
        sequence = 'aon_timer_prescaler_vseq' if field == 'prescaler' else 'aon_timer_jump_vseq'
        cases.append((field + '_exact_interval', sequence, plusargs(target), 45 + offset, target['target_bin']))
    evidence = []
    for index, (label, sequence, directed_plusargs, seed, target_bin) in enumerate(cases):
        job_dir = output / label
        job_dir.mkdir()
        job = {'result_root': str(job_dir / 'raw'), 'test_name': sequence.removesuffix('_vseq'),
               'index': 0, 'global_run_id': index, 'seed': seed, 'sequence': sequence,
               'simv': str(build / 'build_scratch/stage08-ucb-v22/aon_timer-sim-vcs/default/simv'),
               'dv_root': str(build / 'source/opentitan/hw/dv'), 'timeout_seconds': 1200,
               'extra_plusargs': directed_plusargs}
        execution = corpus.run_one(job)
        ok = execution['vcs_return_code'] == 0 and execution['uvm_pass'] and execution['uvm_error'] == execution['uvm_fatal'] == 0
        row = {'case': label, 'sequence': sequence, 'seed': seed, 'uvm_pass': bool(ok)}
        if ok:
            raw = job_dir / 'raw' / job['test_name'] / '0'
            expected_target = map_feature(target_bin) if target_bin else None
            if label in ('bark_zero', 'bite_zero'):
                expected_target = {'field_id': 2 if label == 'bark_zero' else 3, 'value': 0}
            if expected_target:
                expected_target['status'] = 'targeted'
                row['steering_applied_confirmed'] = confirmed_in_log(expected_target, (raw / 'run.log').read_text(errors='replace'))
                ok = ok and row['steering_applied_confirmed']
            report, _, _ = converter.run_urg({'source_root': str(job_dir / 'raw'),
                'relative_run_dir': str(raw.relative_to(job_dir / 'raw')), 'source': 'online', 'global_run_id': index},
                job_dir / 'reports', 'urg', 300)
            counts = schema.parse(report, raw / 'coverage/default.vdb')
            (job_dir / 'coverage_counts.json').write_text(json.dumps(counts))
            row['parsed_bin_count'] = len(counts)
            row['covered_bins'] = sum(value > 0 for value in counts.values())
            cfg_hits = [name for name, value in counts.items() if value > 0 and '::timer_cfg_cg||variable||' in name]
            row['configuration_bin_hits'] = cfg_hits
            if target_bin:
                row['target_bin'] = target_bin
                row['exact_target_hit'] = counts[target_bin] > 0
                ok = ok and row['exact_target_hit']
            if label == 'jump_unsteered':
                ranges = [re.search(r'\|\|name:(?:wkup|bark|bite)\[(0x[0-9a-f]+|[0-9]+):', name, re.I)
                          for name in cfg_hits]
                row['wide_interior_bin_confirmed'] = any(
                    int(match.group(1), 16 if match.group(1).lower().startswith('0x') else 10) > 10
                    for match in ranges if match)
                ok = ok and row['wide_interior_bin_confirmed']
            if label in ('bark_zero', 'bite_zero'):
                prefix = 'bark' if label == 'bark_zero' else 'bite'
                row['zero_target_hit'] = any(f'||name:{prefix}_0||' in name for name in cfg_hits)
                ok = ok and row['zero_target_hit']
        row['status'] = 'pass' if ok else 'fail'
        evidence.append(row)
        result = {'status': 'pass' if len(evidence) == len(cases) and all(r['status'] == 'pass' for r in evidence) else 'in_progress', 'cases': evidence}
        (output / 'probe_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        if not ok:
            raise RuntimeError(f'parameter probe failed: {label}')
    print('V22_REAL_PARAMETER_PROBES_PASS')


if __name__ == '__main__':
    main()
