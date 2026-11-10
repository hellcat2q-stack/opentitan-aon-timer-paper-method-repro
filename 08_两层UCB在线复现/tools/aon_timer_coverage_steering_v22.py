"""Select safe targets within the cluster and sequence selected by UCB.

The stable XML ordinal mapping is inherited from v20. Large thresholds require
jump_vseq; smoke and stress-all can block indefinitely while counting from zero.
"""
import re

from aon_timer_coverage_steering_v20 import (
    confirmed_in_log, map_feature as _map_feature, plusargs,
)

_RANGE = re.compile(r"^name:([a-z_]+)\[(0x[0-9a-f]+|[0-9]+):(0x[0-9a-f]+|[0-9]+)\]$", re.I)
_CONFIG_FIELDS = {
    "prescale_cp": ("prescale", "prescaler", 7, 12),
    "bark_thold_cp": ("bark", "wdog_bark_thold", 2, 32),
    "bite_thold_cp": ("bite", "wdog_bite_thold", 3, 32),
    "wkup_thold_cp": ("wkup", "wkup_thold", 1, 64),
}


def map_feature(feature_name):
    parts = feature_name.split("||")
    if len(parts) != 5 or parts[1] != "variable" or parts[4] != "0":
        return None
    match = _RANGE.fullmatch(parts[3])
    if parts[0].split("::")[-1] == "timer_cfg_cg" and match:
        spec = _CONFIG_FIELDS.get(parts[2])
        if spec is None or match.group(1) != spec[0]:
            return None
        _, field, field_id, width = spec
        low, high = [int(text, 16 if text.lower().startswith("0x") else 10)
                     for text in match.groups()[1:]]
        if not 0 <= low <= high < (1 << width):
            return None
        return {"target_bin": feature_name, "field": field, "field_id": field_id,
                "value": low + (high - low) // 2,
                "auxiliary": {"field": "aim_bite", "field_id": 4, "value": 1} if field_id == 3 else None,
                "requires_jump": field != "prescaler", "range_low": low, "range_high": high,
                "reason": "midpoint of the exact decimal/hex interval in the frozen configuration bin name"}
    try:
        target = _map_feature(feature_name)
    except (ValueError, IndexError):
        return None
    if target is not None:
        target["requires_jump"] = target["field"] != "prescaler"
    return target


def select_target(bin_names, covered_bins, reserved_bins, sequence, rng):
    mapped = [target for name in bin_names if (target := map_feature(name)) is not None]
    if not mapped:
        return {"status": "no_mappable_bin"}
    is_prescaler = sequence == "aon_timer_prescaler_vseq"
    is_jump = sequence == "aon_timer_jump_vseq"
    compatible = [target for target in mapped
                  if (target["field"] == "prescaler" and is_prescaler)
                  or (target["field"] != "prescaler" and is_jump)]
    if not compatible:
        return {"status": "no_sequence_compatible_bin", "mappable_bins": len(mapped),
                "sequence": sequence}
    available = [target for target in compatible
                 if target["target_bin"] not in covered_bins
                 and target["target_bin"] not in reserved_bins]
    if not available:
        return {"status": "no_uncovered_mappable_bin", "mappable_bins": len(compatible)}
    selected = dict(rng.choice(available))
    selected.update(status="targeted", mappable_bins=len(compatible), available_bins=len(available))
    return selected
