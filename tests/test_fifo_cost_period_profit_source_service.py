from services.fifo_cost_period_profit_source_service import (
    FifoCostPeriodProfitSourceService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.ozon_account_repository import make_store_tenant_scope


class _Repository:
    def __init__(
        self, *, active=True, complete=True, allocations=None, cutoff_date=None,
    ):
        self.active = active
        self.complete = complete
        self.allocations = allocations or []
        self.cutoff_date = cutoff_date
        self.summary_calls = 0
        self.summary_scope_calls = []
        self.mode_calls = []

    def read_cost_mode_status(self, **kwargs):
        self.mode_calls.append(dict(kwargs))
        return {
            "error": False, "active": self.active,
            "code": "FIFO_COST_MODE_FIFO" if self.active else "FIFO_COST_MODE_LEGACY",
            "stream_state": "FIFO_READY", "stream_revision": 4,
            "cutoff_date": self.cutoff_date,
        }

    def read_period_allocation_summary(self, **kwargs):
        self.summary_calls += 1
        self.summary_scope_calls.append(dict(kwargs))
        return {
            "error": False, "active": self.active,
            "complete": self.complete,
            "reason_code": "FIFO_ALLOCATION_STALE_OR_MISSING",
            "stream_revision": 4, "allocation_revision": 2,
            "cutoff_date": "2026-11-01", "allocations": self.allocations,
        }


def _digest(*, posting_number="opaque-posting", finance_sku="sku-1"):
    return FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id="store-a", posting_number=posting_number,
        finance_sku=finance_sku, identity={
            "mapping_confirmed": True,
            "offer_id": "offer-1", "product_id": "product-1",
        },
    )["source_identity_digest"]


def _service(repository=None, tenant=None):
    return FifoCostPeriodProfitSourceService(
        repository=repository or _Repository(),
        tenant_scope_provider=lambda: tenant or make_store_tenant_scope(
            "owner-1", "store-a",
        ),
    )


def _product():
    return {"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"}


def test_fifo_period_source_matches_exact_sale_identity_and_allocation_revision():
    service = _service(_Repository(allocations=[{
        "source_identity_digest": _digest(),
        "effective_date": "2026-11-02", "quantity": 2,
        "total_cogs_rub": "20.00",
    }]))
    result = service.reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )

    assert result == {
        "error": False, "active": True, "complete": True,
        "source": "FIFO_ALLOCATION_REVISION", "stream_revision": 4,
        "allocation_revision": 2, "cutoff_date": "2026-11-01",
        "units_sold": 2, "product_cost": "20.00",
    }


def test_fc28_fifo_period_source_attaches_confirmed_layers_and_correction_history():
    class DetailedRepository(_Repository):
        def read_period_allocation_summary(self, **_kwargs):
            return {
                "error": False, "active": True, "complete": True,
                "stream_revision": 4, "allocation_revision": 2,
                "cutoff_date": "2026-11-01",
                "allocations": [{
                    "source_identity_digest": _digest(),
                    "effective_date": "2026-11-02", "quantity": 2,
                    "total_cogs_rub": "20.00",
                }],
                "layers": [{
                    "basis_ref": "fifo-basis-00000000000000000001",
                    "basis_kind": "LAYER", "sequence": 1,
                    "effective_date": "2026-11-01",
                    "provenance": "OWNER_CONFIRMED",
                    "source_method": "OWNER_CONFIRMED_FIFO_CUTOFF",
                    "source_status": "OWNER_CONFIRMED",
                    "coverage_status": "OWNER_CONFIRMED",
                    "quantity": 2, "unit_cost_rub": "10.00",
                    "total_cogs_rub": "20.00",
                }],
                "layer_breakdown_complete": True,
            }

        def read_late_entry_corrections(self, **_kwargs):
            return {"error": False, "corrections": []}

    result = _service(DetailedRepository()).reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )

    assert result["complete"] is True
    assert result["product_cost"] == "20.00"
    assert result["fifo_cost_explanation"]["status"] == "CONFIRMED"
    assert result["fifo_cost_explanation"]["layers"][0]["total_cogs_rub"] == "20.00"
    assert result["fifo_cost_explanation"]["corrections"]["status"] == "NO_CORRECTION"


def test_fc28_bad_layer_explanation_does_not_change_confirmed_fifo_cogs():
    class InvalidLayerRepository(_Repository):
        def read_period_allocation_summary(self, **_kwargs):
            return {
                "error": False, "active": True, "complete": True,
                "stream_revision": 4, "allocation_revision": 2,
                "cutoff_date": "2026-11-01",
                "allocations": [{
                    "source_identity_digest": _digest(),
                    "effective_date": "2026-11-02", "quantity": 2,
                    "total_cogs_rub": "20.00",
                }],
                "layers": [], "layer_breakdown_complete": False,
            }

        def read_late_entry_corrections(self, **_kwargs):
            return {"error": False, "corrections": []}

    result = _service(InvalidLayerRepository()).reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )

    assert result["complete"] is True
    assert result["product_cost"] == "20.00"
    assert result["fifo_cost_explanation"]["status"] == "PARTIAL"
    assert result["fifo_cost_explanation"]["product_cost_rub"] == "20.00"


