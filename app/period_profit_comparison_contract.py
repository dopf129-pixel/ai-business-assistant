"""Normalized, read-only contract for two finalized store-profit periods."""

from datetime import date, datetime, timezone
from decimal import Decimal
from math import isfinite


SCHEMA_VERSION = 1
_TAX_MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}
_SCOPE_FLAGS = (
    "returns_included",
    "advertising_included",
    "storage_included",
)
_SUMMARY_METRICS = (
    ("revenue", "RUB"),
    ("discount_points", "RUB"),
    ("revenue_tax_base", "RUB"),
    ("net_accrual", "RUB"),
    ("product_cost", "RUB"),
    ("tax", "RUB"),
    ("profit", "RUB"),
    ("margin_percent", "PERCENT"),
    ("units_sold", "UNIT"),
)


def build_period_profit_comparison_contract(
    current_result,
    previous_result,
    *,
    tenant_scope=None,
    generated_at=None,
):
    """Project two already-finalized results without recalculating finance facts."""
    timestamp = _timestamp(generated_at)
    if timestamp is None:
        return _error("PERIOD_PROFIT_COMPARISON_GENERATED_AT_INVALID")

    current = _normalize_result(current_result, tenant_scope, timestamp)
    if current is None:
        return _error("PERIOD_PROFIT_COMPARISON_CURRENT_RESULT_INVALID")
    previous = _normalize_result(previous_result, tenant_scope, timestamp)
    if previous is None:
        return _error("PERIOD_PROFIT_COMPARISON_PREVIOUS_RESULT_INVALID")

    reasons = _compatibility_reasons(current, previous)
    profit_ready = not reasons and _confirmed(current, "profit") and _confirmed(
        previous, "profit"
    )
    e_ready = (
        profit_ready
        and _confirmed(current, "profit_after_external_expenses")
        and _confirmed(previous, "profit_after_external_expenses")
    )
    return {
        "error": False,
        "status": "PERIOD_PROFIT_COMPARISON_CONTRACT_READY",
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "tenant_scope": _scope_value(tenant_scope),
            "owner_scope": None,
            "currency": "RUB",
            "result_type": "STORE_PERIOD_PROFIT",
        },
        "generated_at": timestamp,
        "current": current,
        "previous": previous,
        "profit_compatibility": {
            "status": "CONFIRMED" if profit_ready else "UNAVAILABLE",
            "reason_codes": reasons,
        },
        "profit_bases": {
            "B": _basis(
                current,
                previous,
                "profit",
                "CONFIRMED" if profit_ready else "UNAVAILABLE",
                reasons,
            ),
            "E": _basis(
                current,
                previous,
                "profit_after_external_expenses",
                "CONFIRMED" if e_ready else "UNAVAILABLE",
                reasons
                + (
                    []
                    if e_ready
                    else ["PERIOD_PROFIT_COMPARISON_EXTERNAL_COVERAGE_REQUIRED"]
                ),
            ),
        },
        "comparison_basis": "B",
        "read_only": True,
        "executed": False,
    }


def _normalize_result(result, tenant_scope, generated_at):
    if not isinstance(result, dict) or result.get("error") is not False:
        return None
    if result.get("status") != "PERIOD_PROFIT_QUERY_READY":
        return None
    summary = result.get("summary")
    if (
        not isinstance(summary, dict)
        or summary.get("error") is not False
        or summary.get("status") != "PERIOD_PROFIT_SUMMARY_READY"
    ):
        return None

    start = _iso_date(summary.get("date_from"))
    end = _iso_date(summary.get("date_to"))
    if start is None or end is None or start > end:
        return None
    request = result.get("request")
    if (
        not isinstance(request, dict)
        or request.get("status") != "PERIOD_PROFIT_REQUEST_READY"
        or request.get("date_from") != start.isoformat()
        or request.get("date_to") != end.isoformat()
    ):
        return None

    metrics = {
        name: _metric(summary.get(name), unit, "canonical_summary")
        for name, unit in _SUMMARY_METRICS
    }
    if metrics["units_sold"]["status"] == "CONFIRMED":
        units = metrics["units_sold"]["value"]
        if units < 0 or not units.is_integer():
            metrics["units_sold"] = _unknown_metric("UNIT", "canonical_summary")
        else:
            metrics["units_sold"]["value"] = int(units)

    applied = summary.get("return_cogs_profit_applied")
    application_amount = _finite_number(
        summary.get("return_cogs_profit_application_amount")
    )
    tax_recomputed = summary.get("return_cogs_profit_tax_recomputed")
    not_applied_confirmed = (
        applied is False
        and tax_recomputed is False
        and summary.get("return_cogs_profit_application_amount") is None
    )
    applied_confirmed = (
        applied is True
        and tax_recomputed is True
        and application_amount is not None
        and application_amount >= 0
    )
    if not_applied_confirmed:
        metrics["return_cogs_adjustment"] = _known_metric(
            0.0,
            "RUB",
            "final_return_cogs_application",
        )
    elif applied_confirmed:
        metrics["return_cogs_adjustment"] = _known_metric(
            application_amount,
            "RUB",
            "final_return_cogs_application",
        )
    else:
        metrics["return_cogs_adjustment"] = _unknown_metric(
            "RUB",
            "final_return_cogs_application",
        )
    if not (not_applied_confirmed or applied_confirmed):
        metrics["profit"] = _unknown_metric("RUB", "canonical_final_summary")

    external = _external_metrics(
        result.get("external_expense_evidence"),
        result.get("external_expense_adjustment"),
    )
    metrics.update(external)
    tax_policy = _tax_policy(summary)
    flags = {
        flag: summary.get(flag) if type(summary.get(flag)) is bool else None
        for flag in _SCOPE_FLAGS
    }
    coverage = result.get("coverage")
    coverage_summary = {
        "status": _coverage_status(coverage),
        "included_components": _component_names(
            coverage.get("included_components") if isinstance(coverage, dict) else None
        ),
        "missing_components": _component_names(
            coverage.get("missing_components") if isinstance(coverage, dict) else None
        ),
        "external_expenses": external["external_expenses"]["status"],
        "return_cogs_application": metrics["return_cogs_adjustment"]["status"],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "tenant_scope": _scope_value(tenant_scope),
            "owner_scope": None,
            "currency": "RUB",
            "result_type": "STORE_PERIOD_PROFIT",
        },
        "period": {
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "inclusive_days": (end - start).days + 1,
        },
        "generated_at": generated_at,
        "profit_scope": _text(summary.get("profit_scope")),
        "tax_policy": tax_policy,
        "metrics": metrics,
        "coverage": coverage_summary,
        "comparison_basis": "B",
        "component_scope": flags,
        "read_only": True,
        "executed": False,
    }


