from services.current_product_economics_source import (
    CurrentProductEconomicsSource
)


class FakeOzonClient:

    def __init__(self, response, postings=None):
        self.response = response
        self.postings = postings or {"result": []}
        self.calls = []
        self.posting_calls = []

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

    def get_fbo_postings(self, **kwargs):
        self.posting_calls.append(kwargs)
        return self.postings


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
                    "price": 76,
                    "marketing_seller_price": 95
                },
                "commissions": {
                    "sales_percent_fbo": 14,
                    "fbo_deliv_to_customer_amount": 19.32,
                    "fbo_direct_flow_trans_min_amount": 31,
                    "fbo_direct_flow_trans_max_amount": 46.5
                }
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
    assert result["buyer_price"] == 76.0
    assert result["ozon_discount_compensation"] == 19.0
    assert result["commission_rate"] == 14.0
    assert result["commission_amount"] == 13.3
    assert result["current_delivery_tariff"] == 19.32
    assert result["logistics"] is None
    assert result["last_mile"] is None
    assert result["acquiring_average"] is None
    assert "logistics" in result["missing_data"]
    assert "last_mile" in result["missing_data"]
    assert "acquiring" in result["missing_data"]
    assert ozon.calls == [
        {
            "product_id": "3921245627",
            "offer_id": "hook-2"
        }
    ]


def test_source_prefers_marketing_seller_price():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            _price_response()
        )
    )

    result = source.get("hook-2")

    assert result["seller_price"] == 95.0


def test_source_supports_legacy_commission_list_shape():
    response = _price_response()
    response["items"][0]["commissions"] = [
        {
            "sale_schema": "FBO",
            "percent": 14,
            "fbo_deliv_to_customer_amount": 19.32
        }
    ]

    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(response)
    )

    result = source.get("hook-2")

    assert result["commission_rate"] == 14.0
    assert result["commission_amount"] == 13.3
    assert result["current_delivery_tariff"] == 19.32


def test_source_calculates_recent_finance_averages():
    finance = FakeFinanceService(
        {
            "2026-08-23": {
                "error": False,
                "sales_count": 2,
                "fee_breakdown": {
                    "Эквайринг": -2.0,
                    "Логистика": -38.64,
                    "Доставка до места выдачи": -3.0
                }
            },
            "2026-08-24": {
                "error": False,
                "sales_count": 3,
                "fee_breakdown": {
                    "Эквайринг": -4.0,
                    "Логистика": -57.96,
                    "Доставка до места выдачи": -6.0
                }
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
    assert result["logistics"] == 19.32
    assert result["last_mile"] == 1.8
    assert result["finance_sample_sales"] == 5
    assert result["finance_sample_days"] == 2
    assert result["missing_data"] == []


def test_source_calculates_buyout_rate_as_diagnostic_only():
    postings = []
    for _ in range(45):
        postings.append(
            {
                "status": "delivered",
                "products": [{"offer_id": "hook-2"}]
            }
        )
    for _ in range(5):
        postings.append(
            {
                "status": "cancelled",
                "products": [{"offer_id": "hook-2"}]
            }
        )
    postings.append(
        {
            "status": "delivering",
            "products": [{"offer_id": "hook-2"}]
        }
    )

    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            _price_response(),
            {"result": postings}
        )
    )

    result = source.get(
        "hook-2",
        buyout_since="2026-08-01T00:00:00Z",
        buyout_to="2026-08-25T00:00:00Z"
    )

    assert result["buyout_rate"] == 90.0
    assert result["buyout_sample_size"] == 50
    assert result["buyout_delivered"] == 45
    assert result["buyout_cancelled"] == 5
    assert result["buyout_basis"] == "last_completed_fbo_postings"
    assert "buyout_rate" not in result["missing_data"]


def test_source_buyout_diagnostic_ignores_other_sku_and_in_progress():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            _price_response(),
            {
                "result": [
                    {
                        "status": "delivered",
                        "products": [{"offer_id": "other"}]
                    },
                    {
                        "status": "delivering",
                        "products": [{"offer_id": "hook-2"}]
                    }
                ]
            }
        )
    )

    result = source.get(
        "hook-2",
        buyout_since="2026-08-01T00:00:00Z",
        buyout_to="2026-08-25T00:00:00Z"
    )

    assert result["buyout_rate"] is None
    assert "buyout_rate" not in result["missing_data"]


def test_source_keeps_unknown_values_as_none():
    source = CurrentProductEconomicsSource(
        ozon_client=FakeOzonClient(
            {
                "items": [
                    {
                        "product_id": 1,
                        "offer_id": "sku-1",
                        "price": {},
                        "commissions": {}
                    }
                ]
            }
        )
    )

    result = source.get("sku-1")

    assert result["seller_price"] is None
    assert result["buyer_price"] is None
    assert result["ozon_discount_compensation"] is None
    assert result["commission_amount"] is None
    assert result["logistics"] is None
    assert result["last_mile"] is None
    assert result["acquiring_average"] is None
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