def test_active_fifo_scope_never_falls_back_when_allocation_is_stale():
    service = _service(_Repository(complete=False))
    result = service.reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )
    assert result["active"] is True
    assert result["complete"] is False
    assert result["reason_code"] == "FIFO_ALLOCATION_STALE_OR_MISSING"


def test_fifo_join_mismatch_fails_closed_instead_of_using_current_cost():
    service = _service(_Repository(allocations=[{
        "source_identity_digest": "f" * 64,
        "effective_date": "2026-11-02", "quantity": 2,
        "total_cogs_rub": "20.00",
    }]))
    result = service.reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )
    assert result["active"] is True
    assert result["complete"] is False
    assert result["reason_code"] == "FIFO_ALLOCATION_SALE_COVERAGE_MISMATCH"


def test_uninitialized_scope_stays_on_legacy_cost_mode():
    service = _service(_Repository(active=False))
    result = service.get_scope_mode(_product())
    assert result["error"] is False
    assert result["active"] is False


def test_confirmed_historical_finance_sku_mapping_selects_catalog_fifo_stream():
    repository = _Repository(active=True, allocations=[{
        "source_identity_digest": _digest(
            posting_number="mapped-posting", finance_sku="old-finance-sku",
        ),
        "effective_date": "2026-11-02", "quantity": 1,
        "total_cogs_rub": "20.00",
    }])
    service = _service(repository)
    product = {
        "product_id": "product-1",
        "offer_id": "offer-1",
        "sku": "old-finance-sku",
        "catalog_sku": "current-catalog-sku",
        "historical_sku_identity_recovered": True,
        "historical_sku_identity_source": (
            "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
        ),
    }

    result = service.get_scope_mode(product)

    assert result["error"] is False
    assert result["active"] is True
    assert result["sku"] == "current-catalog-sku"
    assert repository.mode_calls[0]["sku"] == "current-catalog-sku"

    reconciled = service.reconcile_period_sales(
        product=product,
        finance_sku="old-finance-sku",
        date_from="2026-11-02",
        date_to="2026-11-02",
        sales=[{"posting_number": "mapped-posting", "quantity": 1}],
    )
    assert reconciled["error"] is False
    assert reconciled["active"] is True
    assert reconciled["complete"] is True
    assert reconciled["product_cost"] == "20.00"
    assert repository.mode_calls[-1]["sku"] == "current-catalog-sku"
    assert repository.summary_scope_calls[0]["sku"] == "current-catalog-sku"


def test_confirmed_finance_sku_aliases_reconcile_together_and_return_per_alias_cogs():
    aliases = [
        {
            "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
            "catalog_sku": "current-catalog-sku",
            "historical_sku_identity_recovered": True,
            "historical_sku_identity_source": (
                "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
            ),
        }
        for sku in ("old-finance-sku-a", "old-finance-sku-b")
    ]
    allocations = [
        {
            "source_identity_digest": _digest(
                posting_number="posting-a", finance_sku="old-finance-sku-a",
            ),
            "effective_date": "2026-11-02", "quantity": 2,
            "total_cogs_rub": "20.00",
        },
        {
            "source_identity_digest": _digest(
                posting_number="posting-b", finance_sku="old-finance-sku-b",
            ),
            "effective_date": "2026-11-02", "quantity": 1,
            "total_cogs_rub": "15.00",
        },
    ]
    service = _service(_Repository(allocations=allocations))
    sales = [
        {"posting_number": "posting-a", "sku": "old-finance-sku-a", "quantity": 2},
        {"posting_number": "posting-b", "sku": "old-finance-sku-b", "quantity": 1},
    ]

    by_alias = {
        sku: service.reconcile_period_sales(
            product=aliases[0], finance_sku=sku,
            finance_sku_alias_products=aliases,
            date_from="2026-11-02", date_to="2026-11-02", sales=sales,
        )
        for sku in ("old-finance-sku-a", "old-finance-sku-b")
    }

    assert by_alias["old-finance-sku-a"]["complete"] is True
    assert by_alias["old-finance-sku-a"]["units_sold"] == 2
    assert by_alias["old-finance-sku-a"]["product_cost"] == "20.00"
    assert by_alias["old-finance-sku-b"]["complete"] is True
    assert by_alias["old-finance-sku-b"]["units_sold"] == 1
    assert by_alias["old-finance-sku-b"]["product_cost"] == "15.00"
    # Stream-wide layer summaries cannot be safely attributed to one alias.
    assert "fifo_cost_explanation" not in by_alias["old-finance-sku-a"]


