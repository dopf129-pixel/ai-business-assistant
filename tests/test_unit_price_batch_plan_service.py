from decimal import Decimal

import pytest

from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.tax_service import TaxService
from services.unit_price_batch_plan_service import UnitPriceBatchPlanService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


class _Products:
    def __init__(self, items):
        self.items = items
        self.calls = 0

    def load_products(self):
        self.calls += 1
        return self.items


class _Source:
    def __init__(self, products, failures=None, complete=False):
        self.product_service = _Products(products)
        self.failures = failures or {}
        self.complete = complete
        self.calls = []

    def load_snapshot(
        self, sku, user_id, operation_trace=None,
        catalog_product=None, force_refresh=False,
    ):
        self.calls.append((sku, user_id, dict(catalog_product or {}), force_refresh))
        reservation = operation_trace.reserve_ozon_request("fake")
        if reservation.get("error"):
            return {"error": True, "code": reservation["code"]}
        if sku in self.failures:
            return {"error": True, "code": self.failures[sku]}
        product = catalog_product or {}
        inputs = {"price": "500", "cost": "100"}
        if self.complete:
            inputs.update({
                "commission_rate": "15",
                "logistics_per_unit": "40",
                "last_mile_per_unit": "10",
                "acquiring_per_unit": "5",
                "advertising_rate": "8",
                "discount_points_rate": "20",
                "tax_mode": "USN_INCOME",
                "tax_rate": "6",
                "minimum_tax_rate": "1",
            })
        return {
            "error": False,
            "identity": {
                "product_id": str(product.get("product_id")),
                "offer_id": str(product.get("offer_id")),
                "sku": str(product.get("sku")),
                "tenant_scope": "user-1::ozon::store-a",
            },
            "product": {"scheme": "FBO"},
            "suggested_inputs": inputs,
            "input_provenance": {"cost": "confirmed_store_cost"},
            "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
            "source_completeness": {"catalog_identity": {"complete": True}},
            "cache": {"status": "miss", "age_seconds": 0, "ttl_seconds": 600},
        }


class _Scenario:
    def calculate(self, inputs, identity=None, provenance=None, sources=None):
        missing = [key for key in ("price", "cost", "commission_rate") if inputs.get(key) is None]
        return {
            "available": not missing,
            "missing_inputs": missing,
            "invalid_inputs": [],
            "calculated": {"profit": 100, "margin_percent": 20},
        }


class _Planner:
    def __init__(self, forward_profit_matches=True):
        self.forward_profit_matches = forward_profit_matches

    def parse_target_margin(self, value):
        try:
            target = Decimal(str(value))
        except Exception:
            return {"error": True}
        if not target.is_finite() or target < 0 or target > 100:
            return {"error": True}
        return {"error": False, "value": target}

    def solve(self, inputs, target, identity=None, provenance=None, sources=None):
        target = Decimal(str(target))
        price = Decimal("600")
        profit = float(target * price / Decimal("100"))
        if not self.forward_profit_matches:
            profit = 0
        return {
            "error": False,
            "evaluation_count": 1,
            "target": {
                "status": "FOUND",
                "price": str(price),
                "profit": profit,
                "margin_percent": float(target),
                "forward_result": {
                    "available": True,
                    "calculated": {"profit": profit},
                },
            },
        }


def _catalog_item(index, scheme=None):
    result = {
        "product_id": f"product-{index}",
        "offer_id": f"offer-{index}",
        "sku": f"sku-{index}",
    }
    if scheme is not None:
        result["scheme"] = scheme
    return result


def _selection(*items):
    return [{
        "identity": {
            "product_id": item["product_id"],
            "offer_id": item["offer_id"],
            "catalog_sku": item["sku"],
        }
    } for item in items]


def _service(products, failures=None, clock=None, complete=False, planner=None,
             tariff_profile_runtime_service=None):
    source = _Source(products, failures, complete=complete)
    return UnitPriceBatchPlanService(
        source,
        _Scenario(),
        planner or _Planner(),
        clock=clock,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
        tariff_profile_runtime_service=tariff_profile_runtime_service,
    ), source


