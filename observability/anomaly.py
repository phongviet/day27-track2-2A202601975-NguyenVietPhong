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
        # inflate the denominator. Require a material departure (e.g. >= 10% or >= 0.5 absolute)
        # to avoid false positives on tiny float precision noise while catching true level shifts.
        delta = abs(current_f - median)
        # Use the natural relative scale of the median (not clamped to 1.0)
        # so small-valued metrics (e.g. median=0.0001) still detect 10x shifts.
        # The absolute guard (delta >= 0.5) prevents float-noise false positives
        # for large-valued constants (e.g. 100.000001 vs 100.0).
        rel_diff = delta / max(abs(median), 1e-9)
        if rel_diff >= 0.1 or delta >= 0.5:
            modified_z = max(threshold + 1.0, 0.6745 * delta / max(abs(median) * 0.05, 0.1))
        else:
            modified_z = 0.0
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


def _trend_residual_detector(
    current: float,
    values: np.ndarray,
    expected_step: float,
    threshold: float = 3.5,
) -> dict[str, Any] | None:
    """Detect deviation from an expected step-over-step trend."""
    if values.size < 4:
        return None
    # Historical step errors relative to the expected trend.
    diffs = np.diff(values)
    residuals = diffs - expected_step
    median_r = float(np.median(residuals))
    mad_r = float(np.median(np.abs(residuals - median_r)))
    actual_step = float(current) - float(values[-1])
    actual_residual = actual_step - expected_step

    if mad_r <= 1e-12:
        deviation = abs(actual_residual - median_r)
        if deviation <= 1e-12:
            score = 0.0
            is_anomaly = False
        else:
            score = _LARGE_SCORE
            is_anomaly = True
    else:
        score = 0.6745 * abs(actual_residual - median_r) / mad_r
        is_anomaly = score > threshold

    return {
        "is_anomaly": bool(is_anomaly),
        "score": float(score),
        "method": "auto:trend",
        "reason": (
            f"expected_step={expected_step:.6g}, "
            f"actual_step={actual_step:.6g}, "
            f"residual_median={median_r:.6g}, "
            f"residual_mad={mad_r:.6g}, "
            f"threshold={threshold}"
        ),
    }


def _infer_same_weekday_segment(
    history: Iterable[float],
    day_of_week: int,
) -> list[float] | None:
    """Infer same-weekday values from consecutive daily history.
    Assumption: history[-1] is yesterday, history[-2] is two days ago, etc.
    """
    raw = list(history)
    if len(raw) < 21:  # Need at least 3 occurrences of the same weekday.
        return None
    try:
        current_dow = int(day_of_week) % 7
    except (TypeError, ValueError):
        return None

    segment: list[float] = []
    for i, value in enumerate(raw):
        days_before_current = len(raw) - i
        historical_dow = (current_dow - days_before_current) % 7
        if historical_dow != current_dow:
            continue
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value_f):
            segment.append(value_f)

    return segment if len(segment) >= 3 else None


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
    known_event = False

    if context:
        # Priority 1: explicitly supplied segment.
        segment = context.get("same_segment_history")
        if segment is not None:
            try:
                segment_values = list(segment)
            except TypeError:
                segment_values = []
            if _finite_history(segment_values).size >= 3:
                effective_history = segment_values
                baseline_source = "same_segment_history"
        # Priority 2: infer same weekday ourselves.
        elif context.get("day_of_week") is not None:
            inferred = _infer_same_weekday_segment(
                base_history,
                context["day_of_week"],
            )
            if inferred is not None:
                effective_history = inferred
                baseline_source = "inferred_same_weekday_from_history"

        known_event = bool(context.get("known_event", False))

    event_mult = 1.5 if known_event else 1.0

    finite_effective = _finite_history(effective_history)

    # A known trend changes what "normal" means:
    # judge the newest step rather than the absolute level.
    trend = context.get("trend") if context else None
    if trend is not None:
        try:
            expected_step = float(trend)
        except (TypeError, ValueError):
            expected_step = None
        if expected_step is not None and np.isfinite(expected_step):
            trend_result = _trend_residual_detector(
                current,
                finite_effective,
                expected_step,
                threshold=3.5 * event_mult,
            )
            if trend_result is not None:
                trend_result["reason"] += f"; baseline_source={baseline_source}"
                if context:
                    trend_result["context_used"] = sorted(context.keys())
                return trend_result

    if finite_effective.size >= 5:
        # Modified Z-Score standard threshold is 3.5
        mad_threshold = 3.5 * event_mult
        result = mad_detector(current, finite_effective, threshold=mad_threshold)
        result["method"] = "auto:mad"
    else:
        zscore_threshold = threshold * event_mult
        result = zscore_detector(current, finite_effective, threshold=zscore_threshold)
        result["method"] = "auto:zscore"

    result["reason"] += f"; baseline_source={baseline_source}"
    if context:
        result["context_used"] = sorted(context.keys())
    return result
