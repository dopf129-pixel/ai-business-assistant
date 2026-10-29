from decimal import Decimal

import pytest

from services.tax_service import TaxService
from services.unit_economics_experiment_candidate_price_service import (
    UnitEconomicsExperimentCandidatePriceService,
)
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter
from services.unit_price_target_planning_service import UnitPriceTargetPlanningService


IDENTITY = {
    "owner_id": "owner-1", "user_id": "owner-1", "store_id": "store-1",
    "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
}


def _inputs(**overrides):
    values = {
        "price": "100", "cost": "20", "commission_rate": "10",
        "logistics_per_unit": "5", "last_mile_per_unit": "1",
        "acquiring_per_unit": "1", "advertising_rate": "0",
        "discount_points_rate": "0", "tax_mode": "NONE", "tax_rate": "0",
        "minimum_tax_rate": "0",
    }
    values.update(overrides)
    return values


def _snapshot(bands, *, seller_price_cents=10_000):
    profile = {
            "profile_id": "profile-1", "revision": 1,
            "state_revision": 1, "owner_id": "owner-1", "store_id": "store-1",
            "identity": {
                "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
            },
            "sale_schema": "FBO", "price_basis": "SELLER_PRICE_RUB",
            "currency": "RUB", "origin": "MANUAL_SELLER_ASSUMPTION",
            "source_ref": "synthetic-test", "recorded_at": "2026-10-27T10:00:00+00:00",
            "observed_at": None,
            "effective_from": "2026-10-01", "effective_to": None,
            "confirmed_by_owner": True, "bands": bands,
    }
    resolution = UnitPriceTariffResolver().resolve(
        seller_price_cents=seller_price_cents, identity=IDENTITY,
        sale_schema="FBO", effective_date="2026-10-27", profiles=[profile],
    )
    return UnitPriceTariffSnapshotAdapter.freeze(
        resolution, profile if resolution.get("available") else None,
        candidate_profiles=[profile], effective_date="2026-10-27",
    )


def _service():
    planner = UnitPriceTargetPlanningService(UnitPriceScenarioService(TaxService()))
    return UnitEconomicsExperimentCandidatePriceService(planner)


def test_selects_bounded_prices_and_uses_canonical_profit_without_demand_claims():
    result = _service().select_candidates(
        _inputs(), {"min_price_cents": 9_500, "max_price_cents": 10_500},
        requested_count=5,
    )

    assert result["status"] == "AVAILABLE"
    assert result["candidate_count"] == 5
    assert result["candidate_prices_cents"][0] == 9_500
    assert result["candidate_prices_cents"][-1] == 10_500
    assert result["best_profit_per_unit_rub"] == max(
        row["profit_per_unit_rub"] for row in result["candidates"]
    )
    assert result["search"]["global_optimum_claimed"] is False
    assert result["read_only"] is True and result["executed"] is False
    assert "NO_PRICE_DEMAND_PREDICTION" in result["model_limitations"]
    assert all("demand" not in key.lower() for key in result)


def test_inserts_each_kopeck_side_of_confirmed_tariff_boundary():
    snapshot = _snapshot([
        {"price_from_cents": 1, "price_to_cents": 9_999, "commission_rate": "10"},
        {"price_from_cents": 10_000, "price_to_cents": 30_000, "commission_rate": "14"},
    ], seller_price_cents=10_000)
    result = _service().select_candidates(
        _inputs(commission_rate="14"),
        {"min_price_cents": 9_997, "max_price_cents": 10_003},
        requested_count=2, frozen_tariff_snapshot=snapshot, identity=IDENTITY,
    )

    assert result["status"] == "AVAILABLE"
    assert {9_999, 10_000}.issubset(
        set(result["candidate_prices_cents"])
    )
    by_price = {row["price_cents"]: row for row in result["candidates"]}
    assert by_price[9_999]["commission_rate_percent"] == "10"
    assert by_price[10_000]["commission_rate_percent"] == "14"
    assert result["tariff_basis"] == "FROZEN_TARIFF_SNAPSHOT"


