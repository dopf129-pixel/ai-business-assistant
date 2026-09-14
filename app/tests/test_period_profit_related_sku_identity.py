from api.period_profit_related_sku_ozon_client import PeriodProfitRelatedSkuOzonClient
from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _NoDirectCost:
    def get_historical_cost_evidence(self, *args, **kwargs):
        return {"error": True, "code": "PRODUCT_COST_HISTORY_MISSING"}

    def get_all_costs(self):
        return []


class _Summary:
    def __init__(self):
        self.cost_service = _NoDirectCost()
        self.tax_rate = 0.0
        self.received_products = None

    def calculate(self, _date_from, _date_to, products):
        self.received_products = products
        return {"error": False}


class _RelatedOzon:
    def __init__(self, items, errors=None):
        self.items = list(items)
        self.errors = list(errors or [])
        self.calls = []

    def get_related_skus(self, skus):
        self.calls.append(tuple(skus))
        return {
            "error": False,
            "items": list(self.items),
            "errors": list(self.errors),
        }


class _Finance:
    def __init__(self, ozon):
        self.ozon = ozon
        self._daily_accrual_cache = {}
        self.posting_calls = []

    def prefetch_daily_accruals(self, date_from, _date_to):
        self._daily_accrual_cache[str(date_from)] = {
            "error": False,
            "accruals": [{
                "accrued_category": "POSTING",
                "unit_number": "posting-legacy",
                "posting": {"products": [{"sku": "legacy-sku"}]},
            }],
        }
        return {"error": False, "complete": True}

    def _get_accruals_by_day(self, day):
        return self._daily_accrual_cache[str(day)]

    def get_sale_posting_quantity_evidence(self, posting_numbers):
        self.posting_calls.append(tuple(posting_numbers))
        return {
            "error": False,
            "complete": True,
            "records": [],
        }


def test_related_sku_resolves_retired_finance_sku_without_fbo_or_posting_bridge():
    ozon = _RelatedOzon([
        {
            "sku": "legacy-sku",
            "product_id": "product-1",
            "delivery_schema": "FBO",
            "availability": "HIDDEN",
        },
        {
            "sku": "current-sku",
            "product_id": "product-1",
            "delivery_schema": "FBO",
            "availability": "AVAILABLE",
        },
    ])
    finance = _Finance(ozon)
    summary = _Summary()
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [{
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "current-sku",
        }],
    )

    assert result["error"] is False
    assert ozon.calls == [("legacy-sku",)]
    assert finance.posting_calls == []
    product = summary.received_products[0]
    assert product["sku"] == "legacy-sku"
    assert product["catalog_sku"] == "current-sku"
    assert product["product_id"] == "product-1"
    assert product["offer_id"] == "offer-1"
    assert product["historical_sku_identity_source"] == (
        "OZON_RELATED_SKU_TO_CURRENT_CATALOG"
    )


def test_related_sku_ambiguity_falls_through_and_still_fails_closed():
    ozon = _RelatedOzon([
        {"sku": "legacy-sku", "product_id": "product-legacy"},
        {"sku": "current-a", "product_id": "product-a"},
        {"sku": "current-b", "product_id": "product-b"},
    ])
    finance = _Finance(ozon)
    summary = _Summary()
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [
            {"product_id": "product-a", "offer_id": "offer-a", "sku": "current-a"},
            {"product_id": "product-b", "offer_id": "offer-b", "sku": "current-b"},
        ],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    assert result["finance_diagnostic_code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_AMBIGUOUS"
    )
    assert finance.posting_calls == [("posting-legacy",)]


