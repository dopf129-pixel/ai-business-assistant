from services.period_profit_finance_posting_identity_scope_service import (
    PeriodProfitFinancePostingIdentityScopeService,
)
from datetime import date


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


def test_realization_resolves_offer_beyond_first_three_postings_without_n_plus_one():
    service = _service()
    service._scope_start = date(2026, 9, 1)
    service._scope_end = date(2026, 9, 19)
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {
            "posting-%03d" % index for index in range(250)
        },
    }
    realization_calls = []
    detail_calls = []

    def realization(year, month):
        realization_calls.append((year, month))
        return {
            "error": False,
            "rows": [{
                "order": {"posting_number": "posting-249"},
                "item": {
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                },
            }],
        }

    service.finance_service.ozon.get_realization_posting = realization
    service.finance_service.ozon.get_fbo_posting = (
        lambda posting_number: detail_calls.append(posting_number)
    )

    result = service._recover_missing_product(
        "legacy-finance-sku",
        date(2026, 9, 19),
    )

    assert result["offer_id"] == "10002_white_01"
    assert result["historical_sku_identity_source"] == (
        "OZON_REALIZATION_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
    )
    assert realization_calls == [(2026, 9)]
    assert detail_calls == []


def test_realization_offer_conflict_remains_fail_closed():
    service = _service()
    other = {
        "product_id": "other-product",
        "offer_id": "other-offer",
        "sku": "other-catalog-sku",
    }
    service._catalog_by_offer["other-offer"] = other
    service._scope_start = date(2026, 9, 1)
    service._scope_end = date(2026, 9, 19)
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {"posting-1", "posting-2"},
    }
    service.finance_service.ozon.get_realization_posting = lambda year, month: {
        "error": False,
        "rows": [
            {
                "order": {"posting_number": "posting-1"},
                "item": {
                    "sku": "legacy-finance-sku",
                    "offer_id": "10002_white_01",
                },
            },
            {
                "order": {"posting_number": "posting-2"},
                "item": {
                    "sku": "legacy-finance-sku",
                    "offer_id": "other-offer",
                },
            },
        ],
    }
    service.finance_service.ozon.get_fbo_posting = lambda posting_number: {
        "error": True,
    }
    service.finance_service.ozon.get_fbs_posting = lambda posting_number: {
        "error": True,
    }

    assert service._recover_from_realization_offer_identity(
        "legacy-finance-sku"
    ) is None
    assert "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_REALIZATION_OFFER_AMBIGUOUS" in (
        service._sku_recovery_diagnostic_codes
    )


def test_realization_accepts_rewritten_sku_for_unique_finance_posting():
    service = _service()
    service._scope_start = date(2026, 9, 1)
    service._scope_end = date(2026, 9, 19)
    service.finance_service.ozon.get_realization_posting = lambda year, month: {
        "error": False,
        "rows": [{
            "order": {"posting_number": "posting-1"},
            "item": {
                "sku": "989101156",
                "offer_id": "10002_white_01",
            },
        }],
    }

    result = service._recover_from_realization_offer_identity(
        "legacy-finance-sku"
    )

    assert result["catalog_sku"] == "989101156"
    assert result["sku"] == "legacy-finance-sku"


def test_realization_rewritten_sku_rejects_multi_product_posting():
    service = _service()
    service._scope_start = date(2026, 9, 1)
    service._scope_end = date(2026, 9, 19)
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {"posting-1"},
        "other-finance-sku": {"posting-1"},
    }
    service.finance_service.ozon.get_realization_posting = lambda year, month: {
        "error": False,
        "rows": [{
            "order": {"posting_number": "posting-1"},
            "item": {
                "sku": "989101156",
                "offer_id": "10002_white_01",
            },
        }],
    }

    assert service._recover_from_realization_offer_identity(
        "legacy-finance-sku"
    ) is None


def test_fbo_period_snapshot_finds_late_posting_without_detail_n_plus_one():
    service = _service()
    service._catalog_by_sku["989101156"].pop("_period_profit_selected_scope")
    service._scope_start = date(2026, 9, 1)
    service._scope_end = date(2026, 9, 19)
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {
            "posting-%03d" % index for index in range(250)
        },
    }
    list_calls = []
    detail_calls = []
    service.finance_service.ozon.get_realization_posting = lambda year, month: {
        "error": True,
    }

    def fbo_list(since, to, **kwargs):
        list_calls.append((since, to, kwargs))
        return {
            "error": False,
            "result": {
                "postings": [{
                    "posting_number": "posting-249",
                    "products": [{
                        "sku": "989101156",
                        "offer_id": "10002_white_01",
                    }],
                }],
                "has_next": False,
            },
        }

    service.finance_service.ozon.get_fbo_postings = fbo_list
    service.finance_service.ozon.get_fbo_posting = (
        lambda posting_number: detail_calls.append(posting_number)
    )

    result = service._recover_missing_product(
        "legacy-finance-sku",
        date(2026, 9, 19),
    )

    assert result["catalog_sku"] == "989101156"
    assert result["historical_sku_identity_source"] == (
        "OZON_FBO_SNAPSHOT_TO_CURRENT_CATALOG_OFFER_ID"
    )
    assert len(list_calls) == 1
    assert detail_calls == []


