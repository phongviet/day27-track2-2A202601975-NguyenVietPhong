from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from student_api import (
    column_downstream,
    detect_distribution,
    detect_metric,
    multiwindow_burn,
    rag_embedding_shift,
    slo_status,
    validate_orders,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "orders_contract.yaml"


def healthy_df(*, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Healthy data using parseable ISO timestamps, like the public fixture.

    `now` is dynamic so freshness tests do not depend on the calendar date.
    """
    if now is None:
        now = pd.Timestamp.now(tz="UTC")

    created_1 = now - pd.Timedelta(minutes=8)
    updated_1 = now - pd.Timedelta(minutes=4)
    created_2 = now - pd.Timedelta(minutes=7)
    updated_2 = now - pd.Timedelta(minutes=3)

    return pd.DataFrame(
        [
            {
                "order_id": 1,
                "customer_id": "C1",
                "amount": 10.0,
                "currency": "USD",
                "status": "completed",
                "created_at": created_1.isoformat(),
                "updated_at": updated_1.isoformat(),
            },
            {
                "order_id": 2,
                "customer_id": "C2",
                "amount": 20.0,
                "currency": "VND",
                "status": "pending",
                "created_at": created_2.isoformat(),
                "updated_at": updated_2.isoformat(),
            },
        ]
    )


def failed(issues: list[dict]) -> list[dict]:
    return [i for i in issues if not i.get("passed", False)]


def has_failed_check(
    issues: list[dict],
    *,
    column: str | None = None,
    check_contains: str | None = None,
    severity: str | None = None,
) -> bool:
    for issue in failed(issues):
        if column is not None and issue.get("column") != column:
            continue
        if check_contains is not None and check_contains not in str(issue.get("check", "")).lower():
            continue
        if severity is not None and issue.get("severity") != severity:
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# Contract / deterministic validation
# ---------------------------------------------------------------------------

def test_missing_required_column_is_critical():
    df = healthy_df().drop(columns=["customer_id"])
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(
        issues,
        column="customer_id",
        check_contains="required",
        severity="critical",
    )


def test_required_null_is_detected():
    df = healthy_df()
    df.loc[0, "customer_id"] = None
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(issues, column="customer_id", check_contains="null")


def test_negative_amount_is_out_of_range():
    df = healthy_df()
    df.loc[0, "amount"] = -0.01
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(issues, column="amount", check_contains="range")


def test_numeric_string_is_type_drift_not_silently_coerced():
    df = healthy_df()
    df["amount"] = ["10.0", "20.0"]
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(issues, column="amount", check_contains="type")


def test_fractional_order_id_fails_integer_type():
    df = healthy_df()
    df["order_id"] = [1.5, 2.5]
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(issues, column="order_id", check_contains="type")


def test_stale_batch_fails_freshness_with_warning_severity():
    now = pd.Timestamp.now(tz="UTC")
    df = healthy_df(now=now)

    # Contract allows max 30 minutes. Make the newest row > 2 hours old.
    df["updated_at"] = [
        (now - pd.Timedelta(hours=3)).isoformat(),
        (now - pd.Timedelta(hours=2)).isoformat(),
    ]

    issues = validate_orders(df, CONTRACT)

    # Do not over-constrain the exact check name; require a failing freshness-like
    # signal on updated_at with the contract-level warning severity.
    assert has_failed_check(
        issues,
        column="updated_at",
        check_contains="fresh",
        severity="warning",
    )


def test_column_rule_severity_is_preserved():
    df = healthy_df()
    df.loc[0, "status"] = "shipped"  # not in accepted_values
    issues = validate_orders(df, CONTRACT)

    assert has_failed_check(
        issues,
        column="status",
        check_contains="accepted",
        severity="warning",
    )


# ---------------------------------------------------------------------------
# Metric anomaly detection
# ---------------------------------------------------------------------------

def test_auto_is_robust_to_single_history_outlier():
    # One huge historical outlier inflates mean/std enough to hide a real drop
    # from naive z-score. Robust auto mode should still catch the current value.
    history = [100.0] * 19 + [10_000.0]
    result = detect_metric(50.0, history, method="auto")

    assert result["is_anomaly"] is True
    assert isinstance(result["score"], (int, float))
    assert isinstance(result["method"], str)
    assert isinstance(result["reason"], str)


def test_auto_uses_same_segment_history_to_avoid_seasonal_false_positive():
    # Global history is mostly weekday traffic around 1000; this segment
    # (e.g. Sunday) is normally around 300.
    global_history = [1000.0] * 30 + [290.0, 310.0]
    same_segment = [290.0, 300.0, 305.0, 295.0, 302.0, 298.0, 301.0]

    result = detect_metric(
        304.0,
        global_history,
        method="auto",
        context={
            "metric_name": "row_count",
            "day_of_week": 6,
            "same_segment_history": same_segment,
            "known_event": None,
        },
    )

    assert result["is_anomaly"] is False


def test_auto_uses_same_segment_history_to_catch_seasonal_anomaly():
    # 1000 is common globally, but grossly abnormal for this segment.
    global_history = [1000.0] * 30 + [290.0, 300.0, 310.0, 295.0, 305.0, 300.0]
    same_segment = [290.0, 300.0, 310.0, 295.0, 305.0, 300.0, 302.0]

    result = detect_metric(
        1000.0,
        global_history,
        method="auto",
        context={
            "metric_name": "row_count",
            "day_of_week": 6,
            "same_segment_history": same_segment,
            "known_event": None,
        },
    )

    assert result["is_anomaly"] is True


def test_mad_zero_baseline_still_detects_change():
    # Median absolute deviation is zero for a perfectly flat baseline.
    # A changed current value must not be treated as healthy just because MAD=0.
    result = detect_metric(80.0, [100.0] * 10, method="mad")

    assert result["is_anomaly"] is True


# ---------------------------------------------------------------------------
# Distribution drift
# ---------------------------------------------------------------------------

def test_same_mean_but_different_shape_is_distribution_shift():
    # Both means are exactly 10. A mean-ratio detector cannot see this shift.
    baseline = [9.0, 10.0, 11.0] * 50
    current = [0.0, 10.0, 20.0] * 50

    result = detect_distribution(current, baseline)

    assert result["is_anomaly"] is True


def test_identical_distribution_is_not_shift():
    baseline = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
    current = list(reversed(baseline))

    result = detect_distribution(current, baseline)

    assert result["is_anomaly"] is False


# ---------------------------------------------------------------------------
# SLO / burn rate
# ---------------------------------------------------------------------------

def test_exact_error_budget_boundary_is_not_breached():
    result = slo_status(0.99, bad_events=1, total_events=100)

    assert result["actual_bad_rate"] == pytest.approx(0.01)
    assert result["allowed_bad_rate"] == pytest.approx(0.01)
    assert result["burn_rate"] == pytest.approx(1.0)
    assert result["remaining_error_budget_fraction"] == pytest.approx(0.0)
    assert result["breached"] is False


def test_multiwindow_transient_spike_does_not_page():
    # High short-window burn but low long-window burn = transient spike.
    result = multiwindow_burn(short_window_burn=20.0, long_window_burn=2.0)

    assert result["page"] is False
    assert isinstance(result["severity"], str)
    assert isinstance(result["reason"], str)


def test_multiwindow_sustained_fast_burn_pages():
    # Both windows are well above Google's 14.4x page threshold example.
    result = multiwindow_burn(short_window_burn=20.0, long_window_burn=20.0)

    assert result["page"] is True
    assert isinstance(result["severity"], str)
    assert result["severity"].lower() not in {"info", "ok", "none"}


# ---------------------------------------------------------------------------
# Column lineage
# ---------------------------------------------------------------------------

def test_column_lineage_is_transitive():
    graph = {
        "raw_orders.amount": ["stg_orders.amount"],
        "stg_orders.amount": ["fct_daily_revenue.revenue"],
        "fct_daily_revenue.revenue": ["ceo_dashboard.revenue"],
    }

    result = column_downstream(graph, "raw_orders.amount")

    assert result == [
        "stg_orders.amount",
        "fct_daily_revenue.revenue",
        "ceo_dashboard.revenue",
    ]


def test_column_lineage_handles_cycles_without_duplicates_or_start_node():
    graph = {
        "a.x": ["b.x", "c.x"],
        "b.x": ["c.x"],
        "c.x": ["a.x", "d.x"],
        "d.x": [],
    }

    result = column_downstream(graph, "a.x")

    assert result == ["b.x", "c.x", "d.x"]
    assert "a.x" not in result
    assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# RAG embedding drift
# ---------------------------------------------------------------------------

def test_large_embedding_norm_shift_is_detected():
    baseline = [0.98, 1.01, 1.00, 1.02, 0.99, 1.01, 1.00]
    current = [1.90, 2.00, 2.10, 1.95, 2.05, 2.00]

    result = rag_embedding_shift(current, baseline)

    assert result["is_anomaly"] is True
    assert isinstance(result["score"], (int, float))
    assert isinstance(result["method"], str)


def test_stable_embedding_norms_do_not_alert():
    baseline = [0.98, 1.01, 1.00, 1.02, 0.99, 1.01, 1.00]
    current = [1.00, 0.99, 1.02, 1.01, 0.98, 1.00]

    result = rag_embedding_shift(current, baseline)

    assert result["is_anomaly"] is False
