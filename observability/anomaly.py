"""Anomaly detection starter.

Z-score is deliberately the default baseline. Students should improve `auto`
mode for seasonality/outliers rather than deleting the simple implementation.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
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
    """Robust MAD detector handling zero-MAD and constant histories gracefully."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    diff = abs(float(current) - median)

    if mad == 0:
        # If median absolute deviation is zero (e.g. constant history or single outlier)
        # Check non-zero differences excluding extreme outliers
        non_zero_diffs = np.abs(values - median)[np.abs(values - median) > 0]
        if non_zero_diffs.size > 0:
            scale = float(np.median(non_zero_diffs))
            modified_z = 0.6745 * diff / scale
        else:
            # Entire history is identical
            scale = max(abs(median) * 0.1, 1.0)
            modified_z = 0.6745 * diff / scale if diff > 0 else 0.0

        # If there is a significant percentage deviation from constant median (> 20%)
        if diff / max(abs(median), 1.0) >= 0.2:
            modified_z = max(modified_z, threshold + 1.0)
    else:
        modified_z = 0.6745 * diff / mad

    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }



def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detector supporting seasonality, robust MAD, and z-score."""
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "auto":
        # Check context for segment history (e.g. same day of week)
        eff_history = list(history)
        if context:
            if "same_segment_history" in context and len(context["same_segment_history"]) >= 3:
                eff_history = list(context["same_segment_history"])
            elif "known_event" in context and context["known_event"] is not None:
                # Known promotion or scheduled maintenance adjusts threshold
                threshold = threshold * 1.5

        # Choose robust MAD if sufficient samples, else Z-score
        if len(eff_history) >= 5:
            res = mad_detector(current, eff_history, threshold=threshold)
            res["method"] = "auto:mad"
        else:
            res = zscore_detector(current, eff_history, threshold=threshold)
            res["method"] = "auto:zscore"

        if context:
            res["context_used"] = list(context.keys())
        return res

    raise ValueError(f"Unsupported method: {method}")
