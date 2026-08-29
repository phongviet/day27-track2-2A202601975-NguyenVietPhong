from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
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
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre_standard",
) -> dict[str, Any]:
    """Evaluates multi-window burn rate according to Google SRE alerting standards.

    Paging requires BOTH short-window AND long-window burn rates to exceed the
    critical threshold (14.4x for fast burn), which suppresses false-alarm pages
    caused by short transient spikes.
    """
    # 1. Critical fast burn: 2% budget consumed in 1 hour (14.4x rate) -> Page
    if short_window_burn >= 14.4 and long_window_burn >= 14.4:
        return {
            "page": True,
            "severity": "critical",
            "reason": "sustained_fast_burn_14.4x",
            "short_window_burn": float(short_window_burn),
            "long_window_burn": float(long_window_burn),
        }

    # 2. Moderate burn: 5% budget consumed in 6 hours (6.0x rate) -> Ticket / Warning
    if short_window_burn >= 6.0 and long_window_burn >= 6.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": "sustained_medium_burn_6x",
            "short_window_burn": float(short_window_burn),
            "long_window_burn": float(long_window_burn),
        }

    # 3. Transient spike: short window spikes but long window is calm -> Suppress page
    if short_window_burn >= 14.4 and long_window_burn < 14.4:
        return {
            "page": False,
            "severity": "warning",
            "reason": "transient_spike_suppressed",
            "short_window_burn": float(short_window_burn),
            "long_window_burn": float(long_window_burn),
        }

    # 4. Slow burn or healthy
    if short_window_burn >= 1.0 and long_window_burn >= 1.0:
        return {
            "page": False,
            "severity": "info",
            "reason": "slow_burn_detected",
            "short_window_burn": float(short_window_burn),
            "long_window_burn": float(long_window_burn),
        }

    return {
        "page": False,
        "severity": "info",
        "reason": "healthy",
        "short_window_burn": float(short_window_burn),
        "long_window_burn": float(long_window_burn),
    }