def test_refuses_to_truncate_when_tariff_boundaries_exceed_ten_candidates():
    snapshot = _snapshot([
        {"price_from_cents": 1, "price_to_cents": 9_500, "commission_rate": "10"},
        {"price_from_cents": 9_501, "price_to_cents": 10_500, "commission_rate": "11"},
        {"price_from_cents": 10_501, "price_to_cents": 20_000, "commission_rate": "12"},
    ], seller_price_cents=10_000)
    result = _service().select_candidates(
        _inputs(commission_rate="11"),
        {"min_price_cents": 9_000, "max_price_cents": 11_000},
        requested_count=10, frozen_tariff_snapshot=snapshot, identity=IDENTITY,
    )

    assert result["status"] == "INCOMPLETE"
    assert result["reason_code"] == "TARIFF_BOUNDARIES_EXCEED_CANDIDATE_LIMIT"
    assert "best_profit_per_unit_rub" not in result


def test_unknown_tariff_gap_blocks_all_candidate_ranking():
    snapshot = _snapshot([
        {"price_from_cents": 9_998, "price_to_cents": 9_998, "commission_rate": "10"},
        {"price_from_cents": 10_001, "price_to_cents": 10_003, "commission_rate": "14"},
    ], seller_price_cents=9_998)
    result = _service().select_candidates(
        _inputs(price="99.98"), {"min_price_cents": 9_997, "max_price_cents": 10_004},
        requested_count=2, frozen_tariff_snapshot=snapshot, identity=IDENTITY,
    )

    assert result["status"] == "INCOMPLETE"
    assert result["reason_code"] == "CANDIDATE_SCENARIO_INCOMPLETE"
    assert "best_profit_per_unit_rub" not in result
    assert "CANDIDATE_COMMISSION_UNAVAILABLE" in result["reason_codes"]


def test_preserves_tied_maximum_instead_of_selecting_arbitrary_winner():
    result = _service().select_candidates(
        _inputs(cost="0", commission_rate="100", logistics_per_unit="0",
                last_mile_per_unit="0", acquiring_per_unit="0"),
        {"min_price_cents": 9_800, "max_price_cents": 10_200}, requested_count=3,
    )

    assert result["status"] == "TIED_MAXIMUM"
    assert len(result["best_candidate_prices_cents"]) == result["candidate_count"]
    assert {row["profit_per_unit_rub"] for row in result["candidates"]} == {"0.00"}


@pytest.mark.parametrize("kwargs,code", [
    ({"price_bounds_cents": {"min_price_cents": 1, "max_price_cents": 1}},
     "PRICE_RANGE_TOO_NARROW"),
    ({"price_bounds_cents": {"min_price_cents": 1, "max_price_cents": 2},
      "requested_count": 1}, "INVALID_CANDIDATE_COUNT"),
    ({"price_bounds_cents": {"min_price_cents": 1, "max_price_cents": 100_000_000_000_000}},
     "INVALID_PRICE_BOUNDS"),
])
def test_rejects_impossible_or_unsupported_candidate_constraints(kwargs, code):
    call = {
        "price_bounds_cents": {"min_price_cents": 9_500, "max_price_cents": 10_500},
        "requested_count": 5,
    }
    call.update(kwargs)
    result = _service().select_candidates(_inputs(), **call)

    if code == "PRICE_RANGE_TOO_NARROW":
        assert result["error"] is False
        assert result["status"] == "INCOMPLETE"
    else:
        assert result["error"] is True
    assert result["code" if result["error"] else "reason_code"] == code


def test_unverified_manual_commission_is_marked_as_assumption_and_no_threshold_is_hidden():
    result = _service().select_candidates(
        _inputs(), {"min_price_cents": 9_500, "max_price_cents": 10_500},
        requested_count=3,
    )

    assert result["tariff_basis"] == "MANUAL_OR_SCENARIO_RATE_ASSUMPTION"
    assert "COMMISSION_RATE_IS_NOT_TARIFF_VERIFIED" in result["model_limitations"]
    assert result["advertising_mode"] == "SAME_DRR"
    assert all(row["commission_origin"] == "manual_seller_assumption"
               for row in result["candidates"])
    assert all(row["compensation_thresholds"] is not None
               for row in result["candidates"])
    assert Decimal(result["best_profit_per_unit_rub"]).is_finite()
