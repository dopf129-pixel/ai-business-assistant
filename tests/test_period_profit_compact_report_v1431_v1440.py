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
            "discount_points": 0.0,
            "revenue_tax_base": 454034.93,
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
        "Выручка: 454 034.93 ₽ (100,00% от общей выручки)\n"
        "Баллы за скидки: 0.00 ₽ (0,00% от общей выручки)\n"
        "Выручка для расчёта налога: 454 034.93 ₽ (100,00% от общей выручки)\n"
        "Продано SKU: 64 шт.\n"
        "Начисления Ozon: 175 004.50 ₽ (38,54% от общей выручки)\n"
        "Себестоимость: 121 212.00 ₽ (26,70% от общей выручки)\n"
        "Налог: 27 242.10 ₽ (6,00% от общей выручки)\n"
        "\n"
        "Прибыль после себестоимости: 26 550.40 ₽ (5,85% от общей выручки)\n"
        "Маржа: 5,85%\n"
        "\n"
        "📈 К прошлому периоду до внешних расходов: +56 147.79 ₽\n"
        "\n"
        "⚠️ Внешние расходы учтены не полностью.\n"
        "Есть 2 возврата Returns API со сменой статуса в периоде; "
        "восстановление себестоимости не подтверждено. "
        "Это не число финансовых «Возврат выручки»."
    )
    assert result["presentation"] == "compact"
    assert len(result["text"].encode("utf-16-le")) // 2 <= 2500
    assert result["read_only"] is True
    assert result["executed"] is False


def test_missing_units_sold_remains_unknown_not_zero():
    source = _result()
    source["summary"].pop("units_sold")

    result = compact_period_profit_result(source)

    assert "Продано SKU: —" in result["text"]
    assert "Продано SKU: 0 шт." not in result["text"]


def test_compact_report_preserves_negative_signs_and_handles_zero_revenue():
    source = _result()
    source["summary"].update({
        "revenue": 0,
        "revenue_tax_base": 0,
        "discount_points": 0,
        "net_accrual": -1234.56,
        "product_cost": 0,
        "tax": 0,
        "profit": -1234.56,
        "margin_percent": -1.25,
    })

    result = compact_period_profit_result(source)

    assert "Выручка: 0.00 ₽ (доля не определена: выручка ≤ 0)" in result["text"]
    assert "Начисления Ozon: -1 234.56 ₽ (доля не определена: выручка ≤ 0)" in result["text"]
    assert "Прибыль после себестоимости: -1 234.56 ₽ (доля не определена: выручка ≤ 0)" in result["text"]
    assert len(result["text"].encode("utf-16-le")) // 2 <= 2500


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

    assert "Внешние расходы: 1 550.40 ₽ (0,34% от общей выручки)" in result["text"]
    assert "Прибыль после себестоимости и внешних расходов: 25 000.00 ₽ (5,51% от общей выручки)" in result["text"]
    assert "Маржа: 5,51%" in result["text"]
    assert "⚠️" not in result["text"]


def test_adjusted_profit_is_not_labeled_with_base_profit_delta_as_same_basis():
    source = _result(
        comparison={
            "error": False,
            "status": "PERIOD_PROFIT_COMPARISON_READY",
            "profit_direction": "UP",
            "profit_change": 40,
            "profit_change_percent": 10,
        },
        external_expense_evidence={
            "error": False,
            "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "coverage_complete": True,
            "observed_expense_total": 100,
        },
        external_expense_adjustment={
            "error": False,
            "profit_adjustment_complete": True,
            "complete_profit_after_external_expenses": 340,
            "complete_margin_percent": 34,
        },
    )

    result = compact_period_profit_result(source)

    assert "Прибыль после себестоимости и внешних расходов: 340.00 ₽ (0,07% от общей выручки)" in result["text"]
    assert "К прошлому периоду до внешних расходов: +40.00 ₽" in result["text"]


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
