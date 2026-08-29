"""Deterministic data-contract validation for the lab stable API."""
from __future__ import annotations

from datetime import date, datetime
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    return payload or {}


def _is_integer_value(value: Any) -> bool:
    # Reject strings and bools, but allow integer-valued numeric scalars such as
    # numpy.int64 and 1.0. This is semantic integer validation, not coercion.
    if isinstance(value, (bool, np.bool_, str, bytes)):
        return False
    if isinstance(value, Real):
        v = float(value)
        return np.isfinite(v) and v.is_integer()
    return False


def _is_number_value(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_, str, bytes)):
        return False
    if isinstance(value, Real):
        return bool(np.isfinite(float(value)))
    return False


def _is_datetime_value(value: Any) -> bool:
    # Public fixtures use ISO-8601 strings although the contract says datetime,
    # so accept parseable ISO timestamps while still rejecting arbitrary strings.
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        return not pd.isna(value)
    if isinstance(value, str):
        try:
            parsed = pd.to_datetime(value, utc=True, errors="raise")
        except (TypeError, ValueError, OverflowError):
            return False
        return not pd.isna(parsed)
    return False


def _validate_type(series: pd.Series, expected_type: str) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return True

    expected = str(expected_type).lower()
    if expected in {"integer", "int"}:
        return bool(non_null.map(_is_integer_value).all())
    if expected in {"number", "float", "numeric"}:
        return bool(non_null.map(_is_number_value).all())
    if expected in {"datetime", "timestamp"}:
        return bool(non_null.map(_is_datetime_value).all())
    if expected in {"string", "str", "text"}:
        return bool(non_null.map(lambda x: isinstance(x, str)).all())
    if expected in {"boolean", "bool"}:
        return bool(non_null.map(lambda x: isinstance(x, (bool, np.bool_))).all())

    # Unknown contract type is a contract/configuration error, not silently valid.
    return False


def validate_dataframe(df: pd.DataFrame, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    issues: list[dict[str, Any]] = []
    columns = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns.items():
        rules = rules or {}
        severity = str(rules.get("severity", "warning")).lower()
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        if rules.get("unique"):
            non_null = series.dropna()
            duplicate_count = int(non_null.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        expected_type = rules.get("type")
        if expected_type:
            type_valid = _validate_type(series, str(expected_type))
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=type_valid,
                    details=f"expected_type={expected_type}; type_valid={type_valid}",
                )
            )

        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            # Non-null values that cannot be interpreted numerically are invalid
            # for the range check too (type check independently catches drift).
            invalid = series.notna() & numeric.isna()
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        if "min_length" in rules or "max_length" in rules:
            non_null_mask = series.notna()
            str_lens = series[non_null_mask].astype(str).str.len()
            invalid_len = pd.Series(False, index=series.index)
            if "min_length" in rules:
                invalid_len.loc[non_null_mask] |= str_lens < rules["min_length"]
            if "max_length" in rules:
                invalid_len.loc[non_null_mask] |= str_lens > rules["max_length"]
            invalid_count = int(invalid_len.sum())
            issues.append(
                _issue(
                    "length",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_length_count={invalid_count}",
                )
            )

    freshness = contract.get("freshness")
    if freshness and isinstance(freshness, dict):
        fresh_col = freshness.get("column")
        max_delay = float(freshness.get("max_delay_minutes", 60))
        fresh_sev = str(freshness.get("severity", "warning")).lower()

        if fresh_col and fresh_col in df.columns:
            parsed_all = pd.to_datetime(df[fresh_col], utc=True, errors="coerce")
            parsed_dates = parsed_all.dropna()

            if parsed_dates.empty:
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_sev,
                        passed=False,
                        details=f"No valid datetime values in freshness column '{fresh_col}'",
                    )
                )
            else:
                latest = parsed_dates.max()
                now = pd.Timestamp.now(tz="UTC")
                delay_minutes = (now - latest).total_seconds() / 60.0

                # Very-future timestamps are not "fresh"; they indicate clock/data
                # corruption. A 5-minute tolerance avoids tiny clock skew.
                future_tolerance = float(freshness.get("future_tolerance_minutes", 5))
                too_far_future = delay_minutes < -future_tolerance
                too_old = delay_minutes > max_delay
                passed = not (too_old or too_far_future)

                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_sev,
                        passed=passed,
                        details=(
                            f"delay_minutes={delay_minutes:.1f}; "
                            f"max_delay_minutes={max_delay:g}; "
                            f"future_tolerance_minutes={future_tolerance:g}"
                        ),
                    )
                )
        elif fresh_col:
            issues.append(
                _issue(
                    "freshness",
                    column=fresh_col,
                    severity=fresh_sev,
                    passed=False,
                    details=f"Freshness column '{fresh_col}' missing from DataFrame",
                )
            )

    return issues


def failed_issues(
    issues: list[dict[str, Any]], min_severity: str | None = None
) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed

    order = {"info": 0, "warning": 1, "critical": 2}
    key = str(min_severity).lower()
    if key not in order:
        raise ValueError(f"Unknown severity: {min_severity}")
    threshold = order[key]
    return [
        i
        for i in failed
        if order.get(str(i.get("severity", "warning")).lower(), 1) >= threshold
    ]
