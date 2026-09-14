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
