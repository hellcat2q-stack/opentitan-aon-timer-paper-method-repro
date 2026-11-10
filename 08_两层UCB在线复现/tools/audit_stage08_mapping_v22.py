#!/usr/bin/env python3
"""Check target values against every bin in the frozen experimental universe."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json

import aon_timer_coverage_steering_v20 as old
import aon_timer_coverage_steering_v22 as new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mapping', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with open(args.mapping, encoding='utf-8', newline='') as handle:
        names = [row['feature_name'] for row in csv.DictReader(handle)]
    assert len(names) == len(set(names)) == 4507
    groups = defaultdict(Counter)
    for name in names:
        group = name.split('||')[0].split('::')[-1]
        before, after = old.map_feature(name), new.map_feature(name)
        groups[group]['total'] += 1
        groups[group]['mapped_v20'] += int(before is not None)
        groups[group]['mapped_v22'] += int(after is not None)
        if after and 'range_low' in after:
            assert after['range_low'] <= after['value'] <= after['range_high']
    with open(args.mapping, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    result = {'status': 'pass', 'bin_count': len(names), 'mapping_sha256': digest,
              'groups': {group: dict(counts) for group, counts in sorted(groups.items())},
              'mapped_v20': sum(v['mapped_v20'] for v in groups.values()),
              'mapped_v22': sum(v['mapped_v22'] for v in groups.values())}
    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({key: result[key] for key in ('status', 'bin_count', 'mapped_v20', 'mapped_v22')}))


if __name__ == '__main__':
    main()
