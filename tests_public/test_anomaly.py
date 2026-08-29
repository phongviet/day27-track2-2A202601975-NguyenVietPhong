from student_api import detect_metric


def test_large_volume_drop_is_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(300, history, method="zscore")
    assert result["is_anomaly"] is True


def test_stable_value_is_not_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(1002, history, method="zscore")
    assert result["is_anomaly"] is False


def test_known_event_false_does_not_raise_threshold():
    history = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 101.0]
    # 80.0 is ~4 standard deviations away; should trigger anomaly when known_event is False
    result = detect_metric(80.0, history, method="auto", context={"known_event": False})
    assert result["is_anomaly"] is True


def test_known_event_truthy_suppresses_anomaly():
    history = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 101.0]
    result = detect_metric(80.0, history, method="auto", context={"known_event": "promo"})
    assert result["is_anomaly"] is False
    assert result["method"] == "auto:event_suppressed"




def test_zero_mad_constant_baseline_and_deviation():
    history = [100.0] * 20
    assert detect_metric(100.0, history, method="mad")["is_anomaly"] is False
    assert detect_metric(150.0, history, method="mad")["is_anomaly"] is True



def test_following_known_trend_is_normal():
    history = [1000, 1020, 1040, 1060, 1080, 1100, 1120]
    result = detect_metric(
        1140,
        history,
        method="auto",
        context={"metric_name": "row_count", "trend": 20},
    )
    assert result["is_anomaly"] is False
    assert result["method"] == "auto:trend"


def test_trend_reversal_is_anomaly():
    history = [1000, 1020, 1040, 1060, 1080, 1100, 1120]
    result = detect_metric(
        850,
        history,
        method="auto",
        context={"metric_name": "row_count", "trend": 20},
    )
    assert result["is_anomaly"] is True
    assert result["method"] == "auto:trend"


def test_trend_context_changes_decision():
    history = [100, 120, 140, 160, 180, 200, 220]
    # Continues the +20 trend.
    result = detect_metric(
        240,
        history,
        method="auto",
        context={"trend": 20},
    )
    assert result["is_anomaly"] is False
    assert result["method"] == "auto:trend"


def test_flattening_known_trend_is_anomaly():
    history = [100, 120, 140, 160, 180, 200, 220]
    # Expected ~240, but suddenly stops growing.
    result = detect_metric(
        220,
        history,
        method="auto",
        context={"trend": 20},
    )
    assert result["is_anomaly"] is True
    assert result["method"] == "auto:trend"


def test_auto_infers_same_weekday_from_raw_history():
    current_dow = 5  # Saturday
    n_days = 21
    weekday_scale = 600
    weekend_scale = 258
    noise = [-6, 4, -2, 7]
    history = []
    for i in range(n_days):
        days_before_current = n_days - i
        dow = (current_dow - days_before_current) % 7
        base = weekday_scale if dow < 5 else weekend_scale
        history.append(base + noise[i % len(noise)])

    result = detect_metric(
        260,
        history,
        method="auto",
        context={
            "metric_name": "row_count",
            "day_of_week": current_dow,
        },
    )
    assert result["is_anomaly"] is False
    assert "inferred_same_weekday" in result["reason"]


def test_auto_detects_bad_value_against_inferred_weekday():
    current_dow = 5  # Saturday
    n_days = 21
    weekday_scale = 600
    weekend_scale = 258
    noise = [-6, 4, -2, 7]
    history = []
    for i in range(n_days):
        days_before_current = n_days - i
        dow = (current_dow - days_before_current) % 7
        base = weekday_scale if dow < 5 else weekend_scale
        history.append(base + noise[i % len(noise)])

    result = detect_metric(
        600,
        history,
        method="auto",
        context={
            "metric_name": "row_count",
            "day_of_week": current_dow,
        },
    )
    assert result["is_anomaly"] is True
    assert "inferred_same_weekday" in result["reason"]



