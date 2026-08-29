from __future__ import annotations

import math

import pytest

from student_api import (
    detect_distribution,
    detect_metric,
    downstream_assets,
    rag_length_shift,
    slo_status,
)


def test_rag_length_explosion_is_detected_not_only_collapse():
    baseline_batch_means = [39.0, 40.0, 41.0, 42.0, 40.0, 39.0, 41.0]
    long_doc = " ".join(["token"] * 160)

    result = rag_length_shift([long_doc, long_doc], baseline_batch_means)

    assert result["is_anomaly"] is True


def test_empty_current_rag_batch_is_suspicious_when_baseline_is_nonempty():
    baseline_batch_means = [39.0, 40.0, 41.0, 42.0, 40.0, 39.0, 41.0]

    result = rag_length_shift([], baseline_batch_means)

    assert result["is_anomaly"] is True


def test_dataset_lineage_cycle_is_safe_and_deduplicated():
    graph = {
        "raw": ["stg", "audit"],
        "stg": ["mart"],
        "audit": ["mart"],
        "mart": ["raw", "dashboard"],
        "dashboard": [],
    }

    result = downstream_assets(graph, "raw")

    assert result == ["stg", "audit", "mart", "dashboard"]
    assert "raw" not in result
    assert len(result) == len(set(result))


@pytest.mark.parametrize(
    ("target", "bad", "total"),
    [
        (0.0, 0, 1),
        (1.0, 0, 1),
        (1.01, 0, 1),
        (0.99, -1, 10),
        (0.99, 11, 10),
        (0.99, 1, -10),
    ],
)
def test_slo_rejects_invalid_inputs(target, bad, total):
    with pytest.raises(ValueError):
        slo_status(target, bad_events=bad, total_events=total)


def test_short_anomaly_history_returns_finite_safe_shape():
    result = detect_metric(999.0, [100.0, 101.0], method="auto")

    assert result["is_anomaly"] is False
    assert math.isfinite(float(result["score"]))
    assert isinstance(result["method"], str)
    assert isinstance(result["reason"], str)


def test_distribution_empty_input_is_safe():
    result = detect_distribution([], [1.0, 2.0, 3.0])

    assert result["is_anomaly"] is False
    assert math.isfinite(float(result["score"]))


def test_distribution_constant_baseline_change_is_detected():
    result = detect_distribution([2.0] * 20, [1.0] * 20)

    assert result["is_anomaly"] is True
