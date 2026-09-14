from services.period_profit_cached_legacy_sku_identity_scope_service import (
    PeriodProfitCachedLegacySkuIdentityScopeService,
)


class _Summary:
    def __init__(self, cost_service):
        self.cost_service = cost_service
        self.tax_rate = 0.0


class _CostService:
    def get_historical_cost_evidence(self, at_date, sku=None, **_kwargs):
        if sku == "legacy-sku":
            return {
                "error": False,
                "historical_cost_confirmed": True,
                "product_id": "product-1",
                "sku": "legacy-sku",
                "offer_id": "offer-1",
                "cost_price": 21.0,
                "currency": "RUB",
            }
        return {"error": True, "code": "PRODUCT_COST_HISTORY_MISSING"}

    def get_all_costs(self):
        return []


class _Finance:
    pass


class _ExplodingFboClient:
    def __init__(self):
        self.calls = 0

    def get_fbo_postings(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("FBO must not be called when seller identity is already proven")


def test_proven_direct_identity_skips_optional_fbo_enrichment():
    client = _ExplodingFboClient()
    service = PeriodProfitCachedLegacySkuIdentityScopeService(
        _Summary(_CostService()),
        _Finance(),
        sku_ozon_client=client,
    )

    recovered = service._recover_missing_product("legacy-sku", "2026-09-14")

    assert recovered["product_id"] == "product-1"
    assert recovered["sku"] == "legacy-sku"
    assert recovered["offer_id"] == "offer-1"
    assert recovered["historical_sku_identity_recovered"] is True
    assert recovered["historical_sku_identity_source"] == (
        "SELLER_CONFIRMED_HISTORICAL_COST_IDENTITY"
    )
    assert client.calls == 0