def test_batch_plan_and_row_price_edit_share_the_same_frozen_tariff_profile():
    class _TariffRuntime:
        def resolve_for_product(self, identity, seller_price, source_snapshot,
                                source_age_seconds, source_ttl_seconds, user_id=None):
            profile = {
                "profile_id": "batch-tariff-" + str(identity["sku"]),
                "revision": 1, "state_revision": 1, "owner_id": user_id,
                "store_id": identity["store_id"],
                "identity": {key: identity[key] for key in ("product_id", "offer_id", "sku")},
                "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB", "currency": "RUB",
                "origin": "MANUAL_SELLER_ASSUMPTION", "source_ref": "synthetic-test",
                "recorded_at": "2026-10-27T10:00:00+00:00", "observed_at": None,
                "effective_from": "2026-10-27", "effective_to": None,
                "confirmed_by_owner": True,
                "bands": [
                    {"price_from_cents": 50_000, "price_to_cents": 50_000, "commission_rate": "11"},
                    {"price_from_cents": 50_001, "price_to_cents": 60_000, "commission_rate": "22"},
                ],
            }
            tariff_identity = {
                "owner_id": user_id, "store_id": identity["store_id"],
                "product_id": identity["product_id"], "offer_id": identity["offer_id"],
                "sku": identity["sku"],
            }
            resolved = UnitPriceTariffResolver().resolve(
                seller_price_cents=UnitPriceTariffSnapshotAdapter.price_to_cents(seller_price),
                identity=tariff_identity, sale_schema="FBO",
                effective_date="2026-10-27", profiles=[profile],
            )
            return {
                "error": False,
                "resolution": resolved,
                "frozen_tariff_resolution": UnitPriceTariffSnapshotAdapter.freeze(
                    resolved, profile, candidate_profiles=[profile],
                    effective_date="2026-10-27",
                ),
            }

    class _TariffPlanner(_Planner):
        def __init__(self):
            super().__init__()
            self.tariff_calls = []

        def solve(self, inputs, target, identity=None, provenance=None, sources=None,
                  frozen_tariff_snapshot=None, tariff_resolution_required=False, **_kwargs):
            self.tariff_calls.append((inputs.get("commission_rate"), frozen_tariff_snapshot,
                                      tariff_resolution_required))
            return super().solve(inputs, target, identity, provenance, sources)

    products = [_catalog_item(1), _catalog_item(2)]
    planner = _TariffPlanner()
    service, _source = _service(
        products, complete=True, planner=planner,
        tariff_profile_runtime_service=_TariffRuntime(),
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "20")
        row = batch["rows"][0]
        edited = service.edit_row_assumption(batch, row["row_id"], "price", "500.01")
    finally:
        reset_current_tenant_user_id(token)

    assert batch["status"] == "COMPLETED"
    assert row["inputs"]["commission_rate"] == "11"
    assert row["tariff_scope"] == "FROZEN_PROFILE_SET"
    assert all(call[1] is not None and call[2] is True for call in planner.tariff_calls)
    assert edited["error"] is False
    edited_row = next(item for item in edited["rows"] if item["row_id"] == row["row_id"])
    assert edited_row["inputs"]["price"] == "500.01"
    assert edited_row["inputs"]["commission_rate"] == "22"
    assert edited_row["provenance"]["commission_rate"] == "manual_seller_assumption"


def test_legacy_current_commission_in_batch_is_limited_to_source_price():
    products = [_catalog_item(1), _catalog_item(2)]
    source = _Source(products, complete=True)
    original_load = source.load_snapshot

    def load_current_point(*args, **kwargs):
        snapshot = original_load(*args, **kwargs)
        snapshot["input_provenance"]["commission_rate"] = "ozon_current_fbo_rate"
        return snapshot

    source.load_snapshot = load_current_point
    scenario = UnitPriceScenarioService(TaxService())
    service = UnitPriceBatchPlanService(
        source, scenario, UnitPriceTargetPlanningService(scenario),
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "0")
        row = batch["rows"][0]
        changed = service.edit_row_assumption(batch, row["row_id"], "price", "500.01")
    finally:
        reset_current_tenant_user_id(token)

    assert batch["status"] == "COMPLETED"
    assert row["tariff_scope"] == "EXACT_PRICE_ONLY"
    assert row["legacy_tariff_price_cents"] == 50_000
    assert row["planning"]["target"]["price"] == "500.00"
    assert changed["error"] is False
    changed_row = next(item for item in changed["rows"] if item["row_id"] == row["row_id"])
    assert changed_row["inputs"]["commission_rate"] is None
    assert changed_row["provenance"]["commission_rate"] == "unknown"
    assert changed_row["status"] == "INCOMPLETE_INPUTS"


