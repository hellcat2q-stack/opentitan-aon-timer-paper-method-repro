"""Frozen common inputs and VCS artifacts for the independent NOVA port."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
from nova_policy import NovaSelector, Parameters

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def load_inputs(config_path=None):
    config_path = Path(config_path or PACKAGE / 'configs/nova_17test.json').resolve()
    config = read(config_path)
    paths = {'config': config_path,
             'initial_csv': PACKAGE / 'inputs/coverage_bin_by_run_39.csv',
             'mapping': PACKAGE / 'inputs/bin_to_cluster.csv',
             'catalog': PACKAGE / 'inputs/aon_timer_17test_catalog.json',
             'corpus_source': REPO / '05_初始语料/tools/run_aon_timer_initial_corpus.py',
             'conversion_source': PACKAGE / 'vendor/run_stage06_conversion_stable.py',
             'stable_schema': REPO / '08_两层UCB在线复现/tools/stage08_stable_coverage_v20.py',
             'uvm_checker': REPO / '08_两层UCB在线复现/tools/verify_stage08_uvm_replay.py'}
    for key, path in paths.items():
        if key != 'config' and sha(path) != config['expected_sha256'][key]:
            raise ValueError(f'Frozen input/source hash mismatch: {key}')
    catalog = read(paths['catalog'])
    if catalog != read(REPO / 'configs/aon_timer_17test_catalog.json'):
        raise ValueError('Packaged catalog differs from the shared 17-test catalog')
    entries = {e['id']: e for e in catalog['tests']}
    if len(entries) != config['selected_test_count'] or len(entries) != 17:
        raise ValueError('Expected all 17 official test IDs')
    with paths['initial_csv'].open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        names = sorted(reader.fieldnames[reader.fieldnames.index('report_id') + 1:])
        initial = list(reader)
    with paths['mapping'].open(newline='', encoding='utf-8') as f:
        mapping_rows = list(csv.DictReader(f))
    mapping = {r['feature_name']: 'category_' + str(r['cluster_id']) for r in mapping_rows}
    if len(names) != 4507 or len(mapping_rows) != len(mapping) or set(names) != set(mapping):
        raise ValueError('Initial matrix and cluster mapping must have the same 4507 unique bins')
    if len(initial) != 39 or len(initial) != config['initial_runs']:
        raise ValueError('Expected unchanged 39-run warm-up data')
    clusters = {}
    for i, name in enumerate(names):
        clusters.setdefault(mapping[name], []).append(i)
    if len(clusters) != config['cluster_count']:
        raise ValueError('Unexpected cluster partition')
    history = []
    for row in initial:
        if row['sequence'] not in entries or row['uvm_pass'] != 'True':
            raise ValueError('Initial observation is outside the catalog or lacks UVM PASS')
        counts = np.array([int(row[n]) for n in names])
        if np.any(counts < 0):
            raise ValueError('Negative initial coverage count')
        history.append((row['sequence'], (counts > 0).astype(np.uint8)))
    selector = NovaSelector(entries, clusters, history, config['seed'], Parameters(**config['policy']))
    if int(selector.union.sum()) != 508 or config['initial_union'] != 508:
        raise ValueError('Expected 508 initially covered bins')
    return {'config': config, 'paths': paths, 'entries': entries, 'names': names,
            'mapping': mapping, 'history': history, 'clusters': clusters, 'selector': selector}


def backend_paths(root):
    root = Path(root).resolve()
    build = root / 'scratch/stage09_17test_repair_v2_20261125'
    return {'simv': build / 'build_scratch/stage08-ucb-v30/aon_timer-sim-vcs/default/simv',
            'dv_root': build / 'source/opentitan/hw/dv',
            'canonical_report': root / 'runs/stage06_conversion_20261101T_v10/reports/original_g0'}


def verify_backend(inputs, root):
    paths = backend_paths(root)
    for key in ('simv', 'canonical_report'):
        path = paths[key] / 'groups.txt' if key == 'canonical_report' else paths[key]
        if sha(path) != inputs['config']['expected_sha256'][key]:
            raise ValueError(f'Baseline V31 artifact differs: {key}')
    if not (paths['dv_root'] / 'tools/sim.tcl').is_file():
        raise ValueError('DV Tcl is missing')
    return paths


def source_manifest(inputs):
    files = set(inputs['paths'].values())
    files.add(REPO / '08_两层UCB在线复现/tools/audit_stage08_urg_union_v22.py')
    files.add(REPO / 'configs/aon_timer_17test_catalog.json')
    files.update(p for p in PACKAGE.rglob('*') if p.is_file() and p.suffix in ('.py', '.json')
                 and 'evidence' not in p.relative_to(PACKAGE).parts)
    return {str(p.relative_to(REPO)): sha(p) for p in sorted(files)}


def verify_sources(manifest):
    for relative, expected in manifest.items():
        if sha(REPO / relative) != expected:
            raise ValueError(f'Frozen experiment source changed: {relative}')
