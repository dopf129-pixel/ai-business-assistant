from copy import deepcopy

from app.product_task_freshness_evidence_application_eligibility import (
    build_freshness_evidence_application_eligibility,
)


def _evidence():
    return {
        "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
        "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
    }


def _contract(**values):
    result = {
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPROVAL_REQUIRED",
        "approval_ready": True,
        "approval_required": True,
        "approval_granted": False,
        "application_allowed": False,
        "freshness_guard_validated": True,
        "preview_freshness_status": "FRESH",
        "validated_evidence": _evidence(),
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


def _signal(**values):
    result = {
        "signal_id": "evidence-signal:evidence-approval:d1",
        "approval_id": "evidence-approval:d1",
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "APPROVED",
        "decision": "APPROVE",
        "signal_ready": True,
        "approval_granted": True,
        "approval_rejected": False,
        "validated_evidence": _evidence(),
        "application_allowed": False,
        "application_started": False,
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


def test_approved_signal_becomes_eligible_for_review_without_allowing_application():
    contract = _contract()
    signal = _signal()
    contract_snapshot = deepcopy(contract)
    signal_snapshot = deepcopy(signal)

    result = build_freshness_evidence_application_eligibility(contract, signal)

    assert result["status"] == "ELIGIBLE_FOR_APPLICATION_REVIEW"
    assert result["application_eligible"] is True
    assert result["application_review_required"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert result["executed"] is False
    assert contract == contract_snapshot
    assert signal == signal_snapshot


def test_rejected_signal_is_ineligible():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(
            status="REJECTED",
            decision="REJECT",
            approval_granted=False,
            approval_rejected=True,
        ),
    )

    assert result["status"] == "APPLICATION_INELIGIBLE"
    assert result["code"] == "APPROVAL_SIGNAL_NOT_APPROVED"
    assert result["application_allowed"] is False


def test_contract_and_signal_identity_must_match():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(request_id="refresh:d2"),
    )

    assert result["code"] == "REQUEST_ID_MISMATCH"
    assert result["application_eligible"] is False


def test_signal_id_must_bind_to_approval_id():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(signal_id="evidence-signal:evidence-approval:d2"),
    )

    assert result["code"] == "SIGNAL_ID_MISMATCH"


def test_approved_evidence_must_match_contract_exactly():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(validated_evidence={
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
        }),
    )

    assert result["code"] == "APPROVED_EVIDENCE_MISMATCH"
    assert result["approved_evidence"] == {}


def test_unsafe_signal_evidence_is_blocked():
    evidence = _evidence()
    evidence["execution_allowed"] = True

    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(validated_evidence=evidence),
    )

    assert result["code"] == "SIGNAL_EVIDENCE_UNSAFE"
    assert result["execution_allowed"] is False


def test_signal_with_started_application_is_blocked():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(application_started=True),
    )

    assert result["code"] == "APPLICATION_ALREADY_STARTED"
    assert result["application_started"] is False


def test_signal_with_execution_boundary_violation_is_blocked():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(execution_ready=True),
    )

    assert result["code"] == "SIGNAL_SAFETY_BOUNDARY_VIOLATION"
    assert result["execution_ready"] is False


def test_forged_persistent_contract_is_blocked():
    result = build_freshness_evidence_application_eligibility(
        _contract(persistent=True),
        _signal(),
    )

    assert result["code"] == "CONTRACT_PERSISTENCE_BOUNDARY_VIOLATION"
    assert result["application_eligible"] is False


def test_forged_signal_cannot_claim_source_freshness():
    result = build_freshness_evidence_application_eligibility(
        _contract(),
        _signal(source_freshness_proven=True),
    )

    assert result["code"] == "SIGNAL_FRESHNESS_BOUNDARY_VIOLATION"
    assert result["source_freshness_proven"] is False
