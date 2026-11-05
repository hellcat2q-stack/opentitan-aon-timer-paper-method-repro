"""Map stable AON Timer coverage labels to VCS sequence plusargs."""
from __future__ import annotations

import re
from typing import Any


FIELD_IDS = {
    "wkup_thold": 1,
    "wdog_bark_thold": 2,
    "wdog_bite_thold": 3,
    "aim_bite": 4,
    "prescaler": 7,
}

_AUTO_RANGE = re.compile(
    r"values:\s*\{\s*\[\s*(\d+)'h([0-9a-f]+)\s*:\s*"
    r"(\d+)'h([0-9a-f]+)\s*\]\s*\}",
    re.IGNORECASE,
)
_DECIMAL_RANGE = re.compile(
    r"values:\s*\{\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*\}",
    re.IGNORECASE,
)
_INDEXED_BIN = re.compile(r"name:([a-z_]+)\[(\d+)\]$", re.IGNORECASE)


def _midpoint(label: str) -> int | None:
    match = _AUTO_RANGE.search(label)
    if match:
        left_width, left_hex, right_width, right_hex = match.groups()
        if left_width != right_width:
            return None
        low, high = int(left_hex, 16), int(right_hex, 16)
    else:
        match = _DECIMAL_RANGE.search(label)
        if not match:
            return None
        low, high = map(int, match.groups())
    return low + (high - low) // 2 if low <= high else None


def _array_bin_value(index: int, count: int, width: int) -> int:
    low = 1
    high = (1 << width) - 2
    size = high - low + 1
    start = low + index * size // count
    stop = low + (index + 1) * size // count - 1
    return start + (stop - start) // 2


def _uniform_unsigned_bin_value(index: int, count: int, width: int) -> int:
    """Representative for one equal-width unsigned auto-bin in the full domain."""
    if not 0 <= index < count:
        raise ValueError("auto-bin index is outside its coverpoint")
    domain = 1 << width
    start = index * domain // count
    stop = (index + 1) * domain // count - 1
    return start + (stop - start) // 2


def map_feature(feature_name: str) -> dict[str, Any] | None:
    """Return a concrete parameter steering target for a direct AON Timer bin."""
    parts = feature_name.split("||")
    if len(parts) < 4 or parts[1] != "variable":
        return None

    covergroup = parts[0].split("::")[-1]
    coverpoint, label = parts[2], parts[3]
    field = None
    value = None
    auxiliary = None
    reason = ""

    if covergroup == "timer_cfg_cg":
        bins = {
            "prescale_cp": ("prescaler", "prescale", 12, 32),
            "bark_thold_cp": ("wdog_bark_thold", "bark", 32, 32),
            "bite_thold_cp": ("wdog_bite_thold", "bite", 32, 32),
            "wkup_thold_cp": ("wkup_thold", "wkup", 64, 64),
        }
        spec = bins.get(coverpoint)
        if not spec or not label.startswith("name:"):
            return None
        field, prefix, width, count = spec
        name = label[5:]
        if name == f"{prefix}_0":
            value, reason = 0, "named zero bin"
        elif name == f"{prefix}_max":
            value, reason = (1 << width) - 1, "named maximum bin"
        else:
            match = _INDEXED_BIN.fullmatch(label)
            if not match or match.group(1) != prefix:
                return None
            index = int(match.group(2))
            if not 0 <= index < count:
                return None
            value = _array_bin_value(index, count, width)
            reason = f"midpoint of {prefix}[{index}]"
        if field == "wdog_bite_thold":
            auxiliary = {
                "field": "aim_bite",
                "field_id": FIELD_IDS["aim_bite"],
                "value": 1,
            }

    elif covergroup == "wake_up_timer_thold_hit_cg":
        match = _AUTO_RANGE.search(label)
        if match is None or coverpoint not in {"wkup_count_cp", "wkup_thold_cp"}:
            return None
        left_width, left_hex, right_width, right_hex = match.groups()
        if left_width != right_width:
            return None
        low, high, ordinal = int(left_hex, 16), int(right_hex, 16), int(parts[4])
        # Stage 06's 512-bin wakeup coverpoints split the VCS-compressed low
        # range into bin 0 and the remaining range into bins 1..511.
        if (low, high) == (0, 0x007F_FFFF_FFFF_FFFF):
            index = 0 if ordinal == 0 else -1
        elif (low, high) == (0x0080_0000_0000_0000, (1 << 64) - 1):
            index = ordinal + 1
        else:
            return None
        if not 0 <= index < 512:
            return None
        field = "wkup_thold"
        value = _uniform_unsigned_bin_value(index, 512, 64)
        if coverpoint == "wkup_count_cp":
            value = min(value + 5, (1 << 64) - 1)
            reason = "threshold chosen to place the initialized count in this auto-bin"
    elif covergroup in {
        "watchdog_timer_bark_thold_hit_cg",
        "watchdog_timer_bite_thold_hit_cg",
    }:
        decimal_match = _DECIMAL_RANGE.search(label)
        if decimal_match is None:
            return None
        low, high = map(int, decimal_match.groups())
        ordinal = int(parts[4])
        if low != 0 or high != (1 << 32) - 1 or ordinal >= 256:
            return None
        value = _uniform_unsigned_bin_value(ordinal, 256, 32)
        threshold = "wdog_bark_thold" if "bark" in covergroup else "wdog_bite_thold"
        aim_bite = int(threshold == "wdog_bite_thold")
        if coverpoint == "wdog_thold_cp":
            field = threshold
            if aim_bite:
                auxiliary = {
                    "field": "aim_bite",
                    "field_id": FIELD_IDS["aim_bite"],
                    "value": aim_bite,
                }
        elif coverpoint == "wdog_count_cp":
            field = threshold
            value = min(value + 5, (1 << 32) - 1)
            auxiliary = {
                "field": "aim_bite",
                "field_id": FIELD_IDS["aim_bite"],
                "value": aim_bite,
            }
            mode = "bite" if aim_bite else "bark"
            reason = f"{mode} threshold midpoint and mode chosen to place count in this auto-bin"
        else:
            return None
    else:
        return None
    reason = reason or "midpoint of URG-reported value range"

    return {
        "target_bin": feature_name,
        "field": field,
        "field_id": FIELD_IDS[field],
        "value": value,
        "auxiliary": auxiliary,
        "reason": reason,
    }


