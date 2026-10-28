from copy import deepcopy
from datetime import datetime, timezone

from services.unit_price_observation_quality_service import UnitPriceObservationQualityService
from services.unit_price_recommendation_ranking_service import UnitPriceRecommendationRankingService


NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
IDENTITY = {
    "store_id": "store-a", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
}
MODEL_COMPLETENESS = {
    "price_history": "PRICE_HISTORY_UNCONFIRMED", "successful_units": "CONFIRMED",
    "finance": "CONFIRMED", "advertising": "PARTIAL", "tariff": "MANUAL_ASSUMPTION",
    "tax": "MANUAL_ASSUMPTION", "unit_cost": "MANUAL_ASSUMPTION",
    "returns": "UNKNOWN", "analytics": "CONFIRMED", "window": "CONFIRMED",
    "deduplication": "CONFIRMED",
}


def _source(name, start, end):
    return {
        "name": name, "status": "COMPLETE", "complete": True,
        "source_window_start": start, "source_window_end": end,
        "source_date_basis": "SHARED_EVENT_DATE", "timezone": "Europe/Moscow",
        "received_at": "2026-10-27T09:00:00+00:00",
    }


def _model_candidate(index, price, profit, start, end, units, *, signature="same-assumptions"):
    return {
        "index": index, "owner_id": "owner-a", "store_id": "store-a",
        "result_revision": 1, "assumption_signature": signature,
        "result": {
            "schema_version": 1, "identity": deepcopy(IDENTITY),
            "seller_price_cents": price * 100, "status": "AVAILABLE",
            "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
            "window": {"from": start, "to": end, "timezone": "Europe/Moscow",
                       "date_basis": "SOURCE_CALENDAR_DATE"},
            "sources": [_source("ANALYTICS", start, end), _source("PERFORMANCE", start, end)],
            "metrics": {
                "profit_per_unit": str(profit), "observed_profit_per_unit": None,
                "successful_sale_units": units, "successful_unit_denominator": units,
                "revenue_basis": "MODELLED_SELLER_REVENUE",
                "advertising_status": "CPC_ONLY_MODEL",
            },
            "completeness": deepcopy(MODEL_COMPLETENESS),
            "reasons": [], "warnings": [],
        },
    }


def _rank(candidates, **kwargs):
    return UnitPriceRecommendationRankingService(
        UnitPriceObservationQualityService(),
    ).rank_observations(candidates, now=NOW, **kwargs)


def test_rank_uses_profit_per_unit_not_total_profit_or_units_sold():
    candidates = [
        _model_candidate(0, 100, "20.00", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "18.00", "2026-10-08", "2026-10-14", 200),
    ]
    result = _rank(candidates)

    assert result["status"] == "RANKED"
    assert result["display_basis"] == "MODELLED_FROM_OBSERVED_INPUTS"
    assert result["verified"] is False
    assert result["best_indices"] == [0]
    assert result["ranking"][0]["profit_per_unit"] == "20.00"
    assert result["ranking"][1]["delta_vs_baseline"] == "-2.00"
    assert result["ranking"][1]["delta_percent_vs_baseline"] == "-10.00"
    assert "COMPARISON_DOES_NOT_ESTABLISH_PRICE_CHANGE_CAUSALITY." in result["quality_assessment"]["warnings"]
    assert "identity" not in result["ranking"][0]


def test_tie_is_resolved_after_money_rounding_and_all_winners_are_shown():
    result = _rank([
        _model_candidate(0, 100, "20.004", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "20.00", "2026-10-08", "2026-10-14", 200),
    ])

    assert result["best_profit_per_unit"] == "20.00"
    assert result["best_indices"] == [0, 1]
    assert all(row["is_best"] for row in result["ranking"])


def test_negative_baseline_keeps_money_delta_but_suppresses_percent():
    result = _rank([
        _model_candidate(0, 100, "-4.00", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "-2.00", "2026-10-08", "2026-10-14", 200),
    ])

    candidate = next(row for row in result["ranking"] if row["index"] == 1)
    assert candidate["delta_vs_baseline"] == "2.00"
    assert candidate["delta_percent_vs_baseline"] is None
    assert candidate["delta_percent_reason"] == "BASELINE_NOT_POSITIVE"


def test_non_comparable_candidates_do_not_produce_partial_winner():
    candidates = [
        _model_candidate(0, 100, "20.00", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "18.00", "2026-10-05", "2026-10-11", 200),
    ]
    candidates[1]["assumption_signature"] = "changed-tax-or-cost"
    result = _rank(candidates)

    assert result["status"] == "INCOMPARABLE"
    assert result["ranking"] == []
    assert result["best_indices"] == []
    assert "OBSERVATION_WINDOWS_OVERLAP" in result["quality_assessment"]["reasons"]
    assert "MODEL_ASSUMPTIONS_MISMATCH" in result["quality_assessment"]["reasons"]


def test_canonical_fact_ranks_observed_metric_and_keeps_verified_basis():
    candidates = [
        _model_candidate(0, 100, "900.00", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "900.00", "2026-10-08", "2026-10-14", 200),
    ]
    for candidate, observed_profit in zip(candidates, ("9.00", "11.00")):
        result = candidate["result"]
        result["evidence_basis"] = "CANONICAL_FACT_COMPARABLE"
        result["metrics"].update({
            "observed_profit_per_unit": observed_profit,
            "revenue_basis": "SELLER_REVENUE", "advertising_status": "COMPLETE",
        })
        result["completeness"] = {key: "CONFIRMED" for key in MODEL_COMPLETENESS}
        result["sources"].extend(
            _source(name, result["window"]["from"], result["window"]["to"])
            for name in ("FINANCE", "RETURNS", "SELLER_PRICE", "TARIFF", "COST", "TAX")
        )

    ranked = _rank(candidates)

    assert ranked["status"] == "RANKED"
    assert ranked["verified"] is True
    assert ranked["display_basis"] == "OBSERVED_COMPARABLE_PERIODS"
    assert ranked["best_indices"] == [1]
    assert ranked["best_profit_per_unit"] == "11.00"


def test_candidate_validation_does_not_mutate_callers_and_enforces_bound():
    candidates = [
        _model_candidate(0, 100, "20.00", "2026-10-01", "2026-10-07", 100),
        _model_candidate(1, 95, "18.00", "2026-10-08", "2026-10-14", 200),
    ]
    original = deepcopy(candidates)
    result = _rank(candidates)
    too_many = _rank(candidates * 6)

    assert result["status"] == "RANKED"
    assert candidates == original
    assert too_many == {
        "error": True, "code": "UNIT_PRICE_RANKING_CANDIDATES_INVALID",
        "read_only": True, "executed": False,
    }