def _compatibility_reasons(current, previous):
    reasons = []
    current_days = current["period"]["inclusive_days"]
    previous_days = previous["period"]["inclusive_days"]
    if current_days != previous_days:
        reasons.append("PERIOD_PROFIT_COMPARISON_PERIOD_LENGTH_MISMATCH")
    try:
        if date.fromisoformat(previous["period"]["date_to"]).toordinal() + 1 != date.fromisoformat(
            current["period"]["date_from"]
        ).toordinal():
            reasons.append("PERIOD_PROFIT_COMPARISON_PERIODS_NOT_ADJACENT")
    except (TypeError, ValueError):
        reasons.append("PERIOD_PROFIT_COMPARISON_PERIOD_INVALID")

    if current.get("profit_scope") is None or previous.get("profit_scope") is None:
        reasons.append("PERIOD_PROFIT_COMPARISON_PROFIT_SCOPE_UNKNOWN")
    elif current["profit_scope"] != previous["profit_scope"]:
        reasons.append("PERIOD_PROFIT_COMPARISON_SCOPE_MISMATCH")

    if current["scope"]["tenant_scope"] != previous["scope"]["tenant_scope"]:
        reasons.append("PERIOD_PROFIT_COMPARISON_TENANT_MISMATCH")
    elif current["scope"]["tenant_scope"] is None:
        reasons.append("PERIOD_PROFIT_COMPARISON_TENANT_SCOPE_UNKNOWN")
    if current["scope"]["currency"] != previous["scope"]["currency"]:
        reasons.append("PERIOD_PROFIT_COMPARISON_CURRENCY_MISMATCH")

    if any(
        current["component_scope"].get(flag) is None
        or previous["component_scope"].get(flag) is None
        for flag in _SCOPE_FLAGS
    ):
        reasons.append("PERIOD_PROFIT_COMPARISON_COMPONENT_SCOPE_UNKNOWN")
    elif current["component_scope"] != previous["component_scope"]:
        reasons.append("PERIOD_PROFIT_COMPARISON_COMPONENT_SCOPE_MISMATCH")

    current_policy = current["tax_policy"]
    previous_policy = previous["tax_policy"]
    if current_policy["status"] != "CONFIRMED" or previous_policy["status"] != "CONFIRMED":
        reasons.append("PERIOD_PROFIT_COMPARISON_TAX_POLICY_UNKNOWN")
    elif any(
        current_policy.get(field) != previous_policy.get(field)
        for field in (
            "mode",
            "rate_percent",
            "minimum_tax_rate_percent",
            "minimum_rate_applicable",
        )
    ):
        reasons.append("PERIOD_PROFIT_COMPARISON_TAX_POLICY_MISMATCH")

    if not _confirmed(current, "profit") or not _confirmed(previous, "profit"):
        reasons.append("PERIOD_PROFIT_COMPARISON_PROFIT_UNAVAILABLE")
    if (
        current["metrics"]["return_cogs_adjustment"]["status"] != "CONFIRMED"
        or previous["metrics"]["return_cogs_adjustment"]["status"] != "CONFIRMED"
    ):
        reasons.append("PERIOD_PROFIT_COMPARISON_FINAL_RESULT_UNCONFIRMED")
    return list(dict.fromkeys(reasons))