def test_related_sku_client_is_read_only_and_uses_single_lookup(monkeypatch):
    calls = []

    def fake_post(self, endpoint, data, timeout=20, max_attempts=3):
        calls.append((endpoint, data, timeout, max_attempts))
        return {
            "items": [
                {"sku": "legacy-sku", "product_id": "product-1"},
                {"sku": "current-sku", "product_id": "product-1"},
            ],
            "errors": [],
        }

    monkeypatch.setattr(
        "api.period_profit_ozon_client.PeriodProfitOzonClient._post",
        fake_post,
    )
    client = PeriodProfitRelatedSkuOzonClient()
    result = client.get_related_skus(["legacy-sku"])

    assert result["error"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
    assert calls == [(
        "/v1/product/related-sku/get",
        {"sku": ["legacy-sku"]},
        10,
        1,
    )]

def test_factory_assigned_related_client_preserves_runtime_nonsale_normalization(
    monkeypatch,
):
    from api.ozon_client import OzonClient
    from services.period_profit_finance_service import PeriodProfitFinanceService

    responses = {
        "2026-09-08": {
            "accruals": [{
                "accrued_category": "POSTING",
                "total_amount": {"amount": "-25", "currency": "RUB"},
                "posting": {"products": [{"sku": "legacy-sku"}]},
            }],
            "last_id": "",
        },
        "2026-09-09": {
            "accruals": [{
                "accrued_category": "POSTING",
                "total_amount": {"amount": "-10", "currency": "RUB"},
                "posting": {"products": [{
                    "sku": "legacy-sku",
                    "commission": None,
                }]},
            }],
            "last_id": "",
        },
    }

    def read_only_post(self, endpoint, data, timeout=20, max_attempts=3):
        assert endpoint == "/v1/finance/accrual/by-day"
        return responses[data["date"]]

    monkeypatch.setattr(OzonClient, "_post", read_only_post)
    finance = PeriodProfitFinanceService()
    finance.ozon = PeriodProfitRelatedSkuOzonClient(
        client_id="client",
        api_key="key",
    )

    result = finance.prefetch_daily_accruals("2026-09-08", "2026-09-09")

    assert result["error"] is False
    assert result["date_count"] == 2
    for response in finance._daily_accrual_cache.values():
        commission = response["accruals"][0]["posting"]["products"][0]["commission"]
        assert commission["sale_amount"]["amount"] == "0"


def test_related_client_keeps_malformed_commission_fail_closed():
    client = PeriodProfitRelatedSkuOzonClient()
    result = client._normalize_period_profit_canonical_finance(
        client.FINANCE_ACCRUAL_BY_DAY,
        {
            "accruals": [{
                "accrued_category": "POSTING",
                "total_amount": {"amount": "-25", "currency": "RUB"},
                "posting": {"products": [{
                    "sku": "legacy-sku",
                    "commission": "ambiguous",
                }]},
            }],
        },
    )

    assert result["error"] is True
    assert result["code"] == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"


def test_related_sku_api_error_is_distinguished_without_exposing_payload():
    class _UnavailableRelatedOzon:
        def get_related_skus(self, skus):
            assert skus == ["legacy-sku"]
            return {
                "error": True,
                "code": "OZON_RELATED_SKU_HTTP_403",
                "payload": {"secret": "must-not-escape"},
            }

    finance = _Finance(_UnavailableRelatedOzon())
    summary = _Summary()
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [{
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "current-sku",
        }],
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    )
    assert result["finance_diagnostic_code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_API_ERROR"
    )
    assert "payload" not in result
    assert "legacy-sku" not in result["finance_diagnostic_code"]


class _SellerCostIdentity(_NoDirectCost):
    def __init__(self, rows):
        self.rows = list(rows)

    def get_all_costs(self):
        return list(self.rows)


def test_related_sku_resolves_hidden_product_through_seller_cost_identity():
    ozon = _RelatedOzon([
        {"sku": "legacy-sku", "availability": "HIDDEN"},
        {"sku": "current-sku", "availability": "HIDDEN"},
    ])
    finance = _Finance(ozon)
    summary = _Summary()
    summary.cost_service = _SellerCostIdentity([
        ("product-1", "current-sku", "offer-1", 999.0, "RUB"),
    ])
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [{
            "product_id": "unrelated-product",
            "offer_id": "unrelated-offer",
            "sku": "unrelated-sku",
        }],
    )

    assert result["error"] is False
    product = summary.received_products[0]
    assert product["sku"] == "legacy-sku"
    assert product["catalog_sku"] == "current-sku"
    assert product["product_id"] == "product-1"
    assert product["offer_id"] == "offer-1"
    assert "cost_price" not in product
    assert product["historical_sku_identity_source"] == (
        "OZON_RELATED_SKU_TO_SELLER_COST_IDENTITY"
    )


def test_related_seller_cost_identity_ambiguity_remains_fail_closed():
    ozon = _RelatedOzon([
        {"sku": "legacy-sku", "availability": "HIDDEN"},
        {"sku": "current-a", "availability": "HIDDEN"},
        {"sku": "current-b", "availability": "HIDDEN"},
    ])
    finance = _Finance(ozon)
    summary = _Summary()
    summary.cost_service = _SellerCostIdentity([
        ("product-a", "current-a", "offer-a", 10.0, "RUB"),
        ("product-b", "current-b", "offer-b", 20.0, "RUB"),
    ])
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary,
        finance,
        sku_ozon_client=None,
    )

    result = service.calculate(
        "2026-09-14",
        "2026-09-14",
        [{
            "product_id": "unrelated-product",
            "offer_id": "unrelated-offer",
            "sku": "unrelated-sku",
        }],
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    )
    assert result["finance_diagnostic_code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_RELATED_AMBIGUOUS"
    )
