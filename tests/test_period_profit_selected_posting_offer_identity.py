from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)


class _Summary:
    cost_service = None
    tax_rate = None


class _Ozon:
    def get_related_skus(self, skus):
        return {"error": False, "items": [], "errors": []}

    def get_fbo_posting(self, posting_number):
        return {
            "error": False,
            "result": {
                "posting_number": posting_number,
                "products": [{
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                    "quantity": 1,
                }],
            },
        }

    def get_fbs_posting(self, posting_number):
        return {"error": True}


class _Finance:
    ozon = _Ozon()


def _service():
    service = PeriodProfitFinancePostingIdentityScopeService(
        _Summary(), _Finance()
    )
    selected = {
        "product_id": "current-product",
        "offer_id": "10002_white_01",
        "sku": "989101156",
        "_period_profit_selected_scope": True,
    }
    service._catalog_by_sku = {"989101156": selected}
    service._catalog_by_product_id = {"current-product": selected}
    service._catalog_by_offer = {"10002_white_01": selected}
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {"posting-1"},
    }
    return service


def test_recovers_legacy_finance_sku_by_exact_posting_offer_id():
    service = _service()
    result = service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    )
    assert result["product_id"] == "current-product"
    assert result["offer_id"] == "10002_white_01"
    assert result["catalog_sku"] == "989101156"
    assert result["sku"] == "legacy-finance-sku"
    assert result["historical_sku_identity_source"] == (
        "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
    )


def test_posting_offer_bridge_rejects_offer_not_in_selected_catalog_scope():
    service = _service()
    service.finance_service.ozon.get_fbo_posting = lambda posting_number: {
        "error": False,
        "result": {
            "posting_number": posting_number,
            "products": [{
                "sku": "legacy-finance-sku",
                "offer_id": "other-offer",
                "quantity": 1,
            }],
        },
    }
    assert service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    ) is None


def test_posting_offer_bridge_does_not_probe_fbs_after_usable_fbo_response():
    service = _service()
    calls = []

    def fbo(posting_number):
        calls.append(("fbo", posting_number))
        return {
            "error": False,
            "result": {
                "posting_number": posting_number,
                "products": [{
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                    "quantity": 1,
                }],
            },
        }

    def fbs(posting_number):
        calls.append(("fbs", posting_number))
        raise AssertionError("FBS must not be probed after a usable FBO response")

    service.finance_service.ozon.get_fbo_posting = fbo
    service.finance_service.ozon.get_fbs_posting = fbs

    result = service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    )

    assert result["offer_id"] == "10002_white_01"
    assert calls == [("fbo", "posting-1")]


def test_posting_offer_bridge_falls_back_to_fbs_when_fbo_has_no_products():
    service = _service()
    calls = []

    def fbo(posting_number):
        calls.append(("fbo", posting_number))
        return {"error": True, "status_code": 404}

    def fbs(posting_number):
        calls.append(("fbs", posting_number))
        return {
            "error": False,
            "result": {
                "posting_number": posting_number,
                "products": [{
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                    "quantity": 1,
                }],
            },
        }

    service.finance_service.ozon.get_fbo_posting = fbo
    service.finance_service.ozon.get_fbs_posting = fbs

    result = service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    )

    assert result["offer_id"] == "10002_white_01"
    assert calls == [("fbo", "posting-1"), ("fbs", "posting-1")]


def test_selected_sku_posting_identity_has_bounded_ozon_call_count():
    service = _service()
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {
            "posting-%03d" % index for index in range(250)
        },
    }
    calls = []

    def fbo(posting_number):
        calls.append(("fbo", posting_number))
        return {
            "error": False,
            "result": {
                "posting_number": posting_number,
                "products": [{
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                }],
            },
        }

    service.finance_service.ozon.get_fbo_posting = fbo
    result = service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    )

    assert result["offer_id"] == "10002_white_01"
    assert calls == [("fbo", "posting-000")]


def test_missing_posting_identity_is_bounded_and_fails_closed():
    service = _service()
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {
            "posting-%03d" % index for index in range(250)
        },
    }
    calls = []

    def missing(kind):
        def get(posting_number):
            calls.append((kind, posting_number))
            return {"error": True, "status_code": 404}
        return get

    service.finance_service.ozon.get_fbo_posting = missing("fbo")
    service.finance_service.ozon.get_fbs_posting = missing("fbs")

    result = service._recover_from_finance_posting_offer_identity(
        "legacy-finance-sku"
    )

    assert result is None
    assert len(calls) == 2 * service.MAX_SELECTED_POSTING_IDENTITY_PROBES
