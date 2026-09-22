from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _Ozon:
    def __init__(self):
        self.fbo_list_calls = 0
        self.fbo_detail_calls = 0
        self.fbs_detail_calls = 0

    def get_fbo_postings(self, *_args, **_kwargs):
        self.fbo_list_calls += 1
        raise AssertionError("account-wide FBO pagination must not be used")

    def get_related_skus(self, _skus):
        return {"items": [], "errors": []}

    def get_fbo_posting(self, _posting_number):
        self.fbo_detail_calls += 1
        return {"result": {"products": []}}

    def get_fbs_posting(self, _posting_number):
        self.fbs_detail_calls += 1
        return {"result": {"products": []}}


class _Finance:
    def __init__(self, ozon):
        self.ozon = ozon


def test_store_wide_identity_recovery_never_pages_account_fbo_snapshot():
    ozon = _Ozon()
    service = PeriodProfitFinancePostingIdentityScopeService(
        summary_service=object(),
        finance_service=_Finance(ozon),
    )
    service._catalog_by_sku = {"current": {"sku": "current", "product_id": "1"}}
    service._catalog_by_product_id = {"1": {"sku": "current", "product_id": "1"}}
    service._catalog_by_offer = {"offer": {"sku": "current", "product_id": "1", "offer_id": "offer"}}
    service._related_sku_identity_cache = {}
    service._legacy_identity_cache = {}
    service._finance_posting_numbers_by_sku = {"historic": {"posting-1"}}
    service._realization_identity_responses = {}
    service._scope_start = None
    service._scope_end = None

    assert service._recover_missing_product("historic", "2026-09-22") is None
    assert ozon.fbo_list_calls == 0
    # Exact detail fallback has a fixed per-SKU budget and stops after the
    # first endpoint returning a structurally usable posting response.
    assert ozon.fbo_detail_calls <= service.MAX_SELECTED_POSTING_IDENTITY_PROBES
    assert ozon.fbs_detail_calls <= service.MAX_SELECTED_POSTING_IDENTITY_PROBES
