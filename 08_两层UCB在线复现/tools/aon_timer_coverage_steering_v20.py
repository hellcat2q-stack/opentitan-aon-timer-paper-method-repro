"""Map stable XML coverage identities to constrained AON Timer inputs."""
from __future__ import annotations

import re
from typing import Any

from aon_timer_coverage_steering import (
    confirmed_in_log,
    plusargs,
    select_target as _select_target,
    map_feature as _map_legacy_feature,
)


FIELD_IDS = {
    "wkup_thold": 1,
    "wdog_bark_thold": 2,
    "wdog_bite_thold": 3,
    "aim_bite": 4,
    "prescaler": 7,
}
_XML_AUTO_BIN = re.compile(r"^name:auto\[(\d+)\]$", re.IGNORECASE)


def _uniform_unsigned_bin_value(index: int, count: int, width: int) -> int:
    if not 0 <= index < count:
        raise ValueError(f"auto-bin ordinal {index} outside 0..{count - 1}")
    domain = 1 << width
    low = index * domain // count
    high = (index + 1) * domain // count - 1
    return low + (high - low) // 2


def map_feature(feature_name: str) -> dict[str, Any] | None:
    parts = feature_name.split("||")
    if len(parts) == 5 and parts[1] == "variable":
        auto = _XML_AUTO_BIN.fullmatch(parts[3])
        if auto:
            group = parts[0].split("::")[-1]
            coverpoint = parts[2]
            ordinal = int(auto.group(1))
            field = None
            value = None
            auxiliary = None
            reason = ""

            if group == "wake_up_timer_thold_hit_cg" and coverpoint in {
                "wkup_count_cp", "wkup_thold_cp"
            }:
                value = _uniform_unsigned_bin_value(ordinal, 512, 64)
                field = "wkup_thold"
                if coverpoint == "wkup_count_cp":
                    value = min(value + 5, (1 << 64) - 1)
                    reason = "threshold places the initialized wakeup count in the XML auto-bin ordinal"
            elif group in {
                "watchdog_timer_bark_thold_hit_cg",
                "watchdog_timer_bite_thold_hit_cg",
            } and coverpoint in {"wdog_count_cp", "wdog_thold_cp"}:
                if ordinal >= 256:
                    return None
                bite = group == "watchdog_timer_bite_thold_hit_cg"
                field = "wdog_bite_thold" if bite else "wdog_bark_thold"
                value = _uniform_unsigned_bin_value(ordinal, 256, 32)
                auxiliary = {"field": "aim_bite", "field_id": FIELD_IDS["aim_bite"], "value": int(bite)}
                if coverpoint == "wdog_count_cp":
                    value = min(value + 5, (1 << 32) - 1)
                    reason = "threshold and mode place the initialized watchdog count in the XML auto-bin ordinal"
                elif bite:
                    reason = "bite mode is selected so the bite threshold coverpoint is sampled"

            if field is not None:
                return {
                    "target_bin": feature_name,
                    "field": field,
                    "field_id": FIELD_IDS[field],
                    "value": value,
                    "auxiliary": auxiliary,
                    "reason": reason or "midpoint of the stable XML auto-bin ordinal",
                }
    return _map_legacy_feature(feature_name)


def select_target(bin_names, covered_bins, reserved_bins, sequence, rng):
    mapped = [target for name in bin_names if (target := map_feature(name)) is not None]
    if not mapped:
        return {"status": "no_mappable_bin"}

    compatible = []
    for target in mapped:
        is_prescaler = target["field"] == "prescaler"
        is_jump = "jump_vseq" in sequence
        if is_prescaler and "prescaler_vseq" not in sequence:
            continue
        if "prescaler_vseq" in sequence and not is_prescaler:
            continue
        if not is_prescaler and not is_jump:
            continue
        compatible.append(target)
    if not compatible:
        return {
            "status": "no_sequence_compatible_bin",
            "mappable_bins": len(mapped),
            "sequence": sequence,
        }

    available = [target for target in compatible
                 if target["target_bin"] not in covered_bins
                 and target["target_bin"] not in reserved_bins]
    if not available:
        return {"status": "no_uncovered_mappable_bin", "mappable_bins": len(compatible)}
    selected = dict(rng.choice(available))
    selected.update(status="targeted", mappable_bins=len(compatible), available_bins=len(available))
    return selected
