from api.period_profit_ozon_client import PeriodProfitOzonClient
from period_profit_compact_response import compact_period_profit_result
from services.period_profit_revenue_diagnostics_summary_service import (
    PeriodProfitRevenueDiagnosticsSummaryService,
)


def _raw_finance():
    return {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "posting": {
                    "products": [
                        {
                            "sku": "123",
                            "commission": {
                                "sale_amount": {"amount": "110.00"},
                                "seller_price": {"amount": "90.00"},
                                "sale_price": {"amount": "80.00"},
                                "bonus": {"amount": "20.00"},
                                "coinvestment": {"amount": "5.00"},
                            },
                        }
                    ]
                },
            }
        ],
    }


def test_client_preserves_raw_fields_before_seller_price_normalization():
    client = PeriodProfitOzonClient()
    normalized = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        _raw_finance(),
    )

    commission = normalized["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "90.00"

    diagnostics = normalized["_period_profit_revenue_diagnostics"]
    assert diagnostics["record_count"] == 1
    assert diagnostics["fields"]["sale_amount"]["amount"] == "110.00"
    assert diagnostics["fields"]["seller_price"]["amount"] == "90.00"
    assert diagnostics["fields"]["sale_price"]["amount"] == "80.00"
    assert diagnostics["fields"]["bonus"]["amount"] == "20.00"
    assert diagnostics["fields"]["coinvestment"]["amount"] == "5.00"


def test_missing_diagnostic_field_is_unknown_not_zero():
    raw = _raw_finance()
    del raw["accruals"][0]["posting"]["products"][0]["commission"]["bonus"]

    client = PeriodProfitOzonClient()
    normalized = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        raw,
    )

    bonus = normalized["_period_profit_revenue_diagnostics"]["fields"]["bonus"]
    assert bonus["amount"] is None
    assert bonus["observed_amount"] == "0.00"
    assert bonus["complete"] is False
    assert bonus["missing_records"] == 1


class _BaseSummary:
    tax_rate = 0.06

    def calculate(self, date_from, date_to, products):
        return {
            "error": False,
            "date_from": date_from,
            "date_to": date_to,
            "revenue": 90.0,
            "net_accrual": 55.0,
            "product_cost": 20.0,
            "tax": 5.4,
            "profit": 29.6,
            "margin_percent": 32.89,
            "units_sold": 1,
            "products": [],
        }


class _Finance:
    def __init__(self, daily):
        self._daily_accrual_cache = daily


def test_summary_diagnostics_do_not_change_profit_fields():
    client = PeriodProfitOzonClient()
    normalized = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        _raw_finance(),
    )
    service = PeriodProfitRevenueDiagnosticsSummaryService(
        _BaseSummary(),
        _Finance({"2026-08-09": normalized}),
    )

    result = service.calculate("2026-08-09", "2026-08-09", [])

    assert result["revenue"] == 90.0
    assert result["profit"] == 29.6
    assert result["tax"] == 5.4
    assert result["revenue_diagnostics"]["fields"]["sale_amount"]["amount"] == 110.0
    assert result["revenue_diagnostics"]["fields"]["seller_price"]["amount"] == 90.0


def test_compact_response_shows_diagnostic_block_without_changing_financial_values():
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "summary": {
            "date_from": "2026-08-09",
            "date_to": "2026-08-09",
            "revenue": 90.0,
            "net_accrual": 55.0,
            "product_cost": 20.0,
            "tax": 5.4,
            "profit": 29.6,
            "margin_percent": 32.89,
            "units_sold": 1,
            "revenue_diagnostics": {
                "missing_days": 0,
                "fields": {
                    "sale_amount": {"amount": 110.0, "complete": True},
                    "seller_price": {"amount": 90.0, "complete": True},
                    "sale_price": {"amount": 80.0, "complete": True},
                    "bonus": {"amount": 20.0, "complete": True},
                    "coinvestment": {"amount": 5.0, "complete": True},
                },
            },
        },
        "read_only": True,
        "executed": False,
    }

    output = compact_period_profit_result(result)

    assert output["summary"]["revenue"] == 90.0
    assert output["summary"]["profit"] == 29.6
    assert "🔎 Диагностика выручки Ozon:" in output["text"]
    assert "sale_amount: 110 ₽" in output["text"]
    assert "seller_price: 90 ₽" in output["text"]
    assert "bonus: 20 ₽" in output["text"]