def select_target(
    bin_names: list[str],
    covered_bins: set[str],
    reserved_bins: set[str],
    sequence: str,
    rng,
) -> dict[str, Any]:
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
        # Only jump_vseq programs the randomized counter values after timer initialization.
        # Other sequences start at zero, so steering a large threshold there can wait forever.
        if not is_prescaler and not is_jump:
            continue
        compatible.append(target)
    if not compatible:
        return {
            "status": "no_sequence_compatible_bin",
            "mappable_bins": len(mapped),
            "sequence": sequence,
        }

    available = [
        target for target in compatible
        if target["target_bin"] not in covered_bins
        and target["target_bin"] not in reserved_bins
    ]
    if not available:
        return {"status": "no_uncovered_mappable_bin", "mappable_bins": len(compatible)}
    selected = dict(rng.choice(available))
    selected["status"] = "targeted"
    selected["mappable_bins"] = len(compatible)
    selected["available_bins"] = len(available)
    return selected


def plusargs(target: dict[str, Any]) -> list[str]:
    if target.get("status") != "targeted":
        return []
    args = [
        f"+aon_steer_field={target['field_id']}",
        f"+aon_steer_value={target['value']:x}",
    ]
    auxiliary = target.get("auxiliary")
    if auxiliary:
        args.extend((
            f"+aon_steer_aux_field={auxiliary['field_id']}",
            f"+aon_steer_aux_value={auxiliary['value']:x}",
        ))
    return args


def confirmed_in_log(target: dict[str, Any], log_text: str) -> bool:
    """Confirm the sequence randomizer reported the requested constrained value."""
    if target.get("status") != "targeted":
        return False
    marker = (
        f"field={target['field_id']} requested=0x{target['value']:x} "
        f"actual=0x{target['value']:x}"
    ).lower()
    for line in log_text.splitlines():
        lowered = line.lower()
        if "aon_timer_steering_applied" not in lowered or marker not in lowered:
            continue
        auxiliary = target.get("auxiliary")
        if auxiliary:
            aux = (
                f"aux_field={auxiliary['field_id']} "
                f"aux_requested=0x{auxiliary['value']:x} "
                f"aux_actual=0x{auxiliary['value']:x}"
            ).lower()
            if aux not in lowered:
                continue
        return True
    return False
