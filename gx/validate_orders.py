#!/usr/bin/env python3
"""Small Great Expectations Core 1.21 example.

This file demonstrates the modern dataframe flow with a few expectations.
Students should extend it into a reusable Expectation Suite / Validation
Definition / Checkpoint and design actions based on severity.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:  # friendlier classroom failure
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def main() -> None:
    df = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")
    context = gx.get_context()

    # 1. Create Expectation Suite
    suite = context.suites.add(gx.ExpectationSuite(name="orders_suite"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0)
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="currency", value_set=["USD", "VND"]
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
        )
    )

    # 2. Connect Data Source & Asset
    data_source = context.data_sources.add_pandas("orders_pandas")
    asset = data_source.add_dataframe_asset(name="orders_dataframe")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_orders")

    # 3. Validation Definition & Checkpoint
    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="orders_validation",
            data=batch_definition,
            suite=suite,
        )
    )

    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="orders_checkpoint",
            validation_definitions=[validation_definition],
        )
    )

    checkpoint_result = checkpoint.run(
        batch_parameters={"dataframe": df}
    )

    all_ok = checkpoint_result.success
    print("=== GREAT EXPECTATIONS SUITE CHECKPOINT ===")
    print(f"Suite: {suite.name}")
    print(f"Total Expectations: {len(suite.expectations)}")
    print(f"Overall Result: {'PASS' if all_ok else 'FAIL'}")

    # Action / triage based on severity
    if not all_ok:
        print("[ACTION REQUIRED] Critical checks failed! Action: QUARANTINE / BLOCK PIPELINE.")
    else:
        print("[ACTION] Data healthy. Action: PROCEED TO DOWNSTREAM MODELS.")


if __name__ == "__main__":
    main()
