from period_profit_compact_response import compact_period_profit_result
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)


def _result(**overrides):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "text": (
            "old verbose report\n"
            "Корректировка по итоговому кабинету Ozon\n"
            "Расшифровка удержаний Ozon"
        ),
        "summary": {
            "date_from": "2026-08-09",
            "date_to": "2026-09-05",
            "revenue": 454034.93,
            "units_sold": 64,
            "net_accrual": 175004.50,
            "product_cost": 121212.00,
            "tax": 27242.10,
            "profit": 26550.40,
            "margin_percent": 5.85,
        },
        "comparison": {
            "error": False,
            "status": "PERIOD_PROFIT_COMPARISON_READY",
            "profit_direction": "UP",
            "profit_change": 56147.79,
            "profit_change_percent": 189.71,
        },
        "external_expense_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
            "coverage_complete": False,
            "observed_expense_total": 0.0,
        },
        "return_cogs_recovery_evidence": {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
            "unresolved_units": 2,
        },
        "read_only": True,
        "executed": False,
    }
    result.update(overrides)
    return result


def test_compact_report_matches_approved_management_format():
    result = compact_period_profit_result(_result())

    assert result["text"] == (
        "💰 Прибыль за период 09.08–05.09\n"
        "\n"
        "Выручка: 454 035 ₽\n"
        "Продано SKU: 64 шт.\n"
        "Начисления Ozon: 175 005 ₽\n"
        "Себестоимость: 121 212 ₽\n"
        "Налог: 27 242 ₽\n"
        "\n"
        "Прибыль: 26 550 ₽\n"
        "Маржа: 5,85%\n"
        "\n"
        "📈 К прошлому периоду: +56 148 ₽\n"
        "\n"
        "⚠️ Внешние расходы учтены не полностью.\n"
        "Есть 2 возврата с неподтверждённым восстановлением себестоимости."
    )
    assert result["presentation"] == "compact"
    assert result["read_only"] is True
    assert result["executed"] is False


def test_missing_units_sold_remains_unknown_not_zero():
    source = _result()
    source["summary"].pop("units_sold")

    result = compact_period_profit_result(source)

    assert "Продано SKU: —" in result["text"]
    assert "Продано SKU: 0 шт." not in result["text"]


def test_verbose_report_is_preserved_as_details_not_main_text():
    result = compact_period_profit_result(_result())

    assert "Корректировка по итоговому кабинету Ozon" not in result["text"]
    assert "Расшифровка удержаний Ozon" not in result["text"]
    assert result["details_text"].startswith("old verbose report")


def test_complete_external_expenses_use_adjusted_profit_and_margin():
    source = _result(
        external_expense_evidence={
            "error": False,
            "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "coverage_complete": True,
            "observed_expense_total": 1550.40,
        },
        external_expense_adjustment={
            "error": False,
            "profit_adjustment_complete": True,
            "complete_profit_after_external_expenses": 25000.00,
            "complete_margin_percent": 5.51,
        },
        return_cogs_recovery_evidence={
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
            "unresolved_units": 0,
        },
    )

    result = compact_period_profit_result(source)

    assert "Внешние расходы: 1 550 ₽" in result["text"]
    assert "Прибыль: 25 000 ₽" in result["text"]
    assert "Маржа: 5,51%" in result["text"]
    assert "⚠️" not in result["text"]


def test_external_source_failure_remains_unknown_not_zero():
    source = _result(
        external_expense_evidence={"error": True},
        return_cogs_recovery_evidence=None,
    )

    result = compact_period_profit_result(source)

    assert "Внешние расходы: 0 ₽" not in result["text"]
    assert (
        "⚠️ Внешние расходы недоступны и не считаются нулём."
        in result["text"]
    )


def test_runtime_applies_compact_presentation_to_period_profit_only():
    class Query:
        def query(self, **kwargs):
            return _result()

    runtime = AssistantPeriodProfitRuntimeService(Query())
    result = runtime.handle_text("Прибыль за 28 дней", today="2026-09-05")

    assert result["presentation"] == "compact"
    assert result["text"].startswith("💰 Прибыль за период 09.08–05.09")
    assert "Продано SKU: 64 шт." in result["text"]
    assert result["details_text"].startswith("old verbose report")


def test_errors_pass_through_without_presentation_rewrite():
    source = {
        "error": True,
        "code": "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE",
        "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
    }

    assert compact_period_profit_result(source) == source
