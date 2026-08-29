from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

from student_api import validate_orders

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "orders_contract.yaml"


def healthy_df():
    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return pd.DataFrame([
        {
            "order_id": 1,
            "customer_id": "C1",
            "amount": 10.0,
            "currency": "USD",
            "status": "completed",
            "created_at": t1,
            "updated_at": t2,
        },
        {
            "order_id": 2,
            "customer_id": "C2",
            "amount": 20.0,
            "currency": "USD",
            "status": "pending",
            "created_at": t1,
            "updated_at": t2,
        },
    ])


def failed(issues):
    return [i for i in issues if not i["passed"]]


def test_healthy_contract_passes_starter_checks():
    assert not failed(validate_orders(healthy_df(), CONTRACT))


def test_duplicate_order_id_is_detected():
    df = healthy_df()
    df.loc[1, "order_id"] = 1
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "unique" and i["column"] == "order_id" for i in issues)


def test_invalid_currency_is_detected():
    df = healthy_df()
    df.loc[0, "currency"] = "BTC"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "accepted_values" and i["column"] == "currency" for i in issues)


def test_type_drift_is_detected():
    df = healthy_df()
    df.loc[0, "amount"] = "not_a_number"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "type" and i["column"] == "amount" for i in issues)


def test_freshness_delay_is_detected():
    df = healthy_df()
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    df["updated_at"] = old_time
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "freshness" and i["column"] == "updated_at" for i in issues)