def test_alias_reconciliation_still_rejects_missing_or_unexpected_allocations():
    aliases = [
        {
            "product_id": "product-1", "offer_id": "offer-1", "sku": sku,
            "catalog_sku": "current-catalog-sku",
            "historical_sku_identity_recovered": True,
            "historical_sku_identity_source": (
                "OZON_FINANCE_POSTING_TO_CURRENT_CATALOG_OFFER_ID"
            ),
        }
        for sku in ("old-finance-sku-a", "old-finance-sku-b")
    ]
    sales = [
        {"posting_number": "posting-a", "sku": "old-finance-sku-a", "quantity": 1},
        {"posting_number": "posting-b", "sku": "old-finance-sku-b", "quantity": 1},
    ]
    complete_allocations = [
        {
            "source_identity_digest": _digest(
                posting_number=f"posting-{letter}",
                finance_sku=f"old-finance-sku-{letter}",
            ),
            "effective_date": "2026-11-02", "quantity": 1,
            "total_cogs_rub": "10.00",
        }
        for letter in ("a", "b")
    ]
    cases = (
        complete_allocations[:1],
        complete_allocations + [{
            "source_identity_digest": "f" * 64,
            "effective_date": "2026-11-02", "quantity": 1,
            "total_cogs_rub": "10.00",
        }],
    )

    for allocations in cases:
        result = _service(_Repository(allocations=allocations)).reconcile_period_sales(
            product=aliases[0], finance_sku="old-finance-sku-a",
            finance_sku_alias_products=aliases,
            date_from="2026-11-02", date_to="2026-11-02", sales=sales,
        )
        assert result["complete"] is False
        assert result["reason_code"] == "FIFO_ALLOCATION_SALE_COVERAGE_MISMATCH"


def test_unconfirmed_catalog_sku_alias_blocks_instead_of_falling_back_to_legacy():
    repository = _Repository(active=False)
    service = _service(repository)
    product = {
        "product_id": "product-1",
        "offer_id": "offer-1",
        "sku": "old-finance-sku",
        "catalog_sku": "unverified-catalog-sku",
        "historical_sku_identity_recovered": True,
        "historical_sku_identity_source": "UNRECOGNIZED_MAPPING_SOURCE",
    }

    result = service.get_scope_mode(product)

    assert result == {
        "error": True, "code": "FIFO_COST_PRODUCT_IDENTITY_INVALID",
    }
    assert repository.mode_calls == []


def test_pre_cutoff_period_uses_legacy_mode_after_fifo_was_activated():
    repository = _Repository(active=True, cutoff_date="2026-11-05")
    service = _service(repository)

    mode = service.get_scope_mode(
        _product(), date_from="2026-10-01", date_to="2026-11-05",
    )
    result = service.reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-10-01", date_to="2026-11-05",
        sales=[{"posting_number": "opaque-posting", "quantity": 2}],
    )

    assert mode["error"] is False
    assert mode["active"] is False
    assert mode["code"] == "FIFO_COST_MODE_PRE_CUTOFF"
    assert result == {"error": False, "active": False, "code": "FIFO_COST_MODE_PRE_CUTOFF"}
    assert repository.summary_calls == 0


def test_period_spanning_fifo_cutoff_fails_closed_and_post_cutoff_uses_fifo():
    repository = _Repository(active=True, cutoff_date="2026-11-05")
    service = _service(repository)
    sales = [{"posting_number": "opaque-posting", "quantity": 2}]

    overlap_mode = service.get_scope_mode(
        _product(), date_from="2026-11-05", date_to="2026-11-06",
    )
    overlap = service.reconcile_period_sales(
        product=_product(), finance_sku="sku-1",
        date_from="2026-11-05", date_to="2026-11-06", sales=sales,
    )
    post_cutoff = service.get_scope_mode(
        _product(), date_from="2026-11-06", date_to="2026-11-06",
    )

    assert overlap_mode["period_cutover_overlap"] is True
    assert overlap_mode["code"] == "FIFO_PERIOD_SPANS_COST_CUTOFF"
    assert overlap["active"] is True
    assert overlap["complete"] is False
    assert overlap["reason_code"] == "FIFO_PERIOD_SPANS_COST_CUTOFF"
    assert repository.summary_calls == 0
    assert post_cutoff["active"] is True


def test_fifo_scope_requires_active_store_and_stable_product_identity():
    no_store = _service(tenant="owner-1").get_scope_mode(_product())
    no_identity = _service().reconcile_period_sales(
        product={"sku": "sku-1"}, finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 1}],
    )
    assert no_store == {"error": True, "code": "FIFO_ACTIVE_STORE_SCOPE_UNAVAILABLE"}
    assert no_identity == {"error": True, "code": "FIFO_COST_PRODUCT_IDENTITY_INVALID"}