def test_batch_requires_two_to_ten_unique_exact_catalog_identities():
    items = [_catalog_item(1), _catalog_item(2)]
    service, _ = _service(items)

    assert service.build(_selection(items[0]), "user-1", "20")["code"] == "BATCH_PLAN_SELECTION_SIZE_INVALID"
    duplicate = _selection(items[0], items[0])
    assert service.build(duplicate, "user-1", "20")["code"] == "BATCH_PLAN_DUPLICATE_IDENTITY"
    eleven = [_catalog_item(index) for index in range(11)]
    assert service.build(_selection(*eleven), "user-1", "20")["code"] == "BATCH_PLAN_SELECTION_SIZE_INVALID"
    assert service.build(_selection(*items), "user-1", "101")["code"] == "BATCH_PLAN_TARGET_INVALID"


def test_batch_loads_catalog_once_and_preserves_row_order_and_stable_ids():
    products = [_catalog_item(index) for index in range(3)]
    service, source = _service(products)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        selected = _selection(products[2], products[0])
        first = service.build(selected, "user-1", "20")
        again = service.build(selected, "user-1", "20")
    finally:
        reset_current_tenant_user_id(token)

    assert source.product_service.calls == 2  # exactly once for each batch build
    assert [row["identity"]["catalog_sku"] for row in first["rows"]] == ["sku-2", "sku-0"]
    assert [row["row_id"] for row in first["rows"]] == [row["row_id"] for row in again["rows"]]
    assert [row["status"] for row in first["rows"]] == ["INCOMPLETE_INPUTS"] * 2
    assert [call[2]["sku"] for call in source.calls] == ["sku-2", "sku-0"] * 2
    assert first["read_only"] is True and first["executed"] is False


