from datetime import datetime, timezone

import pytest

from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer


CAPTURED = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
IDENTITY = {"product_id": "101", "offer_id": "hook-2", "sku": "3921245627"}


def _stock_response(*, present=300, reserved=40, total_items=1):
    return {
        "total_items": total_items,
        "items": [{
            "product_id": 101,
            "stocks": [
                {"type": "fbo", "present": present, "reserved": reserved},
                {"type": "fbs", "present": 999, "reserved": 0},
            ],
        }],
    }


def _act_payloads(*, acts=None, agreement=True):
    if acts is None:
        acts = [{"act_id": 7001, "fact_quantity": 100, "sku": 3921245627}]
    summaries = []
    product_acts = []
    for act in acts:
        summaries.append({
            "type": "ACCEPTANCE",
            "act_state": "ACCEPTED",
            "act_id": act["act_id"],
            **({"created_date": act["created_date"]} if "created_date" in act else {}),
            "summary": {
                "fact_quantity": act["fact_quantity"],
                "unidentified_quantity": 0,
            },
        })
        product_acts.append({
            "type": "ACCEPTANCE",
            "act_id": act["act_id"],
            "items": [{
                "sku_info": {"sku": act["sku"]},
                **({"declared_quantity": act["declared_quantity"]} if "declared_quantity" in act else {}),
                **({"approved_quantity": act["approved_quantity"]} if "approved_quantity" in act else {}),
                "fact_quantity": act["fact_quantity"],
                "unidentified_quantity": 0,
            }],
        })
    return (
        {"supply_acts": product_acts},
        {"supplies_acts": [{
            "supply_id": 2001,
            "is_agreement_completed": agreement,
            "supply_acts": summaries,
        }]},
    )


@pytest.fixture
def normalizer():
    return FifoCostSourceNormalizer()


def _normalize_stock(normalizer, response, **overrides):
    args = {
        "identity": IDENTITY,
        "store_id": "store-a",
        "captured_at": CAPTURED,
        "pagination_complete": True,
        "identity_mapping_confirmed": True,
        "field_semantics_confirmed": True,
        "transit_units": 50,
        "transit_complete": True,
        "transit_overlap_confirmed": True,
    }
    args.update(overrides)
    return normalizer.normalize_stock_snapshot(response, **args)


def test_stock_keeps_reserved_inside_fbo_and_transit_disjoint(normalizer):
    result = _normalize_stock(normalizer, _stock_response())

    assert result.status == "COMPLETE"
    assert result.fbo_units == 300
    assert result.reserved_units == 40
    assert result.available_units == 260
    assert result.transit_units == 50
    assert result.transit_status == "DISJOINT_CONFIRMED"
    # Home stock is owner evidence and is intentionally not inferred/added here.
    old_pool_units = result.fbo_units + result.transit_units + 100
    assert old_pool_units == 450
    assert old_pool_units != result.available_units + result.transit_units + 100
    assert result.source_as_of is None
    assert result.anchor_eligible is False
    assert "INVENTORY_CUTOFF_UNRECONCILED" in result.issue_codes


def test_stock_semantics_and_transit_overlap_remain_unknown_by_default(normalizer):
    result = _normalize_stock(
        normalizer,
        _stock_response(),
        field_semantics_confirmed=False,
        transit_overlap_confirmed=False,
    )

    assert result.status == "PARTIAL"
    assert result.fbo_units == 300  # observed, not approved for an anchor
    assert result.available_units is None
    assert result.transit_units is None
    assert result.transit_status == "UNKNOWN"
    assert "STOCK_SEMANTICS_UNCONFIRMED" in result.issue_codes
    assert "TRANSIT_OVERLAP_UNRESOLVED" in result.issue_codes


def test_unconfirmed_catalog_product_to_sku_mapping_is_partial(normalizer):
    result = _normalize_stock(
        normalizer,
        _stock_response(),
        identity_mapping_confirmed=False,
    )

    assert result.status == "PARTIAL"
    assert result.available_units is None
    assert "PRODUCT_SKU_MAPPING_UNCONFIRMED" in result.issue_codes


def test_stock_incomplete_total_items_is_partial_and_not_zero(normalizer):
    result = _normalize_stock(
        normalizer,
        _stock_response(total_items=2),
        pagination_complete=True,
    )

    assert result.status == "PARTIAL"
    assert result.pagination_complete is False
    # A truncated page is not published as a total or a partial anchor count.
    assert result.fbo_units is None
    assert result.available_units is None
    assert result.source_status == "PARTIAL"


