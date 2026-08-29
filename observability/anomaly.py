"""Robust metric anomaly detection used by the stable student API."""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

_LARGE_SCORE = 1e12


def _finite_history(history: Iterable[float]) -> np.ndarray:
    """Convert history to finite floats; ignore NaN/inf instead of poisoning stats."""
    try:
        values = np.asarray(list(history), dtype=float)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    return values[np.isfinite(values)]


def _invalid_current_result(method: str, current: float) -> dict[str, Any] | None:
    try:
        value = float(current)
    except (TypeError, ValueError):
        return {
            "is_anomaly": True,
            "score": _LARGE_SCORE,
            "method": method,
            "reason": "current_value_is_not_numeric",
        }
    if not np.isfinite(value):
        return {
            "is_anomaly": True,
            "score": _LARGE_SCORE,
            "method": method,
            "reason": "current_value_is_not_finite",
        }
    return None


def zscore_detector(
    current: float, history: Iterable[float], threshold: float = 3.0
) -> dict[str, Any]:
    invalid = _invalid_current_result("zscore", current)
    if invalid is not None:
        return invalid

    values = _finite_history(history)
    if values.size < 3:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "zscore",
            "reason": "insufficient_history",
        }

    current_f = float(current)
    mean = float(np.mean(values))
    std = float(np.std(values))
    eps = max(1e-12, abs(mean) * 1e-12)

    if std <= eps:
        score = _LARGE_SCORE if abs(current_f - mean) > eps else 0.0
    else:
        score = abs(current_f - mean) / std

    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.6g}, std={std:.6g}, threshold={threshold}",
    }


def mad_detector(
    current: float, history: Iterable[float], threshold: float = 3.5
) -> dict[str, Any]:
    """Median/MAD detector that stays robust when MAD is exactly zero.

    Zero MAD often means at least half of the baseline is identical. Falling back
    to mean absolute deviation is not robust: one historical outlier can make a
    genuine anomaly look normal. In that case, the median itself is the robust
    baseline and any material departure is scored as extreme.
    """
    invalid = _invalid_current_result("mad", current)
    if invalid is not None:
        return invalid

    values = _finite_history(history)
    if values.size < 3:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "mad",
            "reason": "insufficient_history",
        }

    current_f = float(current)
    median = float(np.median(values))
    abs_dev = np.abs(values - median)
    mad = float(np.median(abs_dev))
    eps = max(1e-12, abs(median) * 1e-12)

    if mad <= eps:
        # Robust zero-scale fallback. Do not let a sparse extreme history outlier
        # inflate the denominator (which mean absolute deviation would do).
        delta = abs(current_f - median)
        modified_z = _LARGE_SCORE if delta > eps else 0.0
        reason = (
            f"median={median:.6g}, mad=0, zero_scale_fallback=true, "
            f"threshold={threshold}"
        )
    else:
        modified_z = 0.6745 * abs(current_f - median) / mad
        reason = f"median={median:.6g}, mad={mad:.6g}, threshold={threshold}"

    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": reason,
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detector.

    `auto` prefers same-segment history (e.g. same weekday) when enough data is
    available, then uses robust MAD. A known event raises the alert threshold to
    reduce expected-event false positives.
    """
    method = str(method).lower()
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method != "auto":
        raise ValueError(f"Unsupported method: {method}")

    base_history = list(history)
    effective_history = base_history
    baseline_source = "history"

    if context:
        segment = context.get("same_segment_history")
        if segment is not None:
            try:
                segment_values = list(segment)
            except TypeError:
                segment_values = []
            if _finite_history(segment_values).size >= 3:
                effective_history = segment_values
                baseline_source = "same_segment_history"

        if context.get("known_event") is not None:
            threshold *= 1.5

    finite_effective = _finite_history(effective_history)
    if finite_effective.size >= 5:
        result = mad_detector(current, finite_effective, threshold=threshold)
        result["method"] = "auto:mad"
    else:
        result = zscore_detector(current, finite_effective, threshold=threshold)
        result["method"] = "auto:zscore"

    result["reason"] += f"; baseline_source={baseline_source}"
    if context:
        result["context_used"] = sorted(context.keys())
    return result
