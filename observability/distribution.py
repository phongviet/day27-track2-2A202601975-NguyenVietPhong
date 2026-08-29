from __future__ import annotations

from typing import Any, Iterable

import numpy as np
from scipy.stats import ks_2samp


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    alpha: float = 0.01,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Robust distribution shift detector combining Kolmogorov-Smirnov test and mean ratio."""
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)
    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "ks_and_mean_ratio", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))
    if base_mean == 0:
        mean_ratio = float("inf") if cur_mean != 0 else 1.0
    else:
        mean_ratio = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    # Run two-sample Kolmogorov-Smirnov test if enough samples
    if cur.size >= 3 and base.size >= 3:
        ks_res = ks_2samp(cur, base)
        ks_stat = float(ks_res.statistic)
        p_value = float(ks_res.pvalue)
    else:
        ks_stat = 0.0
        p_value = 1.0

    is_anomaly = bool(mean_ratio >= ratio_threshold or (p_value < alpha and ks_stat > 0.4))
    score = float(mean_ratio if not np.isinf(mean_ratio) else 999.0)

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "ks_stat": ks_stat,
        "p_value": p_value,
        "method": "ks_and_mean_ratio",
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, ks_stat={ks_stat:.3f}, p_val={p_value:.4f}",
    }