def test_three_sku_batch_performance_profile_counts_catalog_pages_and_http_attempts():
    class _ProfileClock:
        def __init__(self):
            self.value = 0.0

        def __call__(self):
            return self.value

    class _ProfileSource(_Source):
        def __init__(self, products, clock):
            super().__init__(products, complete=True)
            self.clock = clock
            self.finance_pages = 0

        def load_snapshot(
            self, sku, user_id, operation_trace=None,
            catalog_product=None, force_refresh=False,
        ):
            # Model one current-facts request and one complete finance page per SKU.
            for endpoint in ("current-facts", "finance-page"):
                reservation = operation_trace.reserve_ozon_request(endpoint)
                if reservation.get("error"):
                    return {"error": True, "code": reservation["code"]}
                self.clock.value += 0.01
                if endpoint == "finance-page":
                    self.finance_pages += 1
            self.calls.append((sku, user_id, dict(catalog_product or {}), force_refresh))
            product = catalog_product or {}
            return {
                "error": False,
                "identity": {
                    "product_id": str(product.get("product_id")),
                    "offer_id": str(product.get("offer_id")),
                    "sku": str(product.get("sku")),
                    "tenant_scope": "user-1::ozon::store-a",
                },
                "product": {"scheme": "FBO"},
                "suggested_inputs": {
                    "price": "500", "cost": "100", "commission_rate": "15",
                    "logistics_per_unit": "40", "last_mile_per_unit": "10",
                    "acquiring_per_unit": "5", "advertising_rate": "8",
                    "discount_points_rate": "20", "tax_mode": "USN_INCOME",
                    "tax_rate": "6", "minimum_tax_rate": "1",
                },
                "input_provenance": {"cost": "confirmed_store_cost"},
                "source_periods": {"seller_price_as_of": "2026-10-17T00:00:00Z"},
                "source_completeness": {"catalog_identity": {"complete": True}},
                "cache": {"status": "miss", "age_seconds": 0, "ttl_seconds": 600},
            }

    products = [_catalog_item(index) for index in range(3)]
    fake_clock = _ProfileClock()
    source = _ProfileSource(products, fake_clock)
    service = UnitPriceBatchPlanService(
        source, _Scenario(), _Planner(), clock=fake_clock,
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        result = service.build(_selection(*products), "user-1", "20")
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "COMPLETED"
    assert [row["status"] for row in result["rows"]] == ["READY"] * 3
    assert source.product_service.calls == 1
    assert len(source.calls) == 3
    assert source.finance_pages == 3
    assert result["operation_diagnostics"]["http_attempts"] == 6
    assert abs(fake_clock() - 0.06) < 1e-9


def test_completed_assumptions_remove_old_missing_and_invalid_diagnostics():
    products = [_catalog_item(1), _catalog_item(2)]

    class MissingInputsSource(_Source):
        def load_snapshot(self, *args, **kwargs):
            result = super().load_snapshot(*args, **kwargs)
            result["suggested_inputs"].pop("cost", None)
            return result

    source = MissingInputsSource(products, complete=True)
    service = UnitPriceBatchPlanService(
        source,
        _Scenario(),
        _Planner(),
        tenant_scope_provider=lambda: "user-1::ozon::store-a",
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "20")
        assert batch["rows"][0]["status"] == "INCOMPLETE_INPUTS"
        assert batch["rows"][0]["missing_inputs"] == ["cost"]
        completed = service.edit_row_assumption(
            batch, batch["rows"][0]["row_id"], "cost", "200"
        )
    finally:
        reset_current_tenant_user_id(token)

    row = completed["rows"][0]
    assert row["status"] == "READY"
    assert row["missing_inputs"] == []
    assert row["invalid_inputs"] == []


def test_successful_recalculation_clears_stale_invalid_input_labels():
    products = [_catalog_item(1), _catalog_item(2)]
    service, _source = _service(products, complete=True)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "20")
        row = batch["rows"][0]
        row["missing_inputs"] = ["cost"]
        row["invalid_inputs"] = ["commission_rate"]
        service._recalculate_row(batch, row)
    finally:
        reset_current_tenant_user_id(token)

    assert row["status"] == "READY"
    assert row["missing_inputs"] == []
    assert row["invalid_inputs"] == []


def test_batch_isolates_bad_identity_scheme_and_source_failure():
    products = [
        _catalog_item(1),
        _catalog_item(2, "FBS"),
        _catalog_item(3),
    ]
    service, _ = _service(products, failures={"sku-3": "OZON_TIMEOUT"})
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        result = service.build(_selection(*products), "user-1", "20")
    finally:
        reset_current_tenant_user_id(token)

    assert [row["status"] for row in result["rows"]] == [
        "INCOMPLETE_INPUTS", "UNSUPPORTED_SCHEME", "SOURCE_UNAVAILABLE"
    ]
    assert result["rows"][1]["reason"] == "SCHEME_NOT_SUPPORTED"
    assert result["rows"][2]["reason"] == "OZON_TIMEOUT"


def test_parent_http_budget_applies_to_the_whole_batch():
    products = [_catalog_item(1), _catalog_item(2)]
    service, source = _service(products)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    parent = PeriodProfitOperationTrace(
        operation="test-parent",
        time_budget_seconds=10,
        ozon_request_budget=1,
    )
    try:
        result = service.build(_selection(*products), "user-1", "20", parent_trace=parent)
    finally:
        reset_current_tenant_user_id(token)

    assert len(source.calls) == 1
    assert result["operation_diagnostics"]["http_attempts"] == 1
    assert result["rows"][0]["status"] == "INCOMPLETE_INPUTS"
    assert result["rows"][1]["status"] == "BUDGET_EXHAUSTED"