def test_selected_scope_prefilters_hundreds_of_unrelated_finance_skus():
    class Summary:
        cost_service = None
        tax_rate = 0.0

        def __init__(self):
            self.products = None

        def calculate(self, _date_from, _date_to, products):
            self.products = products
            return {"error": False}

    class Ozon:
        def __init__(self):
            self.related_calls = []
            self.realization_calls = []

        def get_related_skus(self, skus):
            self.related_calls.append(tuple(skus))
            return {"error": False, "items": [], "errors": []}

        def get_realization_posting(self, year, month):
            self.realization_calls.append((year, month))
            return {
                "error": False,
                "rows": [{
                    "order": {"posting_number": "posting-selected"},
                    "item": {
                        "sku": "current-selected",
                        "offer_id": "selected-offer",
                    },
                }],
            }

    class Finance:
        def __init__(self):
            self.ozon = Ozon()
            products = [
                {"sku": "unrelated-%03d" % index}
                for index in range(200)
            ] + [{"sku": "legacy-selected"}]
            self.response = {
                "error": False,
                "accruals": [
                    {
                        "accrued_category": "POSTING",
                        "unit_number": (
                            "posting-selected"
                            if product["sku"] == "legacy-selected"
                            else "posting-" + product["sku"]
                        ),
                        "posting": {"products": [product]},
                    }
                    for product in products
                ],
            }

        def prefetch_daily_accruals(self, *_args):
            return {"error": False}

        def _get_accruals_by_day(self, _day):
            return self.response

    summary = Summary()
    finance = Finance()
    service = PeriodProfitFinancePostingIdentityScopeService(summary, finance)

    result = service.calculate(
        "2026-09-19",
        "2026-09-19",
        [{
            "product_id": "selected-product",
            "sku": "current-selected",
            "offer_id": "selected-offer",
            "_period_profit_selected_scope": True,
        }],
    )

    assert result["error"] is False
    assert [product["sku"] for product in summary.products] == [
        "legacy-selected"
    ]
    assert finance.ozon.realization_calls == [(2026, 9)]
    assert finance.ozon.related_calls == []


def test_selected_scope_uses_one_reverse_related_lookup_not_fbo_history():
    service = _service()
    selected = service._catalog_by_sku["989101156"]
    all_skus = {
        "unrelated-%03d" % index for index in range(500)
    } | {"legacy-finance-sku"}
    related_calls = []

    def related(skus):
        related_calls.append(tuple(skus))
        return {
            "error": False,
            "items": [
                {"sku": "989101156", "product_id": "current-product"},
                {"sku": "legacy-finance-sku", "product_id": "current-product"},
            ],
            "errors": [],
        }

    service.finance_service.ozon.get_related_skus = related
    service.finance_service.ozon.get_realization_posting = lambda *_args: {
        "error": True,
    }
    service.finance_service.ozon.get_fbo_postings = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("selected scope must not list FBO"))
    )

    result = service._selected_finance_sku_candidates(
        all_skus,
        selected,
        date(2026, 9, 19),
    )

    assert result == {"legacy-finance-sku"}
    assert related_calls == [("989101156",)]
    recovered = service._recover_missing_product(
        "legacy-finance-sku",
        date(2026, 9, 19),
    )
    assert recovered["catalog_sku"] == "989101156"
    assert related_calls == [("989101156",)]


def test_selected_scope_missing_identity_fails_without_fbo_page_scan():
    service = _service()
    selected = service._catalog_by_sku["989101156"]
    calls = {"related": 0, "fbo_list": 0}

    def related(skus):
        calls["related"] += 1
        return {
            "error": False,
            "items": [{
                "sku": skus[0],
                "product_id": (
                    "current-product" if skus == ["989101156"] else "other"
                ),
            }],
            "errors": [],
        }

    def fbo_list(*_args, **_kwargs):
        calls["fbo_list"] += 1
        return {"error": False, "result": {"postings": [], "has_next": False}}

    service.finance_service.ozon.get_related_skus = related
    service.finance_service.ozon.get_realization_posting = lambda *_args: {
        "error": True,
    }
    service.finance_service.ozon.get_fbo_postings = fbo_list

    result = service._selected_finance_sku_candidates(
        {"legacy-finance-sku"},
        selected,
        date(2026, 9, 19),
    )

    assert result == set()
    assert calls == {"related": 2, "fbo_list": 0}


