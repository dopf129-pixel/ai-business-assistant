from copy import deepcopy

import pytest

from services.fifo_cost_return_evidence_normalizer import (
    FifoCostReturnEvidenceNormalizer,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)


@pytest.fixture
def evidence():
    return {
        "return_record": {
            "id": "private-return-1",
            "posting_number": "private-posting-1",
            "sku": "sku-private",
            "quantity": 2,
            "type": "ClientReturn",
            "visual_status_sys_name": "ArrivedAtReturnPlace",
            "compensation_status_sys_name": None,
        },
        "recovery_evidence": {
            "error": False,
            "return_id": "private-return-1",
            "posting_number": "private-posting-1",
            "sku": "sku-private",
            "quantity": 2,
            "recovery_state": "SALEABLE_RESTORED",
            "confirmed_on": "2026-11-05",
            "source": "SELLER_CONFIRMED_BOT",
            "inventory_recovery_confirmed": True,
        },
    }


def _normalize(evidence, **overrides):
    values = {
        "store_id": "store-private",
        "finance_sku": "sku-private",
        "identity": {
            "mapping_confirmed": True,
            "offer_id": "offer-private",
            "product_id": "product-private",
        },
        "return_record": evidence["return_record"],
        "recovery_evidence": evidence["recovery_evidence"],
        "return_sample_complete": True,
        "inventory_cutoff": "2026-11-01",
        "cutoff_bridge_confirmed": True,
    }
    values.update(overrides)
    return FifoCostReturnEvidenceNormalizer.normalize(**values)


def test_owner_confirmed_saleable_return_produces_redacted_join_keys(evidence):
    result = _normalize(evidence)
    sale = FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id="store-private",
        posting_number="private-posting-1",
        finance_sku="sku-private",
        identity={
            "mapping_confirmed": True,
            "offer_id": "offer-private",
            "product_id": "product-private",
        },
    )

    assert result["eligible"] is True
    assert result["effective_date"] == "2026-11-05"
    assert result["quantity"] == 2
    assert result["origin_sale_identity_digest"] == sale["source_identity_digest"]
    assert len(result["source_identity_digest"]) == 64
    assert "private-return-1" not in repr(result)
    assert "private-posting-1" not in repr(result)
    assert "sku-private" not in repr(result)


def test_ready_candidate_builds_only_owner_confirmed_source_and_exact_return_event(evidence):
    candidate = _normalize(evidence)
    event = FifoCostReturnEvidenceNormalizer.build_event(
        candidate, origin_sale_event_id="evt_" + "a" * 32,
    )
    source = FifoCostReturnEvidenceNormalizer.build_command_source(
        candidate, captured_at="2026-11-06T12:00:00Z",
    )

    assert event == {
        "kind": "SALEABLE_RETURN_RESTOCK",
        "quantity": 2,
        "effective_date": "2026-11-05",
        "inventory_cutoff": "2026-11-01",
        "source_identity_digest": candidate["source_identity_digest"],
        "supersedes_event_id": "evt_" + "a" * 32,
    }
    assert source["kind"] == "OWNER_CONFIRMATION"
    assert source["method"] == "OWNER_CONFIRMED_SALEABLE_RETURN_RECOVERY"
    assert {row["digest"] for row in source["references"]} == {
        candidate["source_identity_digest"],
        candidate["origin_sale_identity_digest"],
    }
    assert "private-return-1" not in repr(source)
    assert "private-posting-1" not in repr(source)


def test_forged_ready_flag_cannot_build_a_fifo_write_candidate():
    forged = FifoCostReturnEvidenceNormalizer.build_command_source(
        {"eligible": True}, captured_at="2026-11-06T12:00:00Z",
    )

    assert forged["eligible"] is False
    assert forged["reason_code"] == "FIFO_RETURN_EVIDENCE_INVALID"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("return_sample_complete", False, "FIFO_RETURN_SOURCE_INCOMPLETE"),
        ("cutoff_bridge_confirmed", False, "INVENTORY_CUTOFF_UNRECONCILED"),
        ("inventory_cutoff", "2026-13-01", "INVENTORY_CUTOFF_UNRECONCILED"),
    ],
)
def test_incomplete_source_and_unconfirmed_cutoff_fail_closed(
    evidence, field, value, reason,
):
    result = _normalize(evidence, **{field: value})

    assert result["eligible"] is False
    assert result["reason_code"] == reason
    assert result["source_identity_digest"] is None


@pytest.mark.parametrize(
    ("record_field", "value", "reason"),
    [
        ("type", "Cancellation", "FIFO_RETURN_IDENTITY_OR_TYPE_INVALID"),
        ("visual_status_sys_name", "ReturnedToOzon", "FIFO_RETURN_PLACE_STATUS_UNCONFIRMED"),
        ("compensation_status_sys_name", "Received", "FIFO_RETURN_COMPENSATION_UNRESOLVED"),
        ("quantity", 1, "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED"),
        ("sku", "other-sku", "FIFO_RETURN_IDENTITY_OR_TYPE_INVALID"),
    ],
)
def test_return_record_status_type_identity_and_quantity_are_exact(
    evidence, record_field, value, reason,
):
    changed = deepcopy(evidence)
    changed["return_record"][record_field] = value
    result = _normalize(changed)

    assert result["eligible"] is False
    assert result["reason_code"] == reason


@pytest.mark.parametrize(
    ("recovery_field", "value"),
    [
        ("recovery_state", "NON_SALEABLE"),
        ("source", "MANUAL_IMPORT"),
        ("inventory_recovery_confirmed", False),
        ("return_id", "other-return"),
        ("posting_number", "other-posting"),
        ("sku", "other-sku"),
        ("quantity", 1),
        ("confirmed_on", "2026-11-01"),
    ],
)
def test_recovery_requires_exact_owner_confirmation_and_post_cutoff_date(
    evidence, recovery_field, value,
):
    changed = deepcopy(evidence)
    changed["recovery_evidence"][recovery_field] = value
    result = _normalize(changed)

    assert result["eligible"] is False
    assert result["reason_code"] in {
        "FIFO_RETURN_SALEABLE_RECOVERY_UNCONFIRMED",
        "FIFO_RETURN_EFFECTIVE_DATE_UNAVAILABLE",
    }


def test_missing_identity_mapping_and_invalid_quantity_are_not_guessed(evidence):
    no_mapping = _normalize(evidence, identity={"mapping_confirmed": False})
    bad_quantity = deepcopy(evidence)
    bad_quantity["return_record"]["quantity"] = True

    assert no_mapping["eligible"] is False
    assert no_mapping["reason_code"] == "FIFO_SALE_PRODUCT_IDENTITY_UNCONFIRMED"
    assert _normalize(bad_quantity)["eligible"] is False
