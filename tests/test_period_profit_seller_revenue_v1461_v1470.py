from api.period_profit_ozon_client import PeriodProfitOzonClient
from services.finance_service import FinanceService


def _finance_result(seller_price="90.00", sale_amount="110.00"):
    return {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "total_amount": {"amount": "55.00"},
                "posting": {
                    "products": [
                        {
                            "sku": "123",
                            "commission": {
                                "seller_price": {"amount": seller_price},
                                "sale_amount": {"amount": sale_amount},
                                "sale_commission": {"amount": "-10.00"},
                                "bonus": {"amount": "20.00"},
                                "coinvestment": {"amount": "5.00"},
                            },
                        }
                    ]
                },
            }
        ],
    }


def test_period_profit_revenue_uses_seller_price_not_sale_amount():
    client = PeriodProfitOzonClient()
    raw = _finance_result()

    normalized = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        raw,
    )

    commission = normalized["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "90.00"
    assert commission["bonus"]["amount"] == "20.00"
    assert commission["coinvestment"]["amount"] == "5.00"
    assert raw["accruals"][0]["posting"]["products"][0]["commission"]["sale_amount"]["amount"] == "110.00"


def test_finance_service_reads_normalized_seller_revenue_without_adding_bonus():
    client = PeriodProfitOzonClient()
    normalized = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        _finance_result(),
    )

    class FakeOzon:
        def get_accruals_by_day(self, accrual_date):
            return normalized

    service = FinanceService()
    service.ozon = FakeOzon()
    service.accrual_types = {999: {"name": "unused", "description": "unused"}}

    result = service.get_daily_account_finance("2026-08-09")

    assert result["error"] is False
    assert result["gross_sales"] == 90.0
    assert result["net_accrual"] == 55.0
    assert result["sales_count"] == 1


def test_missing_seller_price_fails_closed_without_sale_amount_fallback():
    client = PeriodProfitOzonClient()
    raw = _finance_result()
    del raw["accruals"][0]["posting"]["products"][0]["commission"]["seller_price"]

    result = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        raw,
    )

    assert result == {
        "error": True,
        "code": "FINANCE_SELLER_REVENUE_UNAVAILABLE",
        "complete": False,
    }


def test_invalid_seller_price_fails_closed():
    client = PeriodProfitOzonClient()

    result = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        _finance_result(seller_price="NaN"),
    )

    assert result["error"] is True
    assert result["code"] == "FINANCE_SELLER_REVENUE_UNAVAILABLE"


def test_explicit_zero_seller_price_is_valid_zero_not_unknown():
    client = PeriodProfitOzonClient()

    result = client._normalize_period_profit_revenue(
        client.FINANCE_ACCRUAL_BY_DAY,
        _finance_result(seller_price="0"),
    )

    commission = result["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "0"


def test_non_finance_endpoint_is_not_rewritten():
    client = PeriodProfitOzonClient()
    raw = _finance_result()

    result = client._normalize_period_profit_revenue("/v1/other/read", raw)

    assert result is raw
    assert result["accruals"][0]["posting"]["products"][0]["commission"]["sale_amount"]["amount"] == "110.00"