def test_stock_total_items_below_returned_rows_is_conflict(normalizer):
    result = _normalize_stock(
        normalizer,
        _stock_response(total_items=0),
    )

    assert result.status == "CONFLICT"
    assert "TOTAL_ITEMS_BELOW_ROWS" in result.issue_codes


def test_complete_empty_stock_response_is_not_confirmed_zero(normalizer):
    result = _normalize_stock(
        normalizer,
        {"total_items": 0, "items": []},
    )

    assert result.status == "EMPTY"
    assert result.fbo_units is None
    assert result.available_units is None


def test_exact_product_with_confirmed_zero_is_distinct_from_empty(normalizer):
    result = _normalize_stock(
        normalizer,
        _stock_response(present=0, reserved=0),
    )

    assert result.status == "CONFIRMED_ZERO"
    assert result.fbo_units == 0
    assert result.reserved_units == 0
    assert result.available_units == 0


def test_stock_rejects_boolean_and_fractional_quantities(normalizer):
    for bad in (True, 1.5, -1, "3"):
        result = _normalize_stock(normalizer, _stock_response(present=bad))
        assert result.status == "INVALID"
        assert result.fbo_units is None


def test_stock_rejects_reserved_greater_than_present(normalizer):
    result = _normalize_stock(normalizer, _stock_response(present=2, reserved=3))

    assert result.status == "CONFLICT"
    assert "RESERVED_EXCEEDS_PRESENT" in result.issue_codes


def test_conflicting_duplicate_product_rows_do_not_sum(normalizer):
    response = _stock_response()
    response["items"].append({
        "product_id": 101,
        "stocks": [{"type": "fbo", "present": 200, "reserved": 10}],
    })
    result = _normalize_stock(normalizer, response)

    assert result.status == "CONFLICT"
    assert result.fbo_units is None


def test_unfiltered_product_row_cannot_be_misreported_as_empty(normalizer):
    response = _stock_response()
    response["items"][0]["product_id"] = 999
    result = _normalize_stock(normalizer, response)

    assert result.status == "CONFLICT"
    assert "PRODUCT_SCOPE_MISMATCH" in result.issue_codes


def test_unknown_stock_type_makes_snapshot_partial(normalizer):
    response = _stock_response(present=0, reserved=0)
    response["items"][0]["stocks"] = [{
        "type": "NEW_UNKNOWN_TYPE", "present": 50, "reserved": 0,
    }]
    result = _normalize_stock(normalizer, response)

    assert result.status == "PARTIAL"
    assert result.fbo_units == 0
    assert "STOCK_TYPE_UNKNOWN" in result.issue_codes


def test_duplicate_identical_product_representation_is_deduplicated(normalizer):
    response = _stock_response()
    response["items"].append(dict(response["items"][0]))
    result = _normalize_stock(normalizer, response)

    assert result.fbo_units == 300


def test_stock_fingerprint_contains_only_hash_and_allowlisted_identity(normalizer):
    result = _normalize_stock(normalizer, _stock_response())

    assert len(result.source_fingerprint) == 64
    assert "hook-2" not in result.source_fingerprint


def test_supply_lines_reconcile_to_summary_without_double_counting(normalizer):
    products, summary = _act_payloads()
    result = normalizer.normalize_supply_act_snapshot(
        products,
        summary,
        store_id="store-a",
        expected_supply_id=2001,
        captured_at=CAPTURED,
        products_complete=True,
        summary_complete=True,
    )

    assert result.status == "COMPLETE"
    assert result.units_by_sku == (("3921245627", 100),)
    assert result.effective_at is None
    assert result.supply_ref != "2001"
    assert result.act_refs and all(len(value) == 64 for value in result.act_refs)


def test_multiple_partial_acts_for_one_supply_sum_by_same_exact_sku(normalizer):
    products, summary = _act_payloads(acts=[
        {"act_id": 7001, "fact_quantity": 60, "sku": 3921245627},
        {"act_id": 7002, "fact_quantity": 40, "sku": 3921245627},
    ])
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "COMPLETE"
    assert result.units_by_sku == (("3921245627", 100),)
    assert len(result.act_refs) == 2


