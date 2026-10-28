from copy import deepcopy
from datetime import datetime, timezone

from services.unit_price_observation_quality_service import UnitPriceObservationQualityService


NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
_IDENTITY = {
    "store_id": "store-a", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
}
_COMPLETENESS = {
    "price_history": "PRICE_HISTORY_UNCONFIRMED", "successful_units": "CONFIRMED",
    "finance": "CONFIRMED", "advertising": "PARTIAL", "tariff": "MANUAL_ASSUMPTION",
    "tax": "MANUAL_ASSUMPTION", "unit_cost": "MANUAL_ASSUMPTION",
    "returns": "UNKNOWN", "analytics": "CONFIRMED", "window": "CONFIRMED",
    "deduplication": "CONFIRMED",
}


def _source(name, start, end, *, basis="SHARED_EVENT_DATE", complete=True, received="2026-10-27T09:00:00+00:00"):
    return {
        "name": name, "status": "COMPLETE" if complete else "PARTIAL",
        "complete": complete, "source_window_start": start,
        "source_window_end": end, "source_date_basis": basis,
        "timezone": "Europe/Moscow", "received_at": received,
    }


def _model_candidate(price, start, end, *, sku="sku-1", units=40, signature="same-plan", basis="SHARED_EVENT_DATE"):
    return {
        "owner_id": "owner-a", "store_id": "store-a",
        "result_revision": 1, "assumption_signature": signature,
        "result": {
            "schema_version": 1, "identity": {**_IDENTITY, "sku": sku},
            "seller_price_cents": price * 100, "status": "AVAILABLE",
            "evidence_basis": "MODELLED_FROM_OBSERVED_INPUTS",
            "window": {"from": start, "to": end, "timezone": "Europe/Moscow", "date_basis": "SOURCE_CALENDAR_DATE"},
            "sources": [
                _source("ANALYTICS", start, end, basis=basis),
                _source("PERFORMANCE", start, end, basis=basis),
            ],
            "metrics": {
                "profit_per_unit": "12.34", "observed_profit_per_unit": None,
                "successful_sale_units": units, "successful_unit_denominator": units,
                "revenue_basis": "MODELLED_SELLER_REVENUE",
                "advertising_status": "CPC_ONLY_MODEL",
            },
            "completeness": deepcopy(_COMPLETENESS),
            "reasons": ["CANONICAL_PER_SALE_PROFIT_NOT_AVAILABLE_FROM_CURRENT_SOURCES"],
            "warnings": ["NO_CAUSAL_CLAIM_ABOUT_PRICE_CHANGES_OR_ADVERTISING_EFFICIENCY_IS_MADE."],
        },
    }


def _fbo_buyout_model_candidate(price, start, end, *, units=40, signature="same-plan", returns_basis="FBO_POSTING_AND_RETURN_CHANGE_WINDOW"):
    candidate = _model_candidate(
        price, start, end, units=units, signature=signature,
        basis="PERFORMANCE_REPORT_DATE",
    )
    result = candidate["result"]
    result["sources"] = [
        source for source in result["sources"] if source["name"] != "ANALYTICS"
    ]
    result["sources"].append(_source(
        "RETURNS", start, end, basis=returns_basis,
    ))
    result["completeness"]["returns"] = "CONFIRMED"
    result["metrics"].update({
        "buyout_rate_percent": "80.00", "buyout_sample_size": units,
        "delivered_units": units,
    })
    return candidate


def _assess(candidates, **kwargs):
    return UnitPriceObservationQualityService().assess(candidates, now=NOW, **kwargs)


def test_same_assumptions_nonoverlapping_windows_are_model_comparable_not_verified():
    result = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"),
        _model_candidate(95, "2026-10-08", "2026-10-14"),
    ])

    assert result["status"] == "COMPARABLE"
    assert result["evidence_basis"] == "MODELLED_FROM_OBSERVED_INPUTS"
    assert result["verified"] is False
    assert "OWNER_DECLARED_PRICE_DOES_NOT_VERIFY_PER_SALE_PRICE_HISTORY." in result["warnings"]
    assert "CPC_ONLY_MODEL_OMITS_OTHER_ADVERTISING_TYPES." in result["warnings"]
    assert "COMPARISON_DOES_NOT_ESTABLISH_PRICE_CHANGE_CAUSALITY." in result["warnings"]
    assert result["candidates"][0]["window_days"] == 7
    assert "confidence" not in result


def test_matching_fbo_buyout_estimate_models_compare_without_claiming_same_event_cohort():
    result = _assess([
        _fbo_buyout_model_candidate(100, "2026-10-01", "2026-10-07"),
        _fbo_buyout_model_candidate(95, "2026-10-08", "2026-10-14"),
    ])

    assert result["status"] == "COMPARABLE"
    assert result["evidence_basis"] == "MODELLED_FROM_OBSERVED_INPUTS"
    assert result["verified"] is False
    assert all(item["status"] == "READY" for item in result["candidates"])

    inconsistent = _assess([
        _fbo_buyout_model_candidate(100, "2026-10-01", "2026-10-07"),
        _fbo_buyout_model_candidate(
            95, "2026-10-08", "2026-10-14", returns_basis="ANOTHER_POSTING_BASIS",
        ),
    ])
    assert inconsistent["status"] == "INCOMPARABLE"
    assert "SOURCE_DATE_BASIS_MISMATCH" in inconsistent["reasons"]


