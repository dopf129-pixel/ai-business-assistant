from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_finance_service import PeriodProfitFinanceService


class _Query:
    def __init__(self, result):
        self.result = result

    def query(self, **kwargs):
        return dict(self.result)


def test_prefetch_preserves_safe_http_status_without_ozon_payload():
    result = PeriodProfitFinanceService._prefetch_response_error({
        "error": True,
        "status_code": 429,
        "message": "sensitive upstream detail",
    })

    assert result == {
        "error": True,
        "code": "PERIOD_PROFIT_FINANCE_PREFETCH_HTTP_429",
        "read_only": True,
        "executed": False,
    }


def test_prefetch_preserves_existing_safe_code():
    result = PeriodProfitFinanceService._prefetch_response_error({
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "payload": {"must_not": "escape"},
    })

    assert result["code"] == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"
    assert "payload" not in result


def test_telegram_period_profit_exposes_only_safe_finance_diagnostic_code():
    runtime = AssistantPeriodProfitRuntimeService(_Query({
        "error": True,
        "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
        "code": "PERIOD_PROFIT_FINANCE_PREFETCH_HTTP_403",
        "message": "upstream secret detail",
    }))

    result = runtime.handle_callback("period_profit:7D")

    assert result["message"] == (
        "Финансовые данные Ozon недоступны\n"
        "Код диагностики: PERIOD_PROFIT_FINANCE_PREFETCH_HTTP_403"
    )
    assert result["finance_diagnostic_code"] == (
        "PERIOD_PROFIT_FINANCE_PREFETCH_HTTP_403"
    )
    assert "secret" not in result["message"]
    assert result["read_only"] is True
    assert result["executed"] is False

def test_money_validation_stage_survives_production_error_wiring():
    source = {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "finance_diagnostic_code": (
            "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE_TOTAL_AMOUNT"
        ),
        "complete": False,
    }
    prefetch = PeriodProfitFinanceService._prefetch_response_error(source)
    assert prefetch["finance_diagnostic_code"] == (
        "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE_TOTAL_AMOUNT"
    )

    runtime = AssistantPeriodProfitRuntimeService(_Query({
        "error": True,
        "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
        **prefetch,
    }))
    result = runtime.handle_callback("period_profit:7D")

    assert result["message"].endswith(
        "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE_TOTAL_AMOUNT"
    )
    assert result["read_only"] is True
    assert result["executed"] is False


def test_sku_identity_stage_survives_production_telegram_wiring():
    runtime = AssistantPeriodProfitRuntimeService(_Query({
        "error": True,
        "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
        "code": "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
        "finance_diagnostic_code": (
            "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_API_ERROR"
        ),
        "message": "must not escape",
        "read_only": True,
        "executed": False,
    }))

    result = runtime.handle_callback("period_profit:90D")

    assert result["message"].startswith(
        "Операции Ozon найдены, но не все исторические SKU"
    )
    assert "По выбранному SKU" in result["message"]
    assert result["message"].endswith(
        "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_API_ERROR"
    )
    assert "must not escape" not in result["message"]
    assert result["read_only"] is True
    assert result["executed"] is False


def test_multiple_identity_blockers_show_safe_unresolved_skus():
    runtime = AssistantPeriodProfitRuntimeService(_Query({
        "error": True,
        "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
        "code": "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
        "finance_diagnostic_code": (
            "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_MULTIPLE_BLOCKERS"
        ),
        "unresolved_finance_skus": ["OLD-1", "OLD-2"],
        "unresolved_finance_sku_count": 2,
        "finance_identity_blockers": [
            "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_TARGET_MISSING",
            "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_POSTING_OFFER_MISSING",
        ],
    }))

    result = runtime.handle_callback("period_profit:28D")

    assert "SKU без подтверждённой связи: OLD-1, OLD-2" in result["message"]
    assert "API" not in result["message"]
    assert "secret" not in result["message"].lower()
