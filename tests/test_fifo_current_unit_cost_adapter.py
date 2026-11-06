from datetime import date, datetime, timezone
from copy import deepcopy

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoStockSnapshot
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


class _LegacyCosts:
    def __init__(self, cost="42.50"):
        self.cost = cost

    def get_current_cost_date(self):
        return "2026-11-06"

    def get_cost(self, product_id):
        if str(product_id) != IDENTITY["product_id"] or self.cost is None:
            return None
        return (
            product_id, IDENTITY["sku"], IDENTITY["offer_id"], self.cost, "RUB",
            "2026-10-01",
        )


def _repository(tmp_path):
    return FifoCostRepository(
        db_path=tmp_path / "fifo-current-cost.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )


def _anchor(repository, *, store_id="store-a", cost="10.00", home=0):
    anchor = FifoCostAnchorService(repository)
    preview = anchor.preview_opening_anchor(
        **IDENTITY,
        store_id=store_id,
        inventory_cutoff="2026-11-05",
        cost_layers=[{
            "sequence": 1,
            "unit_cost_rub": cost,
            "ozon_units": 10,
            "transit_units": 0,
            "home_units": home,
        }],
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert preview["error"] is False
    result = anchor.commit_opening_anchor(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="adapter-anchor01",
    )
    assert result["error"] is False
    return result


def _adapter(repository, legacy=None):
    return FifoCurrentUnitCostAdapter(
        legacy or _LegacyCosts(),
        FifoCostHistoryService(repository),
    )


def test_uninitialized_exact_store_sku_preserves_legacy_cost_behavior(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        adapter = _adapter(_repository(tmp_path))
        result = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["cost_per_unit_rub"] == "42.50"
    assert result["cost_method"] == "LEGACY_EFFECTIVE_DATED"
    assert result["cost_basis"]["completeness"] == "LEGACY_EFFECTIVE_COST_CONFIRMED"
    assert result["cost_basis"]["factual_period_profit_eligible"] is False


def test_fifo_old_finite_layer_precedes_future_rate_and_exposes_remaining_units(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _repository(tmp_path)
        _anchor(repository)
        adapter = _adapter(repository, _LegacyCosts(cost="99.00"))
        before_rate = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
        rates = FifoCostRateService(repository)
        preview = rates.preview_new_cost(
            **IDENTITY,
            store_id="store-a",
            effective_date="2026-11-07",
            purchase_cost_rub="12.00",
            delivery_cost_rub="2.00",
            packaging_cost_rub="1.00",
            old_home_units=0,
            expected_revision=1,
        )
        assert preview["error"] is False
        committed = rates.confirm_new_cost(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="adapter-planned-rate01",
        )
        assert committed["error"] is False

        result = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
        after_effective_date = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-07",
        )
    finally:
        reset_current_tenant_user_id(token)

    basis = result["cost_basis"]
    assert before_rate["cost_revision"] != result["cost_revision"]
    assert result["cost_per_unit_rub"] == "10.00"
    assert basis["method"] == "FIFO_FINITE_LAYER"
    assert basis["next_layer_remaining_units"] == 10
    assert basis["next_planned_rate"]["unit_cost_rub"] == "15.00"
    assert basis["next_planned_rate"]["effective_date"] == "2026-11-07"
    assert basis["completeness"] == "CONFIRMED_SNAPSHOT_MODEL_ONLY"
    assert basis["factual_period_profit_eligible"] is False
    assert after_effective_date["cost_per_unit_rub"] == "10.00"
    assert after_effective_date["cost_basis"]["next_layer_remaining_units"] == 10
    assert after_effective_date["cost_revision"] != result["cost_revision"]


def test_existing_fifo_stream_with_unreplayed_movement_does_not_fall_back(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _repository(tmp_path)
        _anchor(repository, home=4)
        preview = repository.preview_command(
            store_id="store-a",
            **IDENTITY,
            events=[{
                "kind": "INVENTORY_TRANSFER",
                "quantity": 1,
                "effective_date": "2026-11-06",
                "location_from": "HOME",
                "location_to": "TRANSIT",
            }],
            source={
                "kind": "OWNER_CONFIRMATION",
                "method": "OWNER_CONFIRMED_TEST_MOVEMENT",
                "status": "OWNER_CONFIRMED",
                "completeness": "OWNER_CONFIRMED",
                "provenance": "OWNER_CONFIRMED",
                "coverage_status": "OWNER_CONFIRMED",
                "captured_at": "2026-11-06T11:00:00Z",
                "references": [],
            },
            expected_revision=1,
        )
        assert preview["error"] is False
        committed = repository.commit_command(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="adapter-movement01",
        )
        assert committed["error"] is False
        adapter = _adapter(repository, _LegacyCosts(cost="99.00"))
        result = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert result["cost_per_unit_rub"] is None
    assert result["cost_method"] == "FIFO_UNAVAILABLE"
    assert result["cost_basis"]["completeness"] == "REPLAY_REQUIRED"
    assert result["cost_basis"]["reason_code"] == "FIFO_COST_MOVEMENT_REPLAY_REQUIRED"
    assert result["cost_basis"]["quantity_allocation_basis"]["status"] == "UNAVAILABLE"


def test_quantity_basis_materializes_reconciled_prior_rate_as_a_finite_fifo_layer(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _repository(tmp_path)
        anchor_preview = FifoCostAnchorService(repository).preview_opening_anchor(
            **IDENTITY,
            store_id="store-a",
            inventory_cutoff="2026-11-05",
            cost_layers=[{
                "sequence": 1, "unit_cost_rub": "20.00", "ozon_units": 150,
                "transit_units": 0, "home_units": 0,
            }],
            ozon_units_include_reserved_confirmed=True,
            transit_not_in_ozon_confirmed=True,
        )
        anchor = FifoCostAnchorService(repository).commit_opening_anchor(
            preview_id=anchor_preview["preview_id"],
            active_preview_id=anchor_preview["preview_id"],
            idempotency_key="quantity-basis-anchor01",
        )
        assert anchor["error"] is False
        rates = FifoCostRateService(repository)
        first = rates.preview_new_cost(
            **IDENTITY, store_id="store-a", effective_date="2026-11-06",
            purchase_cost_rub="25.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=0, expected_revision=1,
        )
        assert first["error"] is False
        assert rates.confirm_new_cost(
            preview_id=first["preview_id"], active_preview_id=first["preview_id"],
            idempotency_key="quantity-basis-rate-two",
        )["error"] is False
        repository._now_provider = lambda: datetime(
            2026, 11, 7, 12, tzinfo=timezone.utc,
        )
        stock = FifoStockSnapshot(
            status="COMPLETE", source_status="COMPLETE", store_id="store-a",
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"], captured_at="2026-11-07T12:00:00Z",
            source_as_of=None, pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=300, reserved_units=40, available_units=260, transit_units=0,
            transit_status="DISJOINT_CONFIRMED", source_fingerprint="b" * 64,
            issue_codes=(), anchor_eligible=False,
        )
        second = rates.preview_new_cost(
            **IDENTITY, store_id="store-a", effective_date="2026-11-07",
            purchase_cost_rub="30.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=50, expected_revision=2,
            stock_snapshot=stock, owner_confirms_reconciliation_scope=True,
        )
        assert second["error"] is False
        assert second["rate_reconciliation"]["prior_rate_units"] == 200
        assert rates.confirm_new_cost(
            preview_id=second["preview_id"], active_preview_id=second["preview_id"],
            idempotency_key="quantity-basis-rate-three",
        )["error"] is False

        result = _adapter(repository).resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-07",
        )
    finally:
        reset_current_tenant_user_id(token)

    basis = result["cost_basis"]["quantity_allocation_basis"]
    assert basis["status"] == "AVAILABLE"
    assert [(row["quantity"], row["unit_cost_rub"], row["kind"]) for row in basis["layers"]] == [
        (150, "20.00", "FINITE_LAYER"),
        (200, "25.00", "RECONCILED_RATE"),
    ]
    assert basis["open_rate"] == {
        "unit_cost_rub": "30.00", "effective_date": "2026-11-07",
    }
    assert basis["revision"] == result["cost_revision"]
    assert basis["factual_period_profit_eligible"] is False


def test_zero_stock_cutoff_is_persisted_and_reconciled_old_rate_is_next_fifo_layer(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _repository(tmp_path)
        rates = FifoCostRateService(repository)
        zero = FifoStockSnapshot(
            status="CONFIRMED_ZERO", source_status="COMPLETE", store_id="store-a",
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"], captured_at="2026-11-06T12:00:00Z",
            source_as_of=None, pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=0, reserved_units=0, available_units=0, transit_units=0,
            transit_status="DISJOINT_CONFIRMED", source_fingerprint="a" * 64,
            issue_codes=(), anchor_eligible=False,
        )
        first = rates.preview_new_cost(
            **IDENTITY, store_id="store-a", effective_date="2026-11-06",
            purchase_cost_rub="20.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=0,
            expected_revision=0, zero_stock_snapshot=zero,
        )
        assert first["error"] is False, first
        assert rates.confirm_new_cost(
            preview_id=first["preview_id"], active_preview_id=first["preview_id"],
            idempotency_key="zero-cutoff-first-rate",
        )["error"] is False

        adapter = _adapter(repository)
        first_cost = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
        assert first_cost["cost_basis"]["cutoff_date"] == "2026-11-06"
        assert first_cost["cost_basis"]["quantity_allocation_basis"]["status"] == "AVAILABLE"
        assert first_cost["cost_basis"]["quantity_allocation_basis"]["layers"] == []

        repository._now_provider = lambda: datetime(
            2026, 11, 7, 12, tzinfo=timezone.utc,
        )
        stock = FifoStockSnapshot(
            status="COMPLETE", source_status="COMPLETE", store_id="store-a",
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"], captured_at="2026-11-07T12:00:00Z",
            source_as_of=None, pagination_complete=True, pages_read=1, total_items=1,
            fbo_units=100, reserved_units=0, available_units=100, transit_units=0,
            transit_status="DISJOINT_CONFIRMED", source_fingerprint="b" * 64,
            issue_codes=(), anchor_eligible=False,
        )
        second = rates.preview_new_cost(
            **IDENTITY, store_id="store-a", effective_date="2026-11-07",
            purchase_cost_rub="30.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=0,
            expected_revision=1, stock_snapshot=stock,
            owner_confirms_reconciliation_scope=True,
        )
        assert second["error"] is False, second
        assert second["rate_reconciliation"]["prior_rate_units"] == 100
        assert rates.confirm_new_cost(
            preview_id=second["preview_id"], active_preview_id=second["preview_id"],
            idempotency_key="zero-cutoff-second-rate",
        )["error"] is False

        result = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-07",
        )
    finally:
        reset_current_tenant_user_id(token)

    basis = result["cost_basis"]["quantity_allocation_basis"]
    assert result["cost_per_unit_rub"] == "20.00"
    assert result["cost_basis"]["next_unit_cost_basis"] == "RECONCILED_RATE_LAYER"
    assert result["cost_basis"]["cutoff_date"] == "2026-11-06"
    assert basis["status"] == "AVAILABLE"
    assert basis["layers"] == [{
        "sequence": 1, "kind": "RECONCILED_RATE", "quantity": 100,
        "unit_cost_rub": "20.00", "effective_date": "2026-11-06",
    }]
    assert basis["open_rate"] == {
        "unit_cost_rub": "30.00", "effective_date": "2026-11-07",
    }


def test_current_unit_cost_uses_remaining_layer_from_fresh_completed_replay():
    class ReplayedHistory:
        def get_sku_history(self, **_kwargs):
            return {
                "error": False, "code": "FIFO_HISTORY_READY", "revision": 5,
                "queue_initialized": True, "stream_state": "FIFO_READY",
                "cutoff_date": "2026-11-05", "projection": {},
                "movement_count": 2, "remaining_status": "AFTER_CONFIRMED_REPLAY",
                "next_unit_cost_rub": "20.00",
                "next_unit_cost_basis": "FINITE_FIFO_LAYER",
                "layers": [
                    {"sequence": 1, "recorded_quantity": 1, "remaining_units": 0,
                     "unit_cost_rub": "10.00", "effective_date": "2026-11-05"},
                    {"sequence": 2, "recorded_quantity": 2, "remaining_units": 1,
                     "unit_cost_rub": "20.00", "effective_date": "2026-11-06"},
                ],
                "reconciled_rate_layers": [], "rates": [],
                "rate_reconciliations": [], "rate_cancellations": [],
                "active_rate": None, "next_planned_rate": None,
                "latest_allocation": {
                    "revision": 3, "stream_revision": 5, "status": "COMPLETE",
                    "cutoff_status": "RECONCILED", "stale": False,
                },
            }

    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        adapter = FifoCurrentUnitCostAdapter(_LegacyCosts(cost="99.00"), ReplayedHistory())
        result = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(tenant)

    assert result["cost_per_unit_rub"] == "20.00"
    assert result["cost_basis"]["next_layer_remaining_units"] == 1
    assert result["cost_basis"]["completeness"] == "CONFIRMED_REPLAY_MODEL_ONLY"
    assert result["cost_basis"]["factual_period_profit_eligible"] is False
    assert result["cost_basis"]["quantity_allocation_basis"]["status"] == "UNAVAILABLE"


def test_fifo_history_is_exact_store_scoped_without_cross_store_fallback(tmp_path):
    tenant_a = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        repository = _repository(tmp_path)
        _anchor(repository)
        adapter = _adapter(repository, _LegacyCosts(cost="99.00"))
        fifo = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date=date(2026, 11, 6),
        )
        other_store = adapter.resolve_current_cost(
            IDENTITY, store_id="store-b", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(tenant_a)

    tenant_b = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-b"))
    try:
        _anchor(repository, store_id="store-b", cost="20.00")
        adapter = _adapter(repository, _LegacyCosts(cost="77.00"))
        resolved_b = adapter.resolve_current_cost(
            IDENTITY, store_id="store-b", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(tenant_b)

    assert fifo["cost_per_unit_rub"] == "10.00"
    assert other_store["cost_per_unit_rub"] is None
    assert other_store["cost_basis"]["reason_code"] == "FIFO_COST_STORE_SCOPE_MISMATCH"
    assert resolved_b["cost_per_unit_rub"] == "20.00"
    assert fifo["cost_revision"] != resolved_b["cost_revision"]


def test_fifo_cost_revision_fingerprints_full_sanitized_history_for_restore_invalidation():
    class _MutableHistory:
        def __init__(self):
            self.snapshot = {
                "error": False,
                "code": "FIFO_HISTORY_READY",
                "revision": 7,
                "as_of_date": "2026-11-06",
                "queue_initialized": True,
                "stream_state": "FIFO_READY",
                "cutoff_date": "2026-11-05",
                "projection": {"remaining_units": 15},
                "layers": [
                    {"sequence": 1, "unit_cost_rub": "10.00", "recorded_quantity": 10, "remaining_units": 10},
                    {"sequence": 2, "unit_cost_rub": "20.00", "recorded_quantity": 5, "remaining_units": 5},
                ],
                "rates": [],
                "rate_reconciliations": [],
                "rate_cancellations": [],
                "active_rate": None,
                "next_planned_rate": None,
                "next_unit_cost_rub": "10.00",
                "next_unit_cost_basis": "FINITE_FIFO_LAYER",
                "movement_count": 0,
                "remaining_status": "AT_CONFIRMED_SNAPSHOT",
                "latest_allocation": None,
            }

        def get_sku_history(self, **_kwargs):
            return deepcopy(self.snapshot)

    history = _MutableHistory()
    adapter = FifoCurrentUnitCostAdapter(
        _LegacyCosts(cost="99.00"),
        history,
    )
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        before_restore = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
        # Simulate restoring a different full layer history with the same
        # stream revision and unchanged next unit cost.
        history.snapshot["layers"][1]["unit_cost_rub"] = "30.00"
        after_restore = adapter.resolve_current_cost(
            IDENTITY, store_id="store-a", as_of_date="2026-11-06",
        )
    finally:
        reset_current_tenant_user_id(token)

    assert before_restore["cost_per_unit_rub"] == after_restore["cost_per_unit_rub"] == "10.00"
    assert before_restore["cost_revision"] != after_restore["cost_revision"]
