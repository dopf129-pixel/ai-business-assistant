from copy import deepcopy

from app.product_task_freshness_evidence_draft_application import (
    apply_freshness_evidence_to_draft,
)


def _readiness(**values):
    result = {
        "application_readiness_id": "evidence-application-readiness:evidence-application-permission-signal:p1",
        "permission_signal_id": "evidence-application-permission-signal:p1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPLICATION_READY_FOR_SEPARATE_STEP",
        "application_ready": True,
        "application_review_complete": True,
        "application_allowed": False,
        "application_started": False,
        "readiness_evidence": {
            "sales_source_recorded_at": "2026-08-29T12:40:00+00:00",
            "stock_source_recorded_at": "2026-08-29T12:41:00+00:00",
        },
        "readiness_evidence_count": 2,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _draft(**values):
    result = {
        "draft_id": "d1",
        "sku": "hook-2",
        "decision": "KEEP_PRICE",
        "price": 1990,
        "notes": "unchanged business content",
    }
    result.update(values)
    return result


def test_applies_only_allowlisted_freshness_fields_and_keeps_business_fields():
    draft = _draft()
    business_snapshot = {key: draft[key] for key in ("decision", "price", "notes")}
    result = apply_freshness_evidence_to_draft(draft, _readiness())
    assert result["status"] == "FRESHNESS_EVIDENCE_APPLIED_TO_DRAFT"
    assert result["task_draft_mutated"] is True
    assert set(result["changed_fields"]) == {"sales_source_recorded_at", "stock_source_recorded_at"}
    assert draft["sales_source_recorded_at"] == "2026-08-29T12:40:00+00:00"
    assert draft["stock_source_recorded_at"] == "2026-08-29T12:41:00+00:00"
    assert {key: draft[key] for key in business_snapshot} == business_snapshot
    assert result["product_decision_recomputed"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False


def test_audit_records_before_and_after():
    draft = _draft(sales_source_recorded_at="old")
    result = apply_freshness_evidence_to_draft(draft, _readiness())
    assert result["audit"]["before"]["sales_source_recorded_at"] == "old"
    assert result["audit"]["after"]["sales_source_recorded_at"] == "2026-08-29T12:40:00+00:00"


def test_second_application_is_idempotent_noop():
    draft = _draft()
    readiness = _readiness()
    apply_freshness_evidence_to_draft(draft, readiness)
    snapshot = deepcopy(draft)
    result = apply_freshness_evidence_to_draft(draft, readiness)
    assert result["idempotent_noop"] is True
    assert result["changed_field_count"] == 0
    assert result["task_draft_mutated"] is False
    assert draft == snapshot


def test_unsafe_evidence_is_blocked_without_mutating_draft():
    draft = _draft()
    snapshot = deepcopy(draft)
    evidence = deepcopy(_readiness()["readiness_evidence"])
    evidence["price"] = 1
    result = apply_freshness_evidence_to_draft(
        draft,
        _readiness(readiness_evidence=evidence, readiness_evidence_count=3),
    )
    assert result["code"] == "READINESS_EVIDENCE_UNSAFE"
    assert draft == snapshot


def test_draft_id_mismatch_is_blocked_without_mutation():
    draft = _draft(draft_id="other")
    snapshot = deepcopy(draft)
    result = apply_freshness_evidence_to_draft(draft, _readiness())
    assert result["code"] == "DRAFT_ID_MISMATCH"
    assert draft == snapshot


def test_sku_mismatch_is_blocked_without_mutation():
    draft = _draft(sku="other")
    snapshot = deepcopy(draft)
    result = apply_freshness_evidence_to_draft(draft, _readiness())
    assert result["code"] == "DRAFT_SKU_MISMATCH"
    assert draft == snapshot


def test_forged_readiness_id_is_blocked_without_mutation():
    draft = _draft()
    snapshot = deepcopy(draft)
    result = apply_freshness_evidence_to_draft(
        draft,
        _readiness(application_readiness_id="evidence-application-readiness:wrong"),
    )
    assert result["code"] == "APPLICATION_READINESS_ID_MISMATCH"
    assert draft == snapshot


def test_not_ready_is_blocked_without_mutation():
    draft = _draft()
    snapshot = deepcopy(draft)
    result = apply_freshness_evidence_to_draft(draft, _readiness(application_ready=False))
    assert result["code"] == "APPLICATION_NOT_READY"
    assert draft == snapshot


def test_execution_boundary_violation_is_blocked():
    draft = _draft()
    result = apply_freshness_evidence_to_draft(draft, _readiness(execution_ready=True))
    assert result["code"] == "READINESS_SAFETY_BOUNDARY_VIOLATION"


def test_preexisting_application_boundary_violation_is_blocked():
    draft = _draft()
    result = apply_freshness_evidence_to_draft(draft, _readiness(application_allowed=True))
    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"


def test_missing_draft_is_blocked():
    result = apply_freshness_evidence_to_draft(None, _readiness())
    assert result["code"] == "DRAFT_REQUIRED"
