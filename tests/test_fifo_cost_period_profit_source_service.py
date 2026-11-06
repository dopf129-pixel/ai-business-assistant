from services.fifo_cost_period_profit_source_service import (
    FifoCostPeriodProfitSourceService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.ozon_account_repository import make_store_tenant_scope


class _Repository:
    def __init__(self, *, active=True, complete=True, allocations=None):
        self.active = active
        self.complete = complete
        self.allocations = allocations or []

    def read_cost_mode_status(self, **_kwargs):
        return {
            "error": False, "active": self.active,
            "code": "FIFO_COST_MODE_FIFO" if self.active else "FIFO_COST_MODE_LEGACY",
            "stream_state": "FIFO_READY", "stream_revision": 4,
        }

    def read_period_allocation_summary(self, **_kwargs):
        return {
            "error": False, "active": self.active,
            "complete": self.complete,
            "reason_code": "FIFO_ALLOCATION_STALE_OR_MISSING",
            "stream_revision": 4, "allocation_revision": 2,
            "cutoff_date": "2026-11-01", "allocations": self.allocations,
        }


def _digest():
    return FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id="store-a", posting_number="opaque-posting",
        finance_sku="sku-1", identity={
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


def test_fifo_scope_requires_active_store_and_stable_product_identity():
    no_store = _service(tenant="owner-1").get_scope_mode(_product())
    no_identity = _service().reconcile_period_sales(
        product={"sku": "sku-1"}, finance_sku="sku-1",
        date_from="2026-11-02", date_to="2026-11-02",
        sales=[{"posting_number": "opaque-posting", "quantity": 1}],
    )
    assert no_store == {"error": True, "code": "FIFO_ACTIVE_STORE_SCOPE_UNAVAILABLE"}
    assert no_identity == {"error": True, "code": "FIFO_COST_PRODUCT_IDENTITY_INVALID"}
