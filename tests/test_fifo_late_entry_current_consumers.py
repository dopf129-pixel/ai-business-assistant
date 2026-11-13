from pathlib import Path
from types import SimpleNamespace

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
from services.ozon_account_repository import make_store_tenant_scope
from services.product_unit_economics_query_service import ProductUnitEconomicsQueryService
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)
from services.tenant_context import reset_current_tenant_user_id
from test_fifo_cost_transition_atomic_apply import (
    SCOPE,
    STORE,
    _commit,
    _prepared_repository,
)
from test_product_unit_economics_query_cache import FakeProvider


class _LegacyCosts:
    def get_current_cost_date(self):
        return "2026-11-08"

    def get_cost(self, product_id):
        return (
            str(product_id), SCOPE.sku, SCOPE.offer_id, "21.00", "RUB",
            "2026-11-01",
        )


class _Products:
    def load_products(self):
        return [{
            "product_id": SCOPE.product_id,
            "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku,
        }]


class _CurrentSource:
    def __init__(self):
        self.calls = 0

    def get(self, **_kwargs):
        self.calls += 1
        return {
            "error": False,
            "seller_price": 100.0,
            "product_id": SCOPE.product_id,
            "sku": SCOPE.sku,
            "missing_data": [],
        }


def test_draft_keeps_legacy_cost_and_applied_revision_refreshes_unit_economics_cache(
    tmp_path: Path,
):
    repository, tenant, _stock, bridge, impact, _cutover, prepared, _clock = (
        _prepared_repository(tmp_path)
    )
    source = _CurrentSource()
    adapter = FifoCurrentUnitCostAdapter(
        _LegacyCosts(), FifoCostHistoryService(repository),
    )
    service = ProductUnitEconomicsQueryService(
        product_service=_Products(),
        period_profit_service=None,
        analytics_service=None,
        unit_economics_provider=FakeProvider(),
        current_economics_source=source,
        cost_service=_LegacyCosts(),
        cost_adapter=adapter,
        returns_finance_impact_query=None,
        cache_ttl_seconds=600,
    )
    try:
        first = service.query(SCOPE.offer_id)
        cached = service.query(SCOPE.offer_id)

        assert first["cost"] == 21.0
        assert first["cost_method"] == "LEGACY_EFFECTIVE_DATED"
        assert cached["cost_revision"] == first["cost_revision"]
        assert cached["cache"]["status"] == "hit"
        assert source.calls == 1
        assert first["_cost_cache_identity"] == {
            "store_id": STORE,
            "product_id": SCOPE.product_id,
            "offer_id": SCOPE.offer_id,
            "sku": SCOPE.sku,
        }

        applied = _commit(repository, bridge, impact, prepared)
        assert applied["error"] is False

        refreshed = service.query(SCOPE.offer_id)
    finally:
        reset_current_tenant_user_id(tenant)

    assert refreshed["cost"] == 14.65
    assert refreshed["cost_method"] == "FIFO_FINITE_LAYER"
    assert refreshed["cost_revision"] != first["cost_revision"]
    assert refreshed["cache"]["status"] == "miss"
    assert len(service._query_cache) == 1
    assert source.calls == 2


def test_successful_runtime_apply_requests_exact_fifo_snapshot_invalidation():
    identity = {
        "store_id": STORE, "product_id": SCOPE.product_id,
        "offer_id": SCOPE.offer_id, "sku": SCOPE.sku,
    }
    invalidations = []
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition_service=object(),
        history_service=object(),
        apply_service=SimpleNamespace(apply=lambda **_kwargs: {"error": False}),
        cache_invalidator=lambda value: invalidations.append(value),
    )
    runtime._read_case = lambda *_args: {
        "error": False, "state": "READY_TO_CONFIRM", "case_revision": 8,
    }
    runtime._refresh_session = lambda *_args: None
    runtime._show_summary = lambda *_args: {"status": "FIFO_TRANSITION_APPLIED"}
    session = {"case_id": "case-1", "identity": identity}

    result = runtime._apply_transition(
        "owner", "owner", session, {"case_revision": 8},
    )

    assert result["status"] == "FIFO_TRANSITION_APPLIED"
    assert invalidations == [identity]

