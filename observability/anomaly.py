"""Anomaly detection.

Z-score is deliberately the default baseline. Students should improve `auto`
mode for seasonality/outliers rather than deleting the simple implementation.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Robust detector using the modified z-score."""
    values = np.asarray(list(history), dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 5:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        different = not np.isclose(float(current), median)
        return {
            "is_anomaly": bool(different),
            "score": float("inf") if different else 0.0,
            "method": "mad",
            "reason": f"median={median:.3f}, mad=0; constant_baseline={different is False}",
        }
    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def _trend_residual_detector(
    current: float, values: np.ndarray, expected_step: float, threshold: float = 3.5
) -> dict[str, Any] | None:
    diffs = np.diff(values)
    if diffs.size < 3:
        return None
    residuals = diffs - expected_step
    median_r = float(np.median(residuals))
    mad_r = float(np.median(np.abs(residuals - median_r)))
    actual_step = float(current) - float(values[-1])
    actual_residual = actual_step - expected_step

    if mad_r == 0:
        is_anomaly = not np.isclose(actual_residual, median_r)
        score = float("inf") if is_anomaly else 0.0
    else:
        score = 0.6745 * abs(actual_residual - median_r) / mad_r
        is_anomaly = score > threshold

    return {
        "is_anomaly": bool(is_anomaly),
        "score": float(score),
        "method": "auto:trend",
        "reason": (
            f"expected_step(trend)={expected_step}, actual_step={actual_step:.3f}, "
            f"residual={actual_residual:.3f}, median_residual={median_r:.3f}, mad_residual={mad_r:.3f}"
        ),
    }


def _infer_same_weekday_segment(history: list[float], day_of_week: int) -> list[float] | None:
    """Derive a same-weekday baseline directly from raw history series."""
    n = len(history)
    if n < 10:
        return None
    segment = [
        value
        for k, value in enumerate(reversed(history))  # k=0 -> history[-1] (yesterday)
        if (day_of_week - (k + 1)) % 7 == day_of_week % 7
    ]
    if len(segment) < 3:
        return None
    segment.reverse()
    return segment


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect a metric anomaly with explicit or context-aware baselines."""
    try:
        cur_val = float(current)
    except (TypeError, ValueError):
        return {"is_anomaly": True, "score": float("inf"), "method": method, "reason": "current_value_not_numeric"}
    if not np.isfinite(cur_val):
        return {"is_anomaly": True, "score": float("inf"), "method": method, "reason": "current_value_not_finite"}

    if method == "mad":
        return mad_detector(cur_val, history)
    if method == "zscore":
        return zscore_detector(cur_val, history, threshold=threshold)
    if method == "auto":
        context = context or {}

        # 1. Known events suppress anticipated anomalies
        if context.get("known_event"):
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "auto:event_suppressed",
                "reason": f"known_event={context['known_event']}",
            }

        # 2. Select baseline history (same_segment_history -> inferred weekday -> raw history)
        selected_history = context.get("same_segment_history")
        baseline_name = "same_segment_history"
        selected_history = list(selected_history) if selected_history is not None else []
        if len(selected_history) < 3:
            raw_list = [float(v) for v in history if np.isfinite(float(v))]
            day_of_week = context.get("day_of_week")
            inferred = None
            if day_of_week is not None:
                try:
                    inferred = _infer_same_weekday_segment(raw_list, int(day_of_week))
                except (TypeError, ValueError):
                    inferred = None
            if inferred is not None:
                selected_history = inferred
                baseline_name = "inferred_same_weekday_from_history"
            else:
                selected_history = raw_list
                baseline_name = "history"

        clean = np.asarray([float(v) for v in selected_history if np.isfinite(float(v))], dtype=float)

        if clean.size < 3:
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "auto:insufficient_history",
                "reason": f"insufficient_history; baseline={baseline_name}",
            }

        # 3. Trend context check
        trend = context.get("trend")
        if trend is not None:
            try:
                expected_step = float(trend)
            except (TypeError, ValueError):
                expected_step = None
            if expected_step is not None and np.isfinite(expected_step):
                trend_result = _trend_residual_detector(cur_val, clean, expected_step)
                if trend_result is not None:
                    trend_result["reason"] += f"; baseline={baseline_name}"
                    return trend_result

        # 4. Standard statistical detection
        if clean.size >= 5:
            result = mad_detector(cur_val, clean, threshold=max(3.5, threshold))
            result["method"] = "auto:mad"
        else:
            result = zscore_detector(cur_val, clean, threshold=threshold)
            result["method"] = "auto:zscore"

        result["reason"] += f"; baseline={baseline_name}"
        if context.get("day_of_week") is not None:
            result["reason"] += f"; day_of_week={context['day_of_week']}"
        return result

    raise ValueError(f"Unsupported method: {method}")
