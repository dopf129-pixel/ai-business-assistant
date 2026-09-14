from datetime import date

from services.period_profit_cached_legacy_sku_identity_scope_service import (
    PeriodProfitCachedLegacySkuIdentityScopeService,
)


class _Summary:
    cost_service = object()


class _Finance:
    pass


class _Ozon:
    def __init__(self):
        self.calls = 0

    def get_fbo_postings(self, since, to, **kwargs):
        self.calls += 1
        return {
            "result": {
                "postings": [
                    {
                        "posting_number": "p-1",
                        "products": [
                            {"sku": "legacy-1", "offer_id": "offer-1"}
                        ],
                    },
                    {
                        "posting_number": "p-2",
                        "products": [
                            {"sku": "legacy-2", "offer_id": "offer-2"}
                        ],
                    },
                ],
                "has_next": False,
            }
        }


def test_multiple_legacy_skus_share_one_fbo_snapshot():
    ozon = _Ozon()
    service = PeriodProfitCachedLegacySkuIdentityScopeService(
        _Summary(),
        _Finance(),
        sku_ozon_client=ozon,
    )
    service._scope_start = date(2026, 6, 1)
    service._scope_end = date(2026, 8, 29)
    service._catalog_by_offer = {
        "offer-1": [{"product_id": "1", "offer_id": "offer-1", "sku": "current-1"}],
        "offer-2": [{"product_id": "2", "offer_id": "offer-2", "sku": "current-2"}],
    }
    service._finance_posting_numbers_by_sku = {}

    first = service._recover_catalog_product_from_fbo("legacy-1")
    second = service._recover_catalog_product_from_fbo("legacy-2")

    assert first["product_id"] == "1"
    assert first["offer_id"] == "offer-1"
    assert second["product_id"] == "2"
    assert second["offer_id"] == "offer-2"
    assert ozon.calls == 1


def test_fbo_snapshot_failure_is_cached_for_whole_scope():
    class _BrokenOzon:
        def __init__(self):
            self.calls = 0

        def get_fbo_postings(self, *args, **kwargs):
            self.calls += 1
            return {"error": True}

    ozon = _BrokenOzon()
    service = PeriodProfitCachedLegacySkuIdentityScopeService(
        _Summary(),
        _Finance(),
        sku_ozon_client=ozon,
    )
    service._scope_start = date(2026, 6, 1)
    service._scope_end = date(2026, 8, 29)
    service._catalog_by_offer = {}

    assert service._recover_catalog_product_from_fbo("legacy-1") is None
    assert service._recover_catalog_product_from_fbo("legacy-2") is None
    assert ozon.calls == 1