def test_directional_related_identity_is_found_with_bounded_batch_bisection():
    service = _service()
    selected = service._catalog_by_sku["989101156"]
    all_skus = {
        "unrelated-%03d" % index for index in range(500)
    } | {"legacy-finance-sku"}
    calls = []

    def related(skus):
        calls.append(tuple(skus))
        # The production failure is directional: asking for the current SKU
        # does not return its historical finance SKU. Asking a batch containing
        # the historical SKU does return the current member of that relation.
        if skus == ["989101156"]:
            items = [{"sku": "989101156", "product_id": "current-product"}]
        elif "legacy-finance-sku" in skus:
            items = [
                {"sku": "legacy-finance-sku", "product_id": "old-product"},
                {"sku": "989101156", "product_id": "current-product"},
            ]
        else:
            items = [{"sku": sku, "product_id": "other"} for sku in skus]
        return {"error": False, "items": items, "errors": []}

    service.finance_service.ozon.get_related_skus = related
    service.finance_service.ozon.get_realization_posting = lambda *_args: {
        "error": True,
    }
    service.finance_service.ozon.get_fbo_postings = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("selected scope must not list FBO"))
    )

    result = service._selected_finance_sku_candidates(
        all_skus,
        selected,
        date(2026, 9, 19),
    )

    assert result == {"legacy-finance-sku"}
    assert calls[0] == ("989101156",)
    assert ("legacy-finance-sku",) in calls
    assert len(calls) <= 24
    recovered = service._recover_missing_product(
        "legacy-finance-sku",
        date(2026, 9, 19),
    )
    assert recovered["catalog_sku"] == "989101156"


def test_selected_scope_uses_batched_finance_posting_sku_evidence_first():
    service = _service()
    selected = service._catalog_by_sku["989101156"]
    all_skus = {
        "unrelated-%03d" % index for index in range(500)
    } | {"legacy-finance-sku"}
    service._finance_posting_numbers_by_sku = {
        sku: {"posting-" + sku} for sku in all_skus
    }
    evidence_calls = []

    def evidence(posting_numbers):
        evidence_calls.append(tuple(posting_numbers))
        return {
            "error": False,
            "complete": True,
            "records": [{
                "posting_number": posting_number,
                "sku": (
                    "989101156"
                    if posting_number == "posting-legacy-finance-sku"
                    else posting_number.removeprefix("posting-")
                ),
                "quantity": 1,
            } for posting_number in posting_numbers],
        }

    service.finance_service.get_sale_posting_quantity_evidence = evidence
    service.finance_service.ozon.get_realization_posting = lambda *_args: {
        "error": True,
    }
    service.finance_service.ozon.get_related_skus = lambda _skus: (
        (_ for _ in ()).throw(AssertionError("related fallback must be skipped"))
    )
    service.finance_service.ozon.get_fbo_postings = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("selected scope must not list FBO"))
    )

    result = service._selected_finance_sku_candidates(
        all_skus,
        selected,
        date(2026, 9, 19),
    )

    assert result == {"legacy-finance-sku"}
    assert len(evidence_calls) == 1
    assert len(evidence_calls[0]) == 501
    recovered = service._recover_missing_product(
        "legacy-finance-sku",
        date(2026, 9, 19),
    )
    assert recovered["catalog_sku"] == "989101156"
    assert len(evidence_calls) == 1


def test_posting_sku_evidence_rejects_shared_posting_owner():
    service = _service()
    selected = service._catalog_by_sku["989101156"]
    service._finance_posting_numbers_by_sku = {
        "legacy-finance-sku": {"shared-posting"},
        "other-finance-sku": {"shared-posting"},
    }
    service.finance_service.get_sale_posting_quantity_evidence = lambda _numbers: {
        "error": False,
        "complete": True,
        "records": [{
            "posting_number": "shared-posting",
            "sku": "989101156",
            "quantity": 1,
        }],
    }

    result = service._selected_finance_posting_sku_candidates(
        {"legacy-finance-sku", "other-finance-sku"},
        selected,
    )

    assert result == set()
