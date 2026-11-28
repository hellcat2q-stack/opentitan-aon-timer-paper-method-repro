#!/usr/bin/env python3
"""Explicit future entry: isolated smoke30/audit/URG gate, then formal1000."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from nova_common import PACKAGE, REPO, load_inputs, read, sha, source_manifest, verify_sources, write


def export(run, destination):
    destination.mkdir(exist_ok=False,parents=True)
    for name in ('protocol.json','summary.json','audit.json','raw_uvm_audit.json','union_audit.json',
                 'coverage_curve.csv','events.jsonl','vectors.csv'):
        text=(run/name).read_text(encoding='utf-8')
        text=text.replace(str(REPO),'<ROOT>').replace(str(REPO.parent),'<SERVER_HOME>')
        (destination/name).write_text(text,encoding='utf-8')
    safe={'run_id','test_id','test_description','test_name','official_test','sequence','seed','test_run_options',
          'status','vcs_return_code','urg_return_code','uvm_pass','uvm_error','uvm_fatal','parsed_bin_count',
          'run_covered_bins','simulator_cpu_seconds','feedback_order','new_bins','accumulated_covered','coverage_percent',
          'worker_start_time','worker_end_time','worker_wall_seconds'}
    write(destination/'run_results.json',[{k:v for k,v in row.items() if k in safe} for row in read(run/'run_results.json')])
    (destination/'sha256.txt').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(destination.iterdir())
                                               if p.is_file() and p.name!='sha256.txt'),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root',type=Path,default=REPO)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--execute',action='store_true',help='Actually run smoke and formal simulations; otherwise preflight only')
    args=parser.parse_args()
    if args.server_root.resolve()!=REPO:
        parser.error('Run the deployed checkout on the server; --server-root must match it')
    args.work_dir.mkdir(parents=True,exist_ok=False)
    inputs=load_inputs();frozen=source_manifest(inputs)
    write(args.work_dir/'frozen_sources.json',frozen)
    env=os.environ.copy()
    env.update(PYTHONHASHSEED='0',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    state={'status':'running','phase':'preflight','completed':[],
           'observed_at_server':datetime.now().astimezone().isoformat()}
    def status(**fields):
        state.update(fields,observed_at_server=datetime.now().astimezone().isoformat())
        write(args.work_dir/'status.json',state)
        print(json.dumps(state),flush=True)
    def call(command,log):
        with (args.work_dir/log).open('w') as stream:
            subprocess.run(command,cwd=REPO,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,check=True)
    try:
        entry=PACKAGE/'tools/run_nova_vcs.py'
        common=[sys.executable,'-u',str(entry),'--server-root',str(REPO)]
        call(common+['--result-dir',str(args.work_dir/'preflight'),'--preflight-only'],'preflight.log')
        if not args.execute:
            status(status='preflight_pass',phase='not_launched',simulation_executed=False)
            return
        # Lock all novelty and shared artifact identities before spending budget.
        for phase in ('smoke','formal'):
            verify_sources(frozen)
            run=args.work_dir/('smoke30' if phase=='smoke' else 'formal1000')
            status(phase=phase,run_name=str(run.relative_to(args.work_dir)))
            call(common+['--result-dir',str(run),'--phase',phase],phase+'.log')
            verify_sources(frozen)
            status(phase=phase+'_audit')
            call([sys.executable,str(PACKAGE/'tools/audit_nova.py'),'--run-dir',str(run)],phase+'_audit.log')
            call([sys.executable,str(REPO/'08_两层UCB在线复现/tools/audit_stage08_urg_union_v22.py'),
                  '--root',str(REPO),'--run-dir',str(run),'--output-dir',str(args.work_dir/(phase+'_urg_union'))],phase+'_urg.log')
            union=args.work_dir/(phase+'_urg_union')/'union_audit.json'
            assert read(union)['status']=='pass'
            shutil.copyfile(union,run/'union_audit.json')
            export(run,args.work_dir/'evidence'/phase)
            state['completed'].append(phase)
        status(status='pass',phase='complete')
    except Exception as exc:
        status(status='failed',phase='stopped_for_diagnosis',error=f'{type(exc).__name__}: {exc}')
        raise


if __name__=='__main__':main()
