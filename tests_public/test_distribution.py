from student_api import detect_distribution


def test_extreme_mean_shift_detected():
    baseline = [9, 10, 11, 10, 10]
    current = [190, 200, 210, 205]
    assert detect_distribution(current, baseline)["is_anomaly"] is True


def test_near_zero_mean_does_not_trigger_false_positive():
    baseline = [-1.0, 0.0, 1.0] * 100
    current = [-0.999, 0.001, 1.001] * 100
    assert detect_distribution(current, baseline)["is_anomaly"] is False

