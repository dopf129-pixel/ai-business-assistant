from copy import deepcopy

import pytest

from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_source import UnitPriceTariffSource


AS_OF = "2026-10-27T10:30:00+00:00"


def _snapshot(**overrides):
    value = {
        "error": False,
        "snapshot_id": "0123456789abcdef",
        "identity": {
            "user_id": "owner-1",
            "store_id": "store-1",
            "tenant_scope": "owner-1::ozon::client-1",
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "sku-1",
        },
        "product": {"scheme": "FBO"},
        "suggested_inputs": {"price": 100.0, "commission_rate": 11.0},
        "input_provenance": {
            "price": "ozon_current_seller_price",
            "commission_rate": "ozon_current_fbo_rate",
        },
        "source_completeness": {
            "seller_price": {"complete": True},
            "commission_rate": {"complete": True},
        },
        "source_periods": {
            "seller_price_as_of": AS_OF,
            "commission_rate_as_of": AS_OF,
        },
    }
    for key, val in overrides.items():
        value[key] = val
    return value


def test_existing_ozon_snapshot_becomes_ephemeral_current_price_point_only():
    result = UnitPriceTariffSource().from_scenario_snapshot(_snapshot())

    assert result["error"] is False
    assert result["status"] == "CURRENT_PRICE_POINT_AVAILABLE"
    assert result["range_status"] == "RANGE_SOURCE_UNAVAILABLE"
    assert result["current_price_cents"] == 10_000
    assert result["current_rate"] == "11.0"
    assert result["profiles"][0]["origin"] == "CURRENT_PRICE_POINT"
    assert result["profiles"][0]["bands"] == [{
        "price_from_cents": 10_000,
        "price_to_cents": 10_000,
        "commission_rate": "11.0",
    }]


def test_current_point_resolves_at_same_price_but_not_adjacent_price():
    source = UnitPriceTariffSource().from_scenario_snapshot(_snapshot())
    resolver = UnitPriceTariffResolver()
    request = {
        "identity": {
            "owner_id": "owner-1",
            "store_id": "store-1",
            "product_id": "product-1",
            "offer_id": "offer-1",
            "sku": "sku-1",
        },
        "sale_schema": "FBO",
        "effective_date": "2026-10-27",
        "profiles": source["profiles"],
    }

    current = resolver.resolve(seller_price_cents=10_000, **request)
    neighbor = resolver.resolve(seller_price_cents=10_001, **request)

    assert current["available"] is True
    assert current["status"] == "CURRENT_PRICE_POINT_ONLY"
    assert current["commission_rate"] == "11"
    assert neighbor["available"] is False


@pytest.mark.parametrize("value", [None, True, "NaN", "Infinity", "100.001", "1e999999", "1e-999999", -1, 0])
def test_invalid_current_price_is_not_exposed_as_a_profile(value):
    snapshot = _snapshot()
    snapshot["suggested_inputs"]["price"] = value

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is False
    assert result["profiles"] == []
    assert result["range_status"] == "RANGE_SOURCE_UNAVAILABLE"


def test_missing_rate_keeps_range_unavailable_and_no_profile():
    snapshot = _snapshot()
    snapshot["suggested_inputs"]["commission_rate"] = None

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is False
    assert result["reason"] == "CURRENT_PRICE_COMMISSION_INVALID"


def test_mixed_or_incomplete_evidence_fails_closed():
    snapshot = _snapshot()
    snapshot["source_periods"]["commission_rate_as_of"] = "2026-10-27T10:31:00+00:00"

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is False
    assert result["reason"] == "CURRENT_SOURCE_TIMESTAMP_MISMATCH"


def test_foreign_tenant_scope_and_unsupported_scheme_are_not_mapped():
    foreign = _snapshot()
    foreign["identity"]["tenant_scope"] = "other-owner::ozon::client-1"
    unsupported = _snapshot()
    unsupported["product"]["scheme"] = "FBS"

    assert UnitPriceTariffSource().from_scenario_snapshot(foreign)["profiles"] == []
    assert UnitPriceTariffSource().from_scenario_snapshot(unsupported)["reason"] == "UNSUPPORTED_SCHEME"


def test_zero_rate_is_explicitly_preserved_from_complete_source():
    snapshot = _snapshot()
    snapshot["suggested_inputs"]["commission_rate"] = 0

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is True
    assert result["profiles"][0]["bands"][0]["commission_rate"] == "0"


def test_source_adapter_is_pure_and_does_not_mutate_snapshot():
    snapshot = _snapshot()
    before = deepcopy(snapshot)

    UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert snapshot == before

def test_malformed_completeness_shape_fails_closed_without_exception():
    snapshot = _snapshot()
    snapshot["source_completeness"]["seller_price"] = "invalid"

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is False
    assert result["profiles"] == []

@pytest.mark.parametrize("rate", ["1e-999999", "1e999999", "101", "NaN", True])
def test_extreme_or_invalid_rate_is_not_formatted_or_persisted(rate):
    snapshot = _snapshot()
    snapshot["suggested_inputs"]["commission_rate"] = rate

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is False
    assert result["profiles"] == []

def test_existing_scenario_source_snapshot_is_accepted_by_point_mapper():
    from datetime import datetime

    from services.tenant_context import (
        reset_current_tenant_user_id,
        set_current_tenant_user_id,
    )
    from services.unit_price_scenario_source import UnitPriceScenarioSource

    class CurrentFacts:
        def get_price_and_commission_facts(self, **_kwargs):
            return {"error": False, "seller_price": 100, "commission_rate": 11}

    class Cost:
        def get_cost(self, product_id):
            return {"product_id": product_id, "cost_price": 40, "currency": "RUB"}

    class Tax:
        def get_policy(self):
            return {"error": False, "configured": True, "policy": {"mode": "NONE"}}

    class Finance:
        def get_daily_discount_points_evidence(self, _day, _sku):
            return {"error": False, "complete": True, "records": []}

    source = UnitPriceScenarioSource(
        product_service=object(),
        current_economics_source=CurrentFacts(),
        finance_service=Finance(),
        cost_service=Cost(),
        tax_configuration_service=Tax(),
        clock=lambda: datetime.fromisoformat("2026-10-14T12:00:00+00:00"),
    )
    token = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        snapshot = source.load_snapshot(
            "sku-1",
            user_id="owner-1",
            catalog_product={"product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1"},
        )
    finally:
        reset_current_tenant_user_id(token)

    result = UnitPriceTariffSource().from_scenario_snapshot(snapshot)

    assert result["current_point_available"] is True
    assert result["current_price_cents"] == 10_000
    assert result["profiles"][0]["identity"]["sku"] == "sku-1"
