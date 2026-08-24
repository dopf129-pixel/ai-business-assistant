from services.current_product_economics_source import (
    CurrentProductEconomicsSource
)


class FakeOzonClient:

    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_product_prices(
        self,
        product_id=None,
        offer_id=None
    ):
        self.calls.append(
            {
                "product_id": product_id,
                "offer_id": offer_id
            }
        )
        return self.response


class FakeFinanceService:

    def __init__(self, results):
        self.results = results

    def get_daily_finance(
        self,
        accrual_date,
        sku=None
    ):
        return self.results[accrual_date]


def _price_response():
    return {
        "items": [
            {
                "product_id": 3921245627,
                "offer_id": "hook-2",
                "price": {
                    "price": 95,
                    "marketing_seller_price": 95
                },
                "commissions": [
                    {
                        "sale_schema": "FBO",
                        "percent": 14,
                        "fbo_deliv_to_customer_amount": 19.32
                    }
                ]
            }
        ]
    }


def test_source_uses_current_seller_price_and_commission():
    ozon = FakeOzonClient(
        _price_response()
    )
    source = CurrentProductEconomicsSource(
        ozon_client=ozon
    )

    result = source.get(
        sku="hook-2",
        product_id="3921245627"
    )

    assert result["seller_price"] == 95.0
    assert result["commission_rate"] == 14.0
    assert result["commission_amount"] == 13.3
    assert result["logistics"] == 19.32
    assert result["last_mile"] is None
    assert result["buyout_rate"] is None
    assert "last_mile" in result["missing_data"]
    assert "buyout_rate" in result["missing_data"]
    assert ozon.calls == [
        {
            "product_id": "3921245627",
            "offer_id": "hook-2"
        }
    ]


def test_source_prefers_marketing_seller_price():
    response = _price_response()
    response["items"][0]["price"][
        "price"
    ] = 76
    response["items"][0]["price"][
        "marketing_seller_price"
    ] = 95

    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            response
        )
    )

    result = source.get("hook-2")

    assert result["seller_price"] == 95.0


def test_source_calculates_recent_acquiring_average():
    finance = FakeFinanceService(
        {
            "2026-08-23": {
                "error": False,
                "sales_count": 2,
                "acquiring": -2.0
            },
            "2026-08-24": {
                "error": False,
                "sales_count": 3,
                "acquiring": -4.0
            }
        }
    )
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            _price_response()
        ),
        finance_service=finance
    )

    result = source.get(
        "hook-2",
        accrual_dates=[
            "2026-08-23",
            "2026-08-24"
        ]
    )

    assert result["acquiring_average"] == 1.2
    assert "acquiring" not in result[
        "missing_data"
    ]


def test_source_keeps_unknown_values_as_none():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            {
                "items": [
                    {
                        "product_id": 1,
                        "offer_id": "sku-1",
                        "price": {},
                        "commissions": []
                    }
                ]
            }
        )
    )

    result = source.get("sku-1")

    assert result["seller_price"] is None
    assert result["commission_amount"] is None
    assert result["logistics"] is None
    assert result["acquiring_average"] is None
    assert result["buyout_rate"] is None
    assert "current_price" in result[
        "missing_data"
    ]


def test_source_returns_safe_result_when_sku_not_found():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            {"items": []}
        )
    )

    result = source.get("missing")

    assert result["error"] is False
    assert result["seller_price"] is None
    assert "current_price" in result[
        "missing_data"
    ]


def test_source_propagates_ozon_error_without_fallback_price():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            {
                "error": True,
                "message": "Ozon unavailable"
            }
        )
    )

    result = source.get("hook-2")

    assert result["error"] is True
    assert result["message"] == (
        "Ozon unavailable"
    )
    assert result["missing_data"] == [
        "current_price"
    ]