#!/usr/bin/env python3
"""Run a separate 17-test matrix after verified reset-race regression gates."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

WORK = "stage09_17test_v31_all_20261125"
REPAIR = "stage09_17test_repair_v2_20261125"
EXPECTED_SIMV = "8b0fd96293a6f85dc1fd3984edf1cdd68f16e6482802c85d784b3722cb0b2760"
EXPECTED_PATCH = "92ba475b04ca930106dbc105972f6bd8ab729b8443939db54e654ed723e00ee8"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)


def export_metadata(root, work):
    out = root / "evidence" / WORK
    out.mkdir(exist_ok=True)
    for name in ("preregistration.json", "source_patch_audit.json", "gates.json", "launch.json", "status.json"):
        path = work / name
        if path.exists():
            # Full logs, VDBs and absolute school account paths stay on server.
            value = json.dumps(read(path), ensure_ascii=False).replace(str(root), "<ROOT>")
            value = value.replace(str(root.parent), "<SERVER_HOME>")
            write(out / name, json.loads(value))
    (out / "sha256.txt").write_text("".join(
        f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "sha256.txt"), encoding="utf-8")


def prepare(root, work):
    previous = root / "scratch/stage09_17test_all_20261124"
    repair = root / "scratch" / REPAIR
    original = root / "scratch/stage08_v30_wkup_phase_bound_20261111/source/opentitan"
    source = repair / "source/opentitan"
    simv = repair / "build_scratch/stage08-ucb-v30/aon_timer-sim-vcs/default/simv"
    patch = root / "08_两层UCB在线复现/tools/aon_timer_wkup_reset_race_v31.patch"
    assert sha(simv) == EXPECTED_SIMV
    assert sha(patch) == EXPECTED_PATCH
    work.mkdir(exist_ok=False)
    shutil.copytree(previous / "tools", work / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(previous / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(Path(__file__), work / "run_stage09_17test_v31.py")
    # Keep the policy/runner untouched. Only the matrix's artifact path and
    # expected build identity change; zero failures now gates formal runs too.
    matrix = work / "tools/run_stage09_matrix_v30.py"
    text = matrix.read_text()
    text = replace_once(text,
        'def paths(root):\n    v30 = root / "scratch/stage08_v30_wkup_phase_bound_20261111"',
        f'def paths(root):\n    v30 = root / "scratch/{REPAIR}"')
    text = replace_once(text,
        'matching = {key: protocol[key] == baseline[key] for key in keys}',
        'matching = {key: protocol[key] == (sha(paths(root)["simv"]) if key == "simv_sha256" else baseline[key]) for key in keys}')
    text = replace_once(text,
        '    if protocol["budget"] == 30:\n        assert summary["failed"] == 0, summary',
        '    assert summary["failed"] == 0, summary')
    text = text.replace("Same V30 build and all frozen inputs", "Same shared V31 repaired build and all original frozen inputs")
    text = text.replace("uniform V30 no-steering protocol", "uniform V31 no-steering protocol")
    text = text.replace("V30 build、seed", "V31 build、seed")
    matrix.write_text(text, encoding="utf-8")
    entry = work / "tools/run_stage09_17test_matrix_v30.py"
    text = entry.read_text().replace('DATE = "20261124"', 'DATE = "20261125"')
    text = text.replace('stage09_17test', 'stage09_17test_v31')
    text = text.replace('shared frozen V30 simv', 'shared repaired V31 simv')
    entry.write_text(text, encoding="utf-8")
    negative = work / "tools/check_stage08_wkup_stuck_low_v30.py"
    text = negative.read_text().replace('scratch/stage08_v30_wkup_phase_bound_20261111', f'scratch/{REPAIR}')
    text = text.replace('runs/stage08_v30_stuck_low_check_20261111', 'runs/stage09_17test_v31_stuck_low_20261125')
    negative.write_text(text, encoding="utf-8")
    # Independently apply the committed patch to copies of the five V30 files,
    # then require byte equality with the source used for the new binary.
    paths = [line[6:] for line in patch.read_text().splitlines() if line.startswith('+++ b/')]
    check = work / "source_patch_check"
    for rel in paths:
        dest = check / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / rel, dest)
    with patch.open('rb') as handle:
        subprocess.run(['patch', '--batch', '--forward', '-p1', '-d', str(check)], stdin=handle, check=True)
    comparisons = {rel: {'old_sha256': sha(original / rel), 'new_sha256': sha(source / rel),
                        'matches_applied_patch': sha(check / rel) == sha(source / rel)} for rel in paths}
    assert all(v['matches_applied_patch'] for v in comparisons.values())
    # The RTL, scoreboard and random-reset CSR audit must retain their checks.
    unchanged = ['hw/ip/aon_timer/dv/env/aon_timer_scoreboard.sv',
                 'hw/dv/sv/cip_lib/seq_lib/cip_base_vseq.sv']
    unchanged += [str(p.relative_to(original)) for p in (original / 'hw/ip/aon_timer/rtl').rglob('*.sv')]
    assert all(sha(original / p) == sha(source / p) for p in unchanged)
    write(work / 'source_patch_audit.json', {'status': 'pass', 'patch_sha256': sha(patch),
          'simv_sha256': sha(simv), 'changed_files': comparisons,
          'unchanged_rtl_scoreboard_and_reset_audit': {p: sha(source / p) for p in unchanged}})
    sys.path.insert(0, str(work / 'tools'))
    catalog_gate = load(entry, 'v31_catalog_setup')
    catalog_gate.verify_official_catalog(root, work / 'official_catalog_audit.json')
    dependencies = list((work / 'tools').glob('*.py')) + list((work / 'tests').glob('*.py'))
    dependencies += list((root / 'runtime17_deps').rglob('*.py'))
    for line in (previous / 'frozen_sha256.txt').read_text().splitlines():
        expected, filename = line.split(None, 1)
        path = Path(filename.strip())
        assert sha(path) == expected, path.name
        dependencies.append(path)
    dependencies += [simv, patch, work / 'run_stage09_17test_v31.py']
    dependencies += [p for p in (source / 'hw/ip/aon_timer').rglob('*') if p.is_file() and p.suffix in ('.sv', '.svh', '.hjson')]
    dependencies += [source / p for p in unchanged]
    (work / 'frozen_sha256.txt').write_text(''.join(f'{sha(p)}  {p}\n' for p in sorted(set(dependencies))), encoding='utf-8')
    protocol = read(previous / 'preregistration.json')
    protocol.update(schema='stage09-v31-reset-race-rerun-v1', created_at_server=datetime.now().astimezone().isoformat(),
        purpose='User-requested clean rerun after fixing the shared UVM reset race',
        simv_sha256=sha(simv), patch_sha256=sha(patch),
        previous_full_preserved=True, previous_incomplete_method_preserved=True,
        failed_seed_replays=[969559112, 1885763299, 589693528],
        official_catalog_audit_sha256=sha(work / 'official_catalog_audit.json'),
        gates_excluded_from_formal_budget=True, negative_fault_excluded_from_formal_budget=True,
        formal_failure_gate='Stop and preserve the failed attempt; no automatic retries or failure suppression',
        frozen_dependency_manifest_sha256=sha(work / 'frozen_sha256.txt'))
    write(work / 'preregistration.json', protocol)
    export_metadata(root, work)
    print('PREPARED', work, flush=True)


def regressions(root, work, status):
    sys.path.insert(0, str(work / 'tools'))
    from verify_stage08_uvm_replay import inspect_log
    corpus = load(root / '05_初始语料/tools/run_aon_timer_initial_corpus.py', 'v31_corpus')
    repair = root / 'scratch' / REPAIR
    output = root / 'runs/stage09_17test_v31_failed_seed_replays_20261125'
    output.mkdir(exist_ok=False)
    catalog = read(root / 'configs/aon_timer_17test_catalog.json')
    entry = next(e for e in catalog['tests'] if e['official_test'] == 'aon_timer_stress_all_with_rand_reset')
    jobs = [dict(result_root=str(output), test_name=entry['official_test'], index=i, global_run_id=i,
                 seed=seed, sequence=entry['sequence'], test_run_options=entry['run_options'],
                 simv=str(repair / 'build_scratch/stage08-ucb-v30/aon_timer-sim-vcs/default/simv'),
                 dv_root=str(repair / 'source/opentitan/hw/dv'), timeout_seconds=entry['timeout_seconds'])
            for i, seed in ((307, 969559112), (547, 1885763299), (918, 589693528))]
    write(output / 'protocol.json', {'jobs': jobs, 'simv_sha256': EXPECTED_SIMV, 'formal_budget_usage': 0})
    records = []
    def run(job):
        result = corpus.run_one(job)
        path = output / job['test_name'] / str(job['index'])
        checked = inspect_log((path / 'run.log').read_text(errors='replace'), result['vcs_return_code'])
        accepted = checked['status'] == 'pass' and result['urg_return_code'] == 0 and result.get('expected_groups') == 4525
        return {'status': 'pass' if accepted else 'failed', 'execution': result,
                'strict_uvm_check': checked, 'log_sha256': sha(path / 'run.log'),
                'result_sha256': sha(path / 'result.json')}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run, j) for j in jobs]
        for future in as_completed(futures):
            records.append(future.result())
            write(work / 'gates.json', {'status': 'running', 'failed_seed_records': records})
            status(phase='failed_seed_replays', completed=len(records), total=3,
                   failed=sum(r['status'] != 'pass' for r in records))
    gates = {'status': 'pass' if all(r['status'] == 'pass' for r in records) else 'failed', 'failed_seed_records': records}
    write(work / 'gates.json', gates)
    assert gates['status'] == 'pass', 'Failed seed regression failed; investigate preserved logs'
    status(phase='negative_fault_check')
    with (work / 'negative_fault.log').open('w') as log:
        subprocess.run([sys.executable, str(work / 'tools/check_stage08_wkup_stuck_low_v30.py'), '--root', str(root)],
                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True)
    negative = read(root / 'runs/stage09_17test_v31_stuck_low_20261125/negative_check.json')
    assert negative['status'] == 'pass' and negative['strict_wkup_assertion_fired']
    gates.update(negative_fault_check=negative)
    write(work / 'gates.json', gates)
    export_metadata(root, work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    dependencies = str(root / 'runtime17_deps')
    sys.path.insert(0, dependencies)
    os.environ['PYTHONPATH'] = dependencies + os.pathsep + os.environ.get('PYTHONPATH', '')
    work = root / 'scratch' / WORK
    if args.prepare:
        prepare(root, work)
        return
    import fcntl
    lock = (work / 'v31.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def status(**fields):
        fields.update(observed_at_server=datetime.now().astimezone().isoformat())
        write(work / 'status.json', fields)
        print(json.dumps(fields), flush=True)
        export_metadata(root, work)
    sys.path.insert(0, str(work / 'tools'))
    import run_stage09_matrix_v30 as matrix
    try:
        matrix.verify_manifest(work / 'frozen_sha256.txt')
        status(status='running', phase='failed_seed_replays', completed=0, total=3)
        regressions(root, work, status)
        matrix.verify_manifest(work / 'frozen_sha256.txt')
        status(status='running', phase='catalog_smoke_and_formal_matrix')
        env = os.environ.copy()
        env.update(PYTHONHASHSEED='0', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        command = [sys.executable, '-u', str(work / 'tools/run_stage09_17test_matrix_v30.py'), '--root', str(root)]
        with (work / 'matrix.log').open('w') as log:
            process = subprocess.Popen(command, env=env, cwd=root, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            write(work / 'matrix_launch.json', {'pid': process.pid, 'command': command})
            while process.poll() is None:
                state_path = work / 'workflow_status.json'
                if state_path.exists():
                    state = read(state_path)
                    if state.get('run_name'):
                        progress = root / 'runs' / state['run_name'] / 'progress.json'
                        if progress.exists() and read(progress).get('failed', 0) > 0:
                            os.killpg(process.pid, signal.SIGTERM)
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait()
                            raise RuntimeError('A simulation failed; preserved all outputs and stopped for diagnosis')
                time.sleep(10)
            assert process.returncode == 0, f'Matrix gate failed, see {work / "matrix.log"}'
        status(status='pass', phase='complete')
    except Exception as exc:
        status(status='failed', phase='stopped_for_diagnosis', error=f'{type(exc).__name__}: {exc}')
        raise


if __name__ == '__main__':
    main()
