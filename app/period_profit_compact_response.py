from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite


def compact_period_profit_result(result):
    """Return a compact Telegram presentation without changing financial facts."""
    if not isinstance(result, dict):
        return result
    if result.get("error") is not False:
        return result
    if result.get("status") != "PERIOD_PROFIT_QUERY_READY":
        return result

    summary = result.get("summary")
    if not isinstance(summary, dict):
        return result

    required = (
        "date_from",
        "date_to",
        "revenue",
        "net_accrual",
        "product_cost",
        "tax",
        "profit",
        "margin_percent",
    )
    if any(summary.get(field) is None for field in required):
        return result

    output = deepcopy(result)
    original_text = output.get("text")
    if isinstance(original_text, str) and original_text.strip():
        output["details_text"] = original_text

    displayed_profit = summary.get("profit")
    displayed_margin = summary.get("margin_percent")
    external_line = None
    external_evidence = output.get("external_expense_evidence")
    external_adjustment = output.get("external_expense_adjustment")

    if (
        isinstance(external_evidence, dict)
        and external_evidence.get("coverage_complete") is True
        and isinstance(external_adjustment, dict)
        and external_adjustment.get("profit_adjustment_complete") is True
        and external_adjustment.get("complete_profit_after_external_expenses") is not None
        and external_adjustment.get("complete_margin_percent") is not None
    ):
        displayed_profit = external_adjustment.get(
            "complete_profit_after_external_expenses"
        )
        displayed_margin = external_adjustment.get(
            "complete_margin_percent"
        )
        external_total = external_evidence.get("observed_expense_total")
        if _finite_number(external_total) is not None:
            external_line = (
                "Внешние расходы: "
                + _money(external_total)
            )

    lines = [
        "💰 Прибыль за период "
        + _period(summary.get("date_from"), summary.get("date_to")),
        "",
        "Выручка: " + _money(summary.get("revenue")),
        "Продано SKU: " + _units(summary.get("units_sold")),
        "Начисления Ozon: " + _money(summary.get("net_accrual")),
        "Себестоимость: " + _money(summary.get("product_cost")),
        "Налог: " + _money(summary.get("tax")),
    ]

    if external_line is not None:
        lines.append(external_line)

    lines.extend([
        "",
        "Прибыль: " + _money(displayed_profit),
        "Маржа: " + _percent(displayed_margin),
    ])

    comparison_line = _comparison_line(output.get("comparison"))
    if comparison_line is not None:
        lines.extend(["", comparison_line])

    diagnostic_lines = _revenue_diagnostic_lines(summary.get("revenue_diagnostics"))
    if diagnostic_lines:
        lines.append("")
        lines.extend(diagnostic_lines)

    warnings = _warnings(output)
    if warnings:
        lines.append("")
        lines.extend(warnings)

    output["text"] = "\n".join(lines)
    output["presentation"] = "compact"
    output["read_only"] = True
    output["executed"] = False
    return output


def _revenue_diagnostic_lines(diagnostics):
    if not isinstance(diagnostics, dict):
        return []

    fields = diagnostics.get("fields")
    if not isinstance(fields, dict):
        return []

    lines = ["🔎 Диагностика выручки Ozon:"]
    for field in (
        "sale_amount",
        "seller_price",
        "sale_price",
        "bonus",
        "coinvestment",
    ):
        item = fields.get(field)
        if not isinstance(item, dict):
            lines.append(field + ": —")
            continue

        if item.get("complete") is True:
            lines.append(field + ": " + _money(item.get("amount")))
            continue

        observed = _money(item.get("observed_amount"))
        missing = item.get("missing_records")
        if isinstance(missing, int) and not isinstance(missing, bool) and missing >= 0:
            lines.append(
                field
                + ": "
                + observed
                + " (частично; пропусков: "
                + str(missing)
                + ")"
            )
        else:
            lines.append(field + ": — (неполные данные)")

    missing_days = diagnostics.get("missing_days")
    if isinstance(missing_days, int) and not isinstance(missing_days, bool) and missing_days > 0:
        lines.append("Диагностика неполна по дням: " + str(missing_days))
    return lines


def _warnings(result):
    warnings = []
    external = result.get("external_expense_evidence")
    if isinstance(external, dict):
        if external.get("error") is True:
            warnings.append(
                "⚠️ Внешние расходы недоступны и не считаются нулём."
            )
        elif (
            external.get("status")
            in {
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
            }
            and external.get("coverage_complete") is not True
        ):
            warnings.append(
                "⚠️ Внешние расходы учтены не полностью."
            )

    return_cogs = result.get("return_cogs_recovery_evidence")
    if isinstance(return_cogs, dict):
        unresolved = _non_negative_int(return_cogs.get("unresolved_units"))
        if unresolved:
            warnings.append(
                "Есть "
                + str(unresolved)
                + " возврата с неподтверждённым восстановлением себестоимости."
            )

    return warnings


def _comparison_line(comparison):
    if not isinstance(comparison, dict):
        return None
    if comparison.get("status") != "PERIOD_PROFIT_COMPARISON_READY":
        return None

    value = _finite_number(comparison.get("profit_change"))
    if value is None:
        return None

    if value > 0:
        icon = "📈"
        sign = "+"
    elif value < 0:
        icon = "📉"
        sign = "−"
    else:
        icon = "➡️"
        sign = ""

    return (
        icon
        + " К прошлому периоду: "
        + sign
        + _money(abs(value))
    )


def _period(date_from, date_to):
    start = _date(date_from)
    end = _date(date_to)
    if start is None or end is None:
        return f"{date_from} — {date_to}"
    if start.year == end.year:
        return f"{start:%d.%m}–{end:%d.%m}"
    return f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"


def _date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _money(value):
    number = _finite_number(value)
    if number is None:
        return "—"
    try:
        rounded = Decimal(str(number)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError):
        return "—"
    integer = int(rounded)
    return f"{integer:,}".replace(",", " ") + " ₽"


def _units(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "—"
    return f"{value:,}".replace(",", " ") + " шт."


def _percent(value):
    number = _finite_number(value)
    if number is None:
        return "—"
    return f"{number:.2f}%".replace(".", ",")


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _non_negative_int(value):
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if number > 0 else 0
