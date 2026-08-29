from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from observability.anomaly import detect_anomaly
from observability.distribution import detect_distribution_shift


def approximate_token_lengths(texts: Iterable[str]) -> list[int]:
    # Deliberately tokenizer-free so hidden evaluation needs no model download.
    return [len(str(t).split()) for t in texts]


def detect_text_length_shift(
    current_texts: Iterable[str],
    baseline_batch_means: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    lengths = approximate_token_lengths(current_texts)
    current_mean = float(np.mean(lengths)) if lengths else 0.0
    result = detect_anomaly(
        current_mean,
        baseline_batch_means,
        method="auto",
        threshold=threshold,
    )
    result["metric"] = "mean_text_length"
    result["current_mean"] = current_mean
    result["method"] = f"text_length:{result['method']}"
    return result


def detect_embedding_norm_shift(
    current_norms: Iterable[float],
    baseline_norms: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detect embedding drift using the full norm distributions, not only means."""
    cur = np.asarray(list(current_norms), dtype=float)
    base = np.asarray(list(baseline_norms), dtype=float)
    cur = cur[np.isfinite(cur)]
    base = base[np.isfinite(base)]

    if cur.size == 0 or base.size == 0:
        return {
            "is_anomaly": False,
            "score": 0.0,
            "method": "embedding_norm_distribution",
            "reason": "empty_or_nonfinite_input",
            "metric": "embedding_norm",
            "current_mean": float(np.mean(cur)) if cur.size else 0.0,
        }

    result = detect_distribution_shift(cur, base)
    result["metric"] = "embedding_norm"
    result["current_mean"] = float(np.mean(cur))
    result["method"] = "embedding_norm_distribution"
    return result
