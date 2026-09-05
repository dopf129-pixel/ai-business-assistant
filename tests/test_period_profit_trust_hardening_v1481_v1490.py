from api.period_profit_ozon_client import PeriodProfitOzonClient
from period_profit_compact_response import compact_period_profit_result


def _money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def _finance_response():
    return {
        "error": False,
        "last_id": "",
        "accruals": [
            {
                "accrued_category": "POSTING",
                "total_amount": _money("42.00"),
                "posting": {
                    "products": [
                        {
                            "sku": "1",
                            "commission": {
                                "sale_amount": _money("100.00"),
                                "seller_price": _money("90.00"),
                                "sale_price": _money("70.00"),
                                "bonus": _money("15.00"),
                                "coinvestment": _money("5.00"),
                                "sale_commission": _money("-9.00"),
                            },
                            "delivery": {
                                "services": [
                                    {"type_id": 32, "accrued": _money("-7.00")}
                                ]
                            },
                        }
                    ]
                },
                "item_fees": {
                    "fees": [
                        {
                            "sku": "1",
                            "fees": [
                                {"type_id": 1, "accrued": _money("-1.00")}
                            ],
                        }
                    ]
                },
            }
        ],
    }


def test_period_profit_finance_validation_preserves_seller_price_mapping():
    client = PeriodProfitOzonClient()
    result = client._normalize_period_profit_finance(
        client.FINANCE_ACCRUAL_BY_DAY,
        _finance_response(),
    )

    assert result["error"] is False
    commission = result["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "90.00"
    assert result["_period_profit_revenue_diagnostics"]["fields"]["sale_amount"]["amount"] == "100.00"


def test_period_profit_finance_fails_closed_when_total_amount_missing():
    client = PeriodProfitOzonClient()
    response = _finance_response()
    response["accruals"][0].pop("total_amount")

    result = client._normalize_period_profit_finance(
        client.FINANCE_ACCRUAL_BY_DAY,
        response,
    )

    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


def test_period_profit_finance_fails_closed_when_sale_commission_missing():
    client = PeriodProfitOzonClient()
    response = _finance_response()
    commission = response["accruals"][0]["posting"]["products"][0]["commission"]
    commission.pop("sale_commission")

    result = client._normalize_period_profit_finance(
        client.FINANCE_ACCRUAL_BY_DAY,
        response,
    )

    assert result["error"] is True
    assert result["code"] == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"


def test_period_profit_finance_fails_closed_when_service_money_malformed():
    client = PeriodProfitOzonClient()
    response = _finance_response()
    response["accruals"][0]["item_fees"]["fees"][0]["fees"][0]["accrued"] = {
        "amount": "not-money",
        "currency": "RUB",
    }

    result = client._normalize_period_profit_finance(
        client.FINANCE_ACCRUAL_BY_DAY,
        response,
    )

    assert result["error"] is True
    assert result["code"] == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"


def test_compact_report_does_not_expose_internal_revenue_diagnostics():
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_QUERY_READY",
        "text": "verbose",
        "summary": {
            "date_from": "2026-08-09",
            "date_to": "2026-08-31",
            "revenue": 374325.0,
            "units_sold": 4811,
            "net_accrual": 141707.0,
            "product_cost": 101031.0,
            "tax": 22460.0,
            "profit": 18217.0,
            "margin_percent": 4.87,
            "revenue_diagnostics": {
                "fields": {
                    "sale_amount": {"complete": True, "amount": 374329.0}
                }
            },
        },
    }

    compact = compact_period_profit_result(result)

    assert "Диагностика выручки Ozon" not in compact["text"]
    assert "sale_amount" not in compact["text"]
    assert compact["summary"]["revenue_diagnostics"] == result["summary"]["revenue_diagnostics"]
    assert compact["read_only"] is True
    assert compact["executed"] is False