def _tax_policy(summary):
    mode = _text(summary.get("tax_mode") or summary.get("tax_policy_mode"))
    rate = _finite_number(summary.get("tax_rate_percent"))
    minimum_applicable = mode == "USN_INCOME_MINUS_EXPENSES"
    minimum_rate = (
        _finite_number(summary.get("minimum_tax_rate_percent"))
        if minimum_applicable
        else None
    )
    known = mode in _TAX_MODES
    if mode == "NONE":
        known = known and rate is not None and rate == 0
    elif mode == "USN_INCOME":
        known = known and rate is not None and 0 <= rate <= 100
    elif mode == "USN_INCOME_MINUS_EXPENSES":
        known = (
            known
            and rate is not None
            and 0 <= rate <= 100
            and minimum_rate is not None
            and 0 <= minimum_rate <= 100
        )
    return {
        "status": "CONFIRMED" if known else "UNKNOWN",
        "mode": mode if known else None,
        "rate_percent": rate if known else None,
        "minimum_tax_rate_percent": minimum_rate if known else None,
        "minimum_rate_applicable": minimum_applicable if known else None,
        "source": "canonical_summary",
    }


def _external_metrics(evidence, adjustment):
    evidence = evidence if isinstance(evidence, dict) else None
    adjustment = adjustment if isinstance(adjustment, dict) else None
    status = "UNKNOWN"
    expense_value = None
    if evidence is not None:
        if evidence.get("error") is True:
            status = "UNAVAILABLE"
        elif (
            evidence.get("error") is False
            and evidence.get("status")
            in {
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
            }
        ):
            complete = evidence.get("coverage_complete") is True
            raw_total = (
                evidence.get("complete_expense_total")
                if complete
                else evidence.get("observed_expense_total")
            )
            expense_value = _finite_number(raw_total)
            status = (
                "CONFIRMED"
                if complete and expense_value is not None
                else "PARTIAL"
                if expense_value is not None
                else "UNKNOWN"
            )

    expense_metric = {
        "value": expense_value,
        "unit": "RUB",
        "status": status,
        "source": "external_expense_evidence",
    }
    after_profit = _unknown_metric("RUB", "external_expense_adjustment")
    after_margin = _unknown_metric("PERCENT", "external_expense_adjustment")
    if adjustment is not None and adjustment.get("error") is False:
        complete = adjustment.get("profit_adjustment_complete") is True
        profit_value = _finite_number(
            adjustment.get(
                "complete_profit_after_external_expenses"
                if complete
                else "observed_profit_after_external_expenses"
            )
        )
        margin_value = _finite_number(
            adjustment.get(
                "complete_margin_percent"
                if complete
                else "observed_margin_percent"
            )
        )
        if profit_value is not None and margin_value is not None:
            adjustment_status = (
                "CONFIRMED"
                if complete and status == "CONFIRMED"
                else "PARTIAL"
                if status == "PARTIAL"
                else "UNKNOWN"
            )
            after_profit = _known_metric(
                profit_value,
                "RUB",
                "external_expense_adjustment",
                adjustment_status,
            )
            after_margin = _known_metric(
                margin_value,
                "PERCENT",
                "external_expense_adjustment",
                adjustment_status,
            )
    if status == "UNAVAILABLE":
        after_profit["status"] = "UNAVAILABLE"
        after_margin["status"] = "UNAVAILABLE"
    return {
        "external_expenses": expense_metric,
        "profit_after_external_expenses": after_profit,
        "margin_after_external_expenses": after_margin,
    }


def _basis(current, previous, metric_name, status, reason_codes):
    return {
        "status": status,
        "current_value": current["metrics"][metric_name]["value"],
        "current_status": current["metrics"][metric_name]["status"],
        "previous_value": previous["metrics"][metric_name]["value"],
        "previous_status": previous["metrics"][metric_name]["status"],
        "unit": current["metrics"][metric_name]["unit"],
        "reason_codes": list(reason_codes),
    }


def _metric(value, unit, source):
    number = _finite_number(value)
    return (
        _known_metric(number, unit, source)
        if number is not None
        else _unknown_metric(unit, source)
    )


def _known_metric(value, unit, source, status="CONFIRMED"):
    return {"value": value, "unit": unit, "status": status, "source": source}


def _unknown_metric(unit, source):
    return {"value": None, "unit": unit, "status": "UNKNOWN", "source": source}


def _confirmed(period, metric_name):
    return period["metrics"][metric_name]["status"] == "CONFIRMED"


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _iso_date(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _timestamp(value):
    if value is None:
        value = datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    try:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, ValueError):
        return None


def _scope_value(value):
    return value if isinstance(value, str) and value else None


def _coverage_status(coverage):
    if not isinstance(coverage, dict):
        return "UNKNOWN"
    status = coverage.get("coverage_status")
    return status if status in {"COMPLETE", "PARTIAL"} else "UNKNOWN"


def _component_names(value):
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value[:20]
        if isinstance(item, str) and 0 < len(item) <= 64
    ]


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_COMPARISON_CONTRACT_UNAVAILABLE",
        "read_only": True,
        "executed": False,
    }
