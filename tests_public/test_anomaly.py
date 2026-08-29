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



def test_zero_mad_small_float_noise_is_not_anomaly():
    history = [100.0] * 20
    result = detect_metric(100.0001, history, method="mad")
    assert result["is_anomaly"] is False