def test_overlap_and_different_price_basis_block_comparison():
    overlapping = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"),
        _model_candidate(95, "2026-10-05", "2026-10-11"),
    ])
    assert overlapping["status"] == "INCOMPARABLE"
    assert "OBSERVATION_WINDOWS_OVERLAP" in overlapping["reasons"]
    assert all(item["status"] == "READY" for item in overlapping["candidates"])

    different_assumptions = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07", signature="plan-a"),
        _model_candidate(95, "2026-10-08", "2026-10-14", signature="plan-b"),
    ])
    assert "MODEL_ASSUMPTIONS_MISMATCH" in different_assumptions["reasons"]


def test_identity_source_basis_and_successful_unit_denominator_are_required():
    different_sku = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"),
        _model_candidate(95, "2026-10-08", "2026-10-14", sku="sku-2"),
    ])
    assert "PRODUCT_STORE_OR_SCHEME_MISMATCH" in different_sku["reasons"]

    different_owner = _model_candidate(95, "2026-10-08", "2026-10-14")
    different_owner["owner_id"] = "owner-b"
    scoped = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"), different_owner,
    ])
    assert "OWNER_OR_STORE_SCOPE_MISMATCH" in scoped["reasons"]

    different_source_basis = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"),
        _model_candidate(95, "2026-10-08", "2026-10-14", basis="REPORT_GENERATION_DATE"),
    ])
    assert "SOURCE_DATE_BASIS_MISMATCH" in different_source_basis["reasons"]

    missing_units = _model_candidate(95, "2026-10-08", "2026-10-14", units=None)
    missing_units["result"]["metrics"]["successful_unit_denominator"] = None
    no_denominator = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-07"), missing_units,
    ])
    assert "SUCCESSFUL_UNIT_DENOMINATOR_UNCONFIRMED" in no_denominator["reasons"]


def test_freshness_is_checked_against_oldest_required_source_timestamp():
    first = _model_candidate(100, "2026-10-01", "2026-10-07")
    first["result"]["sources"][0]["received_at"] = "2026-10-01T09:00:00+00:00"
    result = _assess([
        first, _model_candidate(95, "2026-10-08", "2026-10-14"),
    ])
    assert result["status"] == "INCOMPARABLE"
    assert "OBSERVATION_EVIDENCE_STALE" in result["reasons"]


def test_small_sample_and_short_window_are_warnings_not_confidence():
    result = _assess([
        _model_candidate(100, "2026-10-01", "2026-10-03", units=2),
        _model_candidate(95, "2026-10-08", "2026-10-10", units=3),
    ])
    assert result["status"] == "COMPARABLE"
    assert "OBSERVATION_WINDOW_SHORTER_THAN_RECOMMENDED." in result["warnings"]
    assert "SMALL_SUCCESSFUL_UNIT_SAMPLE." in result["warnings"]
    assert "SAMPLE_THRESHOLDS_ARE_OPERATIONAL_WARNINGS_NOT_STATISTICAL_CONFIDENCE." in result["warnings"]


def test_single_candidate_is_not_ready_and_does_not_claim_comparability():
    result = _assess([_model_candidate(100, "2026-10-01", "2026-10-07")])
    assert result["status"] == "NOT_READY"
    assert result["verified"] is False
    assert "AT_LEAST_TWO_PRICE_VARIANTS_REQUIRED" in result["reasons"]


def test_canonical_fact_requires_every_complete_axis_and_matching_source():
    def fact(price, start, end):
        result = _model_candidate(price, start, end)["result"]
        result["evidence_basis"] = "CANONICAL_FACT_COMPARABLE"
        result["metrics"].update({"observed_profit_per_unit": "10.00", "revenue_basis": "SELLER_REVENUE", "advertising_status": "COMPLETE"})
        result["completeness"] = {key: "CONFIRMED" for key in _COMPLETENESS}
        for name in ("FINANCE", "ANALYTICS", "PERFORMANCE", "RETURNS", "SELLER_PRICE", "TARIFF", "COST", "TAX"):
            result["sources"].append(_source(name, start, end))
        return {"owner_id": "owner-a", "store_id": "store-a", "result": result}

    verified = _assess([
        fact(100, "2026-10-01", "2026-10-07"),
        fact(95, "2026-10-08", "2026-10-14"),
    ])
    assert verified["status"] == "COMPARABLE"
    assert verified["evidence_basis"] == "CANONICAL_FACT_COMPARABLE"
    assert verified["verified"] is True

    incomplete = fact(95, "2026-10-08", "2026-10-14")
    incomplete["result"]["completeness"]["price_history"] = "PRICE_HISTORY_UNCONFIRMED"
    rejected = _assess([fact(100, "2026-10-01", "2026-10-07"), incomplete])
    assert rejected["verified"] is False
    assert "FACT_PRICE_HISTORY_INCOMPLETE" in rejected["reasons"]


def test_result_reason_codes_are_preserved_in_quality_payload():
    candidate = _model_candidate(100, "2026-10-01", "2026-10-07")
    candidate["result"]["warnings"].append("OTHER_ADVERTISING_TYPES_ARE_UNKNOWN.")
    result = _assess([candidate])
    assert any("CANONICAL_PER_SALE_PROFIT_NOT_AVAILABLE" in item for item in result["candidates"][0]["warnings"])
    assert "OTHER_ADVERTISING_TYPES_ARE_UNKNOWN." in result["candidates"][0]["warnings"]
