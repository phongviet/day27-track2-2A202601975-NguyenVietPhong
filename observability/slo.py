from __future__ import annotations

import math
from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not isinstance(target, (int, float)) or isinstance(target, bool) or not math.isfinite(float(target)):
        raise ValueError("target must be a finite number between 0 and 1")
    target = float(target)
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if not isinstance(bad_events, int) or isinstance(bad_events, bool):
        raise ValueError("bad_events must be an integer")
    if not isinstance(total_events, int) or isinstance(total_events, bool):
        raise ValueError("total_events must be an integer")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")

    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }

    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, burn_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        # At exactly 1x burn the budget is fully consumed but not exceeded.
        "breached": bool(burn_rate > 1.0),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre_standard",
) -> dict[str, Any]:
    """SRE-style multi-window policy.

    Both windows must be elevated to page. This intentionally suppresses a
    short transient spike when the longer window remains healthy.
    """
    if policy != "sre_standard":
        raise ValueError(f"Unsupported policy: {policy}")

    for name, value in {
        "short_window_burn": short_window_burn,
        "long_window_burn": long_window_burn,
    }.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{name} must be numeric")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{name} must be finite and non-negative")

    short = float(short_window_burn)
    long = float(long_window_burn)

    if short >= 14.4 and long >= 14.4:
        severity, page, reason = "critical", True, "sustained_fast_burn_14.4x"
    elif short >= 6.0 and long >= 6.0:
        severity, page, reason = "warning", False, "sustained_medium_burn_6x"
    elif short >= 14.4 and long < 14.4:
        severity, page, reason = "warning", False, "transient_spike_suppressed"
    elif short >= 1.0 or long >= 1.0:
        severity, page, reason = "info", False, "slow_or_single_window_burn"
    else:
        severity, page, reason = "info", False, "healthy"

    return {
        "page": page,
        "severity": severity,
        "reason": reason,
        "short_window_burn": short,
        "long_window_burn": long,
    }
