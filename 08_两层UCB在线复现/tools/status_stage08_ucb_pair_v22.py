#!/usr/bin/env python3
"""Read compact current status without exposing raw simulator logs."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    result = {}
    for label, dirname in (
        ('v22_smoke', 'stage08_vcs_ucb_smoke30_20261110_v22'),
        ('v22_full', 'stage08_vcs_ucb_full1000_20261110_v22'),
        ('v20_control', 'stage08_vcs_paper_ucb_full1000_20261110_v20'),
    ):
        root = args.root / 'runs' / dirname
        if not root.exists():
            result[label] = {'status': 'not_started'}
            continue
        progress = root / 'progress.json'
        row = json.loads(progress.read_text()) if progress.exists() else {}
        events = root / 'events.jsonl'
        submitted = []
        if events.exists():
            for line in events.open():
                if line.endswith('\n'):
                    event = json.loads(line)
                    if event['event'] == 'submit':
                        submitted.append(event)
        row['selected_sequences'] = dict(Counter(event['sequence'] for event in submitted))
        row['target_statuses'] = dict(Counter(event.get('steering', {}).get('status') for event in submitted))
        row['target_hits'] = 0
        if events.exists():
            for line in events.open():
                if line.endswith('\n'):
                    event = json.loads(line)
                    if event['event'] == 'feedback' and event.get('steering_bin_hit'):
                        row['target_hits'] += 1
        summary = root / 'summary.json'
        row['status'] = json.loads(summary.read_text())['status'] if summary.exists() else 'running'
        result[label] = row
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
