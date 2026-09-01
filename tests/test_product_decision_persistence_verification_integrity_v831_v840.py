from copy import deepcopy

from services.product_decision_persistence_verification_service import (
    ProductDecisionPersistenceVerificationService,
)


class FakeHistoryService:
    def __init__(self, latest):
        self.latest_value = deepcopy(latest)
        self.calls = []

    def latest(self, sku):
        self.calls.append(sku)
        return deepcopy(self.latest_value)


def _ids():
    preview_id = "product-decision-recompute-preview:auth-1"
    delta_id = "product-decision-preview-delta:" + preview_id
    review_id = "product-decision-preview-review:" + delta_id
    eligibility_id = "product-decision-persistence-eligibility:" + review_id
    authorization_id = (
        "product-decision-persistence-authorization:" + eligibility_id
    )
    readiness_id = (
        "product-decision-persistence-application-readiness:"
        + authorization_id
    )
    application_id = "product-decision-persistence-application:" + readiness_id
    return (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    )


def _decision(**values):
    result = {
        "sku": "hook-2",
        "product_id": 123,
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "sales_velocity": 4.2,
        "current_stock": 30,
        "days_of_stock": 7.1,
        "decision_profit_per_unit": 35.10,
        "decision_margin_percent": 36.56,
        "economics_basis": "CURRENT_PRICE",
    }
    result.update(values)
    return result


def _snapshot(**values):
    result = {
        "sku": "hook-2",
        "product_id": 123,
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "sales_velocity": 4.2,
        "current_stock": 30,
        "days_of_stock": 7.1,
        "profit_per_unit": 35.10,
        "margin_percent": 36.56,
        "economics_basis": "CURRENT_PRICE",
        "recorded_at": "2026-08-29T15:10:00+00:00",
    }
    result.update(values)
    return result


def _application(**values):
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    ) = _ids()
    result = {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLIED",
        "decision_persistence_application_id": application_id,
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": True,
        "decision_persistence_application_completed": True,
        "history_context": {
            "decision_history_available": True,
            "decision_recorded_at": "2026-08-29T15:10:00+00:00",
            "decision_history_count": 2,
        },
        "history_persistence_receipt": {
            "error": False,
            "code": None,
            "sku": "hook-2",
            "saved": True,
            "persistence_state": "COMMITTED",
            "decision_recorded_at": "2026-08-29T15:10:00+00:00",
            "decision_history_count": 2,
            "history_context": {
                "decision_history_available": True,
                "decision_recorded_at": "2026-08-29T15:10:00+00:00",
                "decision_history_count": 2,
            },
        },
        "persisted_preview_decision": _decision(),
        "persistent": True,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _verify(application=None, snapshot=None):
    history = FakeHistoryService(snapshot or _snapshot())
    service = ProductDecisionPersistenceVerificationService(history)
    result = service.verify(
        _application() if application is None else application
    )
    return result, history


def test_v831_non_mapping_application_fails_closed():
    result, history = _verify(application=["not", "a", "mapping"])

    assert result["error"] is True
    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_APPLICATION_INPUT_INVALID"
    )
    assert result["decision_persistence_verified"] is False
    assert history.calls == []


def test_v832_numeric_identity_is_not_coerced_into_verified_lineage():
    application = _application(sku=123)
    application["persisted_preview_decision"]["sku"] = 123
    snapshot = _snapshot(sku=123)

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_CONTEXT_REQUIRED"
    )
    assert history.calls == []


def test_v833_non_boolean_preview_error_marker_is_not_trusted():
    application = _application()
    application["persisted_preview_decision"]["error"] = "false"

    result, history = _verify(application=application)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID"
    )
    assert history.calls == []


def test_v834_matching_string_reasons_cannot_verify_as_character_evidence():
    application = _application()
    application["persisted_preview_decision"]["reasons"] = (
        "POSITIVE_UNIT_PROFIT"
    )
    snapshot = _snapshot(reasons="POSITIVE_UNIT_PROFIT")

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID"
    )
    assert history.calls == []


def test_v835_unknown_decision_type_cannot_be_verified_as_business_fact():
    application = _application()
    application["persisted_preview_decision"]["decision_type"] = "UNKNOWN"
    snapshot = _snapshot(decision_type="UNKNOWN")

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID"
    )
    assert history.calls == []


def test_v836_unknown_priority_cannot_be_verified_as_business_fact():
    application = _application()
    application["persisted_preview_decision"]["priority"] = "URGENT"
    snapshot = _snapshot(priority="URGENT")

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID"
    )
    assert history.calls == []


def test_v837_unknown_confidence_cannot_be_verified_as_business_fact():
    application = _application()
    application["persisted_preview_decision"]["confidence"] = "CERTAIN"
    snapshot = _snapshot(confidence="CERTAIN")

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID"
    )
    assert history.calls == []


def test_v838_numeric_recorded_at_cannot_bind_verification_lineage():
    application = _application()
    application["history_context"]["decision_recorded_at"] = 123
    snapshot = _snapshot(recorded_at=123)

    result, history = _verify(application=application, snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_REQUIRED"
    )
    assert history.calls == []


def test_v839_non_string_reason_item_in_history_fails_closed():
    snapshot = _snapshot(reasons=[123])

    result, history = _verify(snapshot=snapshot)

    assert (
        result["code"]
        == "DECISION_PERSISTENCE_VERIFICATION_HISTORY_SNAPSHOT_INVALID"
    )
    assert history.calls == ["hook-2"]


def test_v840_valid_verification_remains_read_only_and_non_external():
    application = _application()
    snapshot = _snapshot()
    result, history = _verify(application=application, snapshot=snapshot)

    assert result["error"] is False
    assert result["decision_persistence_verified"] is True
    assert result["verified_snapshot"] == snapshot
    assert result["externally_verified"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
    assert history.calls == ["hook-2"]

    result["verified_snapshot"]["reasons"].append("MUTATED_COPY")
    assert snapshot["reasons"] == ["POSITIVE_UNIT_PROFIT"]
