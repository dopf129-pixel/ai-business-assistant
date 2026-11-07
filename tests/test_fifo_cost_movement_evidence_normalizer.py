from services.fifo_cost_movement_evidence_normalizer import (
    FifoCostMovementEvidenceNormalizer as Normalizer,
)


def _normalize(**overrides):
    values = {
        "store_id": "store-a", "sku": "seller-sku",
        "movement_id": "owner-note-1", "reason_code": "HOME_SHORTAGE",
        "quantity": 2, "effective_date": "2026-11-04",
        "inventory_cutoff": "2026-11-01", "cutoff_bridge_confirmed": True,
    }
    values.update(overrides)
    return Normalizer.normalize(**values)


def test_outflow_identity_is_redacted_and_event_source_are_exact():
    candidate = _normalize()
    event = Normalizer.build_event(candidate)
    source = Normalizer.build_source(
        candidate, captured_at="2026-11-06T12:00:00Z",
    )

    assert candidate["eligible"] is True
    assert "owner-note-1" not in repr(candidate)
    assert event == {
        "kind": "NON_SALE_OUTFLOW", "quantity": 2,
        "effective_date": "2026-11-04", "inventory_cutoff": "2026-11-01",
        "source_identity_digest": candidate["source_identity_digest"],
        "reason_code": "HOME_SHORTAGE",
    }
    assert source["method"] == "OWNER_CONFIRMED_FIFO_NON_SALE_MOVEMENT"
    assert source["references"] == [{
        "kind": "OTHER", "digest": candidate["source_identity_digest"],
    }]


def test_missing_cutoff_and_bad_effective_date_fail_closed():
    assert _normalize(cutoff_bridge_confirmed=False)["reason_code"] == "INVENTORY_CUTOFF_UNRECONCILED"
    assert _normalize(effective_date="2026-11-01")["reason_code"] == "FIFO_MOVEMENT_EFFECTIVE_DATE_UNAVAILABLE"
    assert _normalize(quantity=0)["reason_code"] == "FIFO_MOVEMENT_EVIDENCE_INVALID"


def test_acceptance_shortfall_is_discrepancy_not_outflow():
    result = _normalize(
        reason_code="ACCEPTANCE_SHORTFALL", quantity=None,
        declared_quantity=200, accepted_quantity=100,
    )
    assert result["status"] == "FIFO_MOVEMENT_DISCREPANCY_ONLY"
    assert result["unreceived_quantity"] == 100
    assert result["inventory_change"] is False
    assert result["cost_impact_rub"] is None
    assert Normalizer.build_event(result)["eligible"] is False
    invalid = _normalize(
        reason_code="ACCEPTANCE_SHORTFALL", quantity=None,
        declared_quantity=100, accepted_quantity=200,
    )
    assert invalid["reason_code"] == "FIFO_ACCEPTANCE_COMPARISON_INVALID"


def test_transfer_is_pool_neutral_and_does_not_create_outflow():
    result = _normalize(
        reason_code="INVENTORY_TRANSFER", location_from="HOME",
        location_to="OZON", quantity=100,
    )
    assert result["status"] == "FIFO_MOVEMENT_POOL_NEUTRAL"
    assert result["inventory_change"] is False
    assert result["cost_impact_rub"] is None
