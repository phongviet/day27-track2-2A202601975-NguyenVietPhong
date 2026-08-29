"""Distribution drift detection without undeclared third-party dependencies."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def _finite(values: Iterable[float]) -> np.ndarray:
    try:
        arr = np.asarray(list(values), dtype=float)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    return arr[np.isfinite(arr)]


def _ks_statistic(a: np.ndarray, b: np.ndarray) -> float:
    """Exact empirical two-sample KS D statistic (NumPy only)."""
    if a.size == 0 or b.size == 0:
        return 0.0
    points = np.sort(np.unique(np.concatenate([a, b])))
    a_sorted = np.sort(a)
    b_sorted = np.sort(b)
    cdf_a = np.searchsorted(a_sorted, points, side="right") / a.size
    cdf_b = np.searchsorted(b_sorted, points, side="right") / b.size
    return float(np.max(np.abs(cdf_a - cdf_b)))


def _ks_pvalue_asymptotic(d: float, n: int, m: int) -> float:
    """Useful deterministic approximation; anomaly decision also uses effect size."""
    if d <= 0.0 or n <= 0 or m <= 0:
        return 1.0
    en = math.sqrt(n * m / (n + m))
    if en <= 0:
        return 1.0
    lam = (en + 0.12 + 0.11 / en) * d
    total = 0.0
    for k in range(1, 101):
        term = 2.0 * ((-1.0) ** (k - 1)) * math.exp(-2.0 * (k * lam) ** 2)
        total += term
        if abs(term) < 1e-12:
            break
    return float(min(1.0, max(0.0, total)))


def _symmetric_ratio(a: float, b: float, *, eps: float = 1e-12) -> float:
    aa, bb = abs(float(a)), abs(float(b))
    if aa <= eps and bb <= eps:
        return 1.0
    lo = min(aa, bb)
    hi = max(aa, bb)
    if lo <= eps:
        return float("inf")
    return hi / lo


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    alpha: float = 0.01,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect location, scale, or CDF shift.

    Combines:
    - symmetric mean-ratio for obvious volume/level changes,
    - robust/standard scale ratio to catch same-mean shape changes,
    - two-sample KS with a practical D threshold to avoid p-value-only alerts.
    """
    cur = _finite(current_values)
    base = _finite(baseline_values)
    if cur.size == 0 or base.size == 0:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "ks_location_scale",
            "reason": "empty_or_nonfinite_input",
        }

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))
    cur_std = float(np.std(cur))
    base_std = float(np.std(base))
    pooled_std = math.sqrt(0.5 * (cur_std**2 + base_std**2))
    location_diff = abs(cur_mean - base_mean)
    scale_diff = abs(cur_std - base_std)

    # Location test: avoid inf/false positives when means are near zero
    if abs(base_mean) > 1e-4 and abs(cur_mean) > 1e-4:
        mean_ratio = _symmetric_ratio(cur_mean, base_mean)
        mean_alert = bool(
            mean_ratio >= ratio_threshold
            and location_diff > 0.1 * max(pooled_std, 1.0)
        )
    else:
        mean_ratio = 1.0
        standardized_diff = location_diff / max(pooled_std, 1e-6)
        mean_alert = bool(standardized_diff >= ratio_threshold)

    scale_ratio = _symmetric_ratio(cur_std, base_std)
    scale_alert = bool(scale_ratio >= ratio_threshold)

    ks_stat = _ks_statistic(cur, base)
    p_value = _ks_pvalue_asymptotic(ks_stat, int(cur.size), int(base.size))

    # Require practical CDF separation AND material difference in location or scale.
    # This prevents tiny float noise (< 1% scale) on discrete mass points from triggering false alarms.
    ks_practical_threshold = 0.25
    material_difference = (
        (location_diff / max(pooled_std, 1e-6)) >= 0.1
        or (scale_diff / max(pooled_std, 1e-6)) >= 0.1
        or scale_ratio >= 1.5
    )
    ks_alert = (
        cur.size >= 4
        and base.size >= 4
        and p_value < alpha
        and ks_stat >= ks_practical_threshold
        and material_difference
    )

    is_anomaly = bool(mean_alert or scale_alert or ks_alert)

    finite_scores = [
        (mean_ratio / ratio_threshold) if np.isfinite(mean_ratio) else 1e12,
        (scale_ratio / ratio_threshold) if np.isfinite(scale_ratio) else 1e12,
        ks_stat / ks_practical_threshold if material_difference else 0.0,
    ]
    score = float(max(finite_scores))

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "ks_stat": float(ks_stat),
        "p_value": float(p_value),
        "mean_ratio": float(mean_ratio) if np.isfinite(mean_ratio) else 1e12,
        "scale_ratio": float(scale_ratio) if np.isfinite(scale_ratio) else 1e12,
        "method": "ks_location_scale",
        "reason": (
            f"baseline_mean={base_mean:.6g}, current_mean={cur_mean:.6g}, "
            f"mean_ratio={mean_ratio:.6g}, scale_ratio={scale_ratio:.6g}, "
            f"ks_stat={ks_stat:.4f}, p_value={p_value:.4g}"
        ),
    }