def test_partial_acceptance_preserves_declared_approved_fact_and_document_date_separately(normalizer):
    products, summary = _act_payloads(acts=[{
        "act_id": 7001,
        "declared_quantity": 200,
        "approved_quantity": 0,
        "fact_quantity": 100,
        "created_date": "2026-09-28",
        "sku": 3921245627,
    }])
    result = normalizer.normalize_supply_act_snapshot(
        products,
        summary,
        store_id="store-a",
        expected_supply_id=2001,
        expected_order_id=11,
        captured_at=CAPTURED,
        products_complete=True,
        summary_complete=True,
    )

    assert result.status == "COMPLETE"
    assert result.units_by_sku == (("3921245627", 100),)
    assert result.act_evidence[0].declared_quantity == 200
    assert result.act_evidence[0].approved_quantity == 0
    assert result.act_evidence[0].fact_quantity == 100
    assert result.act_evidence[0].created_date == "2026-09-28"
    assert result.effective_at is None
    assert result.order_ref != "11"
    assert "7001" not in repr(result)


def test_identical_supply_refresh_has_stable_evidence_fingerprint(normalizer):
    products, summary = _act_payloads()
    first = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        expected_order_id=11, captured_at=CAPTURED,
        products_complete=True, summary_complete=True,
    )
    refreshed = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        expected_order_id=11,
        captured_at=datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc),
        products_complete=True, summary_complete=True,
    )

    assert first.evidence_fingerprint == refreshed.evidence_fingerprint
    assert first.source_fingerprint != refreshed.source_fingerprint


def test_multiple_acts_with_different_skus_require_explicit_split(normalizer):
    products, summary = _act_payloads(acts=[
        {"act_id": 7001, "fact_quantity": 60, "sku": 3921245627},
        {"act_id": 7002, "fact_quantity": 40, "sku": 3921245628},
    ])
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "CONFLICT"
    assert result.units_by_sku is None
    assert "SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS" in result.issue_codes


def test_duplicate_representation_of_same_act_is_deduplicated(normalizer):
    products, summary = _act_payloads()
    products["supply_acts"].append(dict(products["supply_acts"][0]))
    summary["supplies_acts"][0]["supply_acts"].append(
        dict(summary["supplies_acts"][0]["supply_acts"][0])
    )
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "COMPLETE"
    assert result.units_by_sku == (("3921245627", 100),)
    assert len(result.act_refs) == 1


def test_supply_summary_mismatch_is_conflict_not_sum(normalizer):
    products, summary = _act_payloads()
    summary["supplies_acts"][0]["supply_acts"][0]["summary"]["fact_quantity"] = 101
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "CONFLICT"
    assert result.units_by_sku is None
    assert "SUPPLY_SUMMARY_LINE_MISMATCH" in result.issue_codes


def test_supply_multiple_skus_require_explicit_split(normalizer):
    products, summary = _act_payloads()
    products["supply_acts"][0]["items"].append({
        "sku_info": {"sku": 3921245628},
        "fact_quantity": 0,
        "unidentified_quantity": 0,
    })
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "CONFLICT"
    assert "SUPPLY_PRODUCT_IDENTITY_AMBIGUOUS" in result.issue_codes


def test_supply_unidentified_quantity_blocks_normalization(normalizer):
    products, summary = _act_payloads()
    summary["supplies_acts"][0]["supply_acts"][0]["summary"]["unidentified_quantity"] = 1
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "PARTIAL"
    assert result.units_by_sku is None


def test_partial_supply_reads_never_publish_units(normalizer):
    products, summary = _act_payloads()
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=False, summary_complete=True,
    )

    assert result.status == "PARTIAL"
    assert result.units_by_sku is None


def test_no_act_in_complete_sources_is_empty_not_confirmed_zero(normalizer):
    products, summary = _act_payloads(acts=[])
    summary["supplies_acts"][0]["supply_acts"] = []
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "EMPTY"
    assert result.units_by_sku is None


def test_unconfirmed_act_state_is_partial_not_empty(normalizer):
    products, summary = _act_payloads()
    summary["supplies_acts"][0]["supply_acts"][0]["act_state"] = "NEW_UNKNOWN_STATE"
    result = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert result.status == "PARTIAL"
    assert result.units_by_sku is None
    assert "SUPPLY_ACT_STATE_UNCONFIRMED" in result.issue_codes


def test_incomplete_agreement_and_api_error_are_not_zero(normalizer):
    products, summary = _act_payloads(agreement=False)
    partial = normalizer.normalize_supply_act_snapshot(
        products, summary, store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )
    unavailable = normalizer.normalize_supply_act_snapshot(
        {"error": True, "code": "OZON_HTTP_ERROR"}, summary,
        store_id="store-a", expected_supply_id=2001,
        captured_at=CAPTURED, products_complete=True, summary_complete=True,
    )

    assert partial.status == "PARTIAL"
    assert unavailable.status == "UNAVAILABLE"

