"""Simple contract validator used as the starter baseline.

The implementation intentionally covers only common deterministic checks.
Students are expected to extend it with:
- stronger type validation/coercion rules,
- freshness checks,
- cross-field/cross-table assertions,
- severity-aware actions (block/quarantine/warn),
- richer observability metadata.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

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
        return yaml.safe_load(f)


def validate_dataframe(df: pd.DataFrame, contract: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    columns = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns.items():
        severity = rules.get("severity", "warning")
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
            duplicate_count = int(series.duplicated(keep=False).sum())
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
            non_null = series.dropna()
            type_valid = True
            if len(non_null) > 0:
                if expected_type in ("integer", "int"):
                    coerced = pd.to_numeric(non_null, errors="coerce")
                    type_valid = coerced.notna().all() and (coerced % 1 == 0).all()
                elif expected_type in ("number", "float", "numeric"):
                    coerced = pd.to_numeric(non_null, errors="coerce")
                    type_valid = coerced.notna().all()
                elif expected_type in ("datetime", "timestamp"):
                    coerced = pd.to_datetime(non_null, errors="coerce", utc=True)
                    type_valid = coerced.notna().all()
                elif expected_type in ("string", "str", "text"):
                    type_valid = non_null.apply(lambda x: isinstance(x, str)).all()
                elif expected_type in ("boolean", "bool"):
                    type_valid = non_null.apply(
                        lambda x: isinstance(x, (bool, bool)) or str(x).lower() in ("true", "false", "0", "1")
                    ).all()

            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=bool(type_valid),
                    details=f"expected_type={expected_type}; type_valid={type_valid}",
                )
            )

        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
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
        max_delay = freshness.get("max_delay_minutes", 60)
        fresh_sev = freshness.get("severity", "warning")
        if fresh_col and fresh_col in df.columns:
            parsed_dates = pd.to_datetime(df[fresh_col], utc=True, errors="coerce").dropna()
            if len(parsed_dates) > 0:
                latest = parsed_dates.max()
                now = pd.Timestamp.now(tz="UTC")
                delay_minutes = max(0.0, (now - latest).total_seconds() / 60.0)
                passed = delay_minutes <= max_delay
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_sev,
                        passed=bool(passed),
                        details=f"delay_minutes={delay_minutes:.1f}; max_delay_minutes={max_delay}",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_sev,
                        passed=False,
                        details=f"No valid datetime values in freshness column '{fresh_col}'",
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


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order[min_severity]
    return [i for i in failed if order.get(i.get("severity", "warning"), 1) >= threshold]