def test_complete_row_uses_solver_candidate_and_independent_forward_result_check():
    products = [_catalog_item(1), _catalog_item(2)]
    service, _ = _service(products, complete=True)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        result = service.build(_selection(*products), "user-1", "20")
    finally:
        reset_current_tenant_user_id(token)
    assert [row["status"] for row in result["rows"]] == ["READY", "READY"]
    assert result["evaluation_count"] == 2
    assert result["rows"][0]["planning"]["target"]["forward_result"]["available"] is True


def test_solver_success_without_forward_target_proof_is_not_ready():
    products = [_catalog_item(1), _catalog_item(2)]
    service, _ = _service(
        products, complete=True, planner=_Planner(forward_profit_matches=False)
    )
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        result = service.build(_selection(*products), "user-1", "20")
    finally:
        reset_current_tenant_user_id(token)
    assert [row["status"] for row in result["rows"]] == ["TARGET_NOT_CONFIRMED"] * 2
    assert result["rows"][0]["reason"] == "FINAL_FORWARD_CHECK_FAILED"


def test_assumption_edits_and_bulk_advertising_are_local_and_versioned():
    products = [_catalog_item(1), _catalog_item(2)]
    service, source = _service(products, complete=True)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "20")
        row_id = batch["rows"][0]["row_id"]
        edited = service.edit_row_assumption(batch, row_id, "cost", "0")
        assert edited["version"] == batch["version"] + 1
        assert edited["rows"][0]["inputs"]["cost"] == "0"
        assert edited["rows"][0]["provenance"]["cost"] == "manual_seller_assumption"
        assert edited["rows"][0]["status"] == "READY"

        row_ids = [row["row_id"] for row in edited["rows"]]
        preview = service.preview_advertising_rate(edited, row_ids, "0")
        assert preview["requires_confirmation"] is True
        assert [row["new_value"] for row in preview["rows"]] == ["0", "0"]
        assert service.apply_advertising_rate(
            edited, row_ids, "0", confirmed=True,
            expected_batch_id=edited["batch_id"],
            expected_batch_version=edited["version"] - 1,
        )["code"] == "BATCH_PLAN_CONFIRMATION_STALE"
        assert service.apply_advertising_rate(edited, row_ids, "0")["code"] == "BATCH_PLAN_CONFIRMATION_REQUIRED"
        applied = service.apply_advertising_rate(
            edited, row_ids, "0", confirmed=True,
            expected_batch_id=edited["batch_id"],
            expected_batch_version=edited["version"],
        )
        assert applied["version"] == edited["version"] + 1
        assert all(row["inputs"]["advertising_rate"] == "0" for row in applied["rows"])
        assert all(row["provenance"]["advertising_rate"] == "manual_seller_assumption" for row in applied["rows"])
    finally:
        reset_current_tenant_user_id(token)
    assert len(source.calls) == 2


def test_explicit_refresh_uses_new_source_and_preserves_manual_zero_assumptions():
    products = [_catalog_item(1), _catalog_item(2)]
    service, source = _service(products, complete=True)
    token = set_current_tenant_user_id("user-1::ozon::store-a")
    try:
        batch = service.build(_selection(*products), "user-1", "20")
        edited = service.edit_row_assumption(
            batch, batch["rows"][0]["row_id"], "cost", "0"
        )
        refreshed = service.refresh(edited)
    finally:
        reset_current_tenant_user_id(token)
    assert refreshed["version"] == edited["version"] + 1
    assert refreshed["batch_id"] == edited["batch_id"]
    assert refreshed["rows"][0]["inputs"]["cost"] == "0"
    assert refreshed["rows"][0]["provenance"]["cost"] == "manual_seller_assumption"
    assert refreshed["rows"][0]["status"] == "READY"
    assert [call[3] for call in source.calls] == [False, False, True, True]


@pytest.mark.parametrize("bad_items", [None, {}, [None, None]])
def test_batch_selection_rejects_unknown_identity_shapes(bad_items):
    service, source = _service([])
    result = service.build(bad_items, "user-1", "20")
    assert result["error"] is True
    assert source.product_service.calls == 0
