from datetime import datetime, timezone

from services.product_returns_finance_impact_query_service import (
    ProductReturnsFinanceImpactQueryService,
)


class StubProductService:
    def __init__(self, products):
        self.products = products

    def load_products(self):
        return self.products


class StubAttributionQuery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.result is None:
            return None
        return dict(self.result)


def _service(products=None, result=None):
    query = StubAttributionQuery(
        {
            "error": False,
            "complete": False,
            "missing_data": [
                "finance_postings_unmatched"
            ],
            "categories": {},
        }
        if result is None
        else result
    )
    service = ProductReturnsFinanceImpactQueryService(
        product_service=StubProductService(
            products
            if products is not None
            else [{
                "product_id": "101",
                "offer_id": "hook-2",
                "sku": 3921245627,
            }]
        ),
        attribution_query_service=query,
        period_days=30,
        now_provider=lambda: datetime(
            2026,
            8,
            25,
            10,
            45,
            tzinfo=timezone.utc,
        ),
    )
    return service, query


def test_resolves_offer_and_finance_sku_for_complete_days():
    service, query = _service()

    result = service.query("hook-2")

    assert query.calls == [{
        "sku": "hook-2",
        "finance_sku": "3921245627",
        "since": "2026-07-26T00:00:00Z",
        "to": "2026-08-25T00:00:00Z",
    }]
    assert result["error"] is False
    assert result["product_id"] == "101"
    assert result["sku"] == "hook-2"
    assert result["finance_sku"] == "3921245627"
    assert result["requested_sku"] == "hook-2"
    assert result["period_days"] == 30
    assert result["period_complete_days"] is True
    assert result["complete"] is False


def test_accepts_internal_ozon_sku_and_tuple_product():
    service, query = _service(
        products=[
            ("101", "hook-2", 3921245627),
        ]
    )

    result = service.query({"sku": "3921245627"})

    assert result["error"] is False
    assert result["sku"] == "hook-2"
    assert result["requested_sku"] == "3921245627"
    assert query.calls[0]["sku"] == "hook-2"
    assert query.calls[0]["finance_sku"] == "3921245627"


def test_requires_sku_before_loading_attribution():
    service, query = _service()

    result = service.query({"sku": "  "})

    assert result == {
        "error": True,
        "code": "SKU_REQUIRED",
        "product_id": None,
        "sku": None,
        "message": "SKU не указан",
        "complete": False,
        "missing_data": ["sku"],
    }
    assert query.calls == []


def test_returns_sku_not_found_without_zero_fallback():
    service, query = _service(products=[])

    result = service.query("missing")

    assert result["error"] is True
    assert result["code"] == "SKU_NOT_FOUND"
    assert result["sku"] == "missing"
    assert result["complete"] is False
    assert result["missing_data"] == ["sku"]
    assert query.calls == []


def test_requires_offer_id_and_internal_finance_sku():
    missing_offer, offer_query = _service(products=[{
        "product_id": "101",
        "sku": 3921245627,
    }])
    missing_finance, finance_query = _service(products=[{
        "product_id": "101",
        "offer_id": "hook-2",
    }])

    offer_result = missing_offer.query("3921245627")
    finance_result = missing_finance.query("hook-2")

    assert offer_result["code"] == "OFFER_ID_MISSING"
    assert offer_result["missing_data"] == ["offer_id"]
    assert finance_result["code"] == "FINANCE_SKU_MISSING"
    assert finance_result["missing_data"] == ["finance_sku"]
    assert offer_query.calls == []
    assert finance_query.calls == []


def test_preserves_attribution_error_with_product_identity():
    service, _ = _service(result={
        "error": True,
        "code": "FINANCE_UNAVAILABLE",
        "message": "Финансы недоступны",
        "complete": False,
        "missing_data": ["finance"],
    })

    result = service.query("hook-2")

    assert result["error"] is True
    assert result["code"] == "FINANCE_UNAVAILABLE"
    assert result["product_id"] == "101"
    assert result["sku"] == "hook-2"
    assert result["finance_sku"] == "3921245627"
    assert result["missing_data"] == ["finance"]


def test_handles_invalid_attribution_contract():
    service, _ = _service(result={})
    service.attribution_query_service.result = None

    result = service.query("hook-2")

    assert result["error"] is True
    assert result["code"] == "RETURNS_FINANCE_UNAVAILABLE"
    assert result["complete"] is False
    assert result["missing_data"] == ["returns_finance"]


def test_normalizes_naive_clock_to_utc_complete_days():
    service, query = _service()
    service.now_provider = lambda: datetime(
        2026,
        8,
        25,
        23,
        59,
    )

    service.query("hook-2")

    assert query.calls[0]["since"] == "2026-07-26T00:00:00Z"
    assert query.calls[0]["to"] == "2026-08-25T00:00:00Z"
