from copy import deepcopy

from product_decision_user_action_guidance import (
    build_product_decision_user_action_guidance,
)


def _verification(**values):
    application_id = "product-decision-persistence-application:ready-1"
    recorded_at = "2026-09-01T12:00:00+00:00"
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_PERSISTENCE_VERIFIED",
        "decision_persistence_verification_id":
            "product-decision-persistence-verification:" + application_id,
        "decision_persistence_application_id": application_id,
        "sku": "hook-2",
        "decision_persistence_verified": True,
        "verified_recorded_at": recorded_at,
        "verified_snapshot": {
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "HIGH",
            "confidence": "HIGH",
            "reasons": ["LOW_STOCK"],
            "recorded_at": recorded_at,
        },
        "mismatched_fields": [],
        "externally_verified": False,
        "persistent": True,
        "product_decision_recomputed": True,
        "product_decision_persisted": True,
        "product_decision_mutated": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_v841_non_mapping_verification_fails_closed():
    result = build_product_decision_user_action_guidance(
        ["not", "a", "mapping"]
    )

    assert result["error"] is True
    assert (
        result["code"]
        == "USER_ACTION_GUIDANCE_VERIFICATION_INPUT_INVALID"
    )
    assert result["executed"] is False


def test_v842_missing_explicit_verifier_success_marker_is_not_trusted():
    source = _verification()
    source.pop("error")

    result = build_product_decision_user_action_guidance(source)

    assert (
        result["code"]
        == "USER_ACTION_GUIDANCE_VERIFICATION_STATUS_INVALID"
    )


def test_v843_external_verification_overclaim_blocks_guidance():
    result = build_product_decision_user_action_guidance(
        _verification(externally_verified=True)
    )

    assert (
        result["code"]
        == "USER_ACTION_GUIDANCE_SAFETY_BOUNDARY_VIOLATION"
    )
    assert result["externally_verified"] is False


def test_v844_numeric_identity_is_not_coerced_into_guidance_lineage():
    source = _verification(sku=123)
    source["verified_snapshot"]["sku"] = 123

    result = build_product_decision_user_action_guidance(source)

    assert result["code"] == "USER_ACTION_GUIDANCE_CONTEXT_REQUIRED"


def test_v845_recorded_at_must_bind_verifier_and_snapshot():
    source = _verification(
        verified_recorded_at="2026-09-01T12:00:01+00:00"
    )

    result = build_product_decision_user_action_guidance(source)

    assert (
        result["code"]
        == "USER_ACTION_GUIDANCE_VERIFIED_RECORDING_MISMATCH"
    )


def test_v846_reasons_string_cannot_become_character_evidence():
    source = _verification()
    source["verified_snapshot"]["reasons"] = "LOW_STOCK"

    result = build_product_decision_user_action_guidance(source)

    assert result["code"] == "USER_ACTION_GUIDANCE_SNAPSHOT_INVALID"


def test_v847_unknown_priority_cannot_be_presented_as_verified_fact():
    source = _verification()
    source["verified_snapshot"]["priority"] = "URGENT"

    result = build_product_decision_user_action_guidance(source)

    assert result["code"] == "USER_ACTION_GUIDANCE_SNAPSHOT_INVALID"


def test_v848_unknown_confidence_cannot_be_presented_as_verified_fact():
    source = _verification()
    source["verified_snapshot"]["confidence"] = "CERTAIN"

    result = build_product_decision_user_action_guidance(source)

    assert result["code"] == "USER_ACTION_GUIDANCE_SNAPSHOT_INVALID"


def test_v849_nonempty_mismatch_evidence_blocks_even_verified_status():
    result = build_product_decision_user_action_guidance(
        _verification(mismatched_fields=["priority"])
    )

    assert (
        result["code"]
        == "USER_ACTION_GUIDANCE_VERIFICATION_MISMATCH_EVIDENCE_INVALID"
    )


def test_v850_valid_guidance_preserves_read_only_verified_lineage():
    source = _verification()
    before = deepcopy(source)

    result = build_product_decision_user_action_guidance(source)

    assert result["error"] is False
    assert (
        result["status"]
        == "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY"
    )
    assert result["decision_persistence_verified"] is True
    assert (
        result["verified_recorded_at"]
        == "2026-09-01T12:00:00+00:00"
    )
    assert result["confidence"] == "HIGH"
    assert result["reasons"] == ["LOW_STOCK"]
    assert result["externally_verified"] is False
    assert result["persistent"] is True
    assert result["user_execution_required"] is True
    assert result["automatic_execution_prohibited"] is True
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert source == before

    result["reasons"].append("MUTATED_COPY")
    assert source["verified_snapshot"]["reasons"] == ["LOW_STOCK"]
