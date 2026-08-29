from copy import deepcopy

from app.product_task_freshness_evidence_approval_signal import (
    build_freshness_evidence_approval_signal,
)


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
        "validated_evidence": {
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
        },
        "executed": False,
    }
    result.update(values)
    return result


def test_explicit_approve_creates_signal_without_allowing_application():
    contract = _contract()
    snapshot = deepcopy(contract)

    result = build_freshness_evidence_approval_signal(contract, "approve")

    assert result["status"] == "APPROVED"
    assert result["decision"] == "APPROVE"
    assert result["approval_granted"] is True
    assert result["application_allowed"] is False
    assert result["application_started"] is False
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert result["executed"] is False
    assert contract == snapshot


def test_explicit_reject_creates_rejected_signal_without_side_effects():
    result = build_freshness_evidence_approval_signal(_contract(), "REJECT")

    assert result["status"] == "REJECTED"
    assert result["approval_granted"] is False
    assert result["approval_rejected"] is True
    assert result["application_allowed"] is False
    assert result["task_draft_mutated"] is False


def test_invalid_decision_is_blocked():
    result = build_freshness_evidence_approval_signal(_contract(), "later")

    assert result["status"] == "SIGNAL_BLOCKED"
    assert result["code"] == "APPROVAL_DECISION_INVALID"
    assert result["approval_granted"] is False


def test_missing_approval_context_is_blocked():
    contract = _contract()
    contract.pop("request_id")

    result = build_freshness_evidence_approval_signal(contract, "APPROVE")

    assert result["code"] == "APPROVAL_CONTEXT_REQUIRED"
    assert result["signal_ready"] is False


def test_non_ready_contract_cannot_be_approved():
    result = build_freshness_evidence_approval_signal(
        _contract(status="APPROVAL_BLOCKED", approval_ready=False),
        "APPROVE",
    )

    assert result["code"] == "APPROVAL_CONTRACT_NOT_READY"
    assert result["approval_granted"] is False


def test_forged_non_fresh_contract_is_blocked():
    result = build_freshness_evidence_approval_signal(
        _contract(preview_freshness_status="STALE"),
        "APPROVE",
    )

    assert result["code"] == "FRESHNESS_NOT_VALIDATED"
    assert result["application_allowed"] is False


def test_contract_that_already_allows_application_is_rejected():
    result = build_freshness_evidence_approval_signal(
        _contract(application_allowed=True),
        "APPROVE",
    )

    assert result["code"] == "APPLICATION_BOUNDARY_VIOLATION"
    assert result["approval_granted"] is False
    assert result["execution_ready"] is False


def test_approval_id_must_be_bound_to_same_draft():
    result = build_freshness_evidence_approval_signal(
        _contract(approval_id="evidence-approval:d2"),
        "APPROVE",
    )

    assert result["code"] == "APPROVAL_ID_MISMATCH"
    assert result["approval_granted"] is False


def test_validated_evidence_must_remain_whitelisted():
    result = build_freshness_evidence_approval_signal(
        _contract(validated_evidence={
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "execution_allowed": True,
        }),
        "APPROVE",
    )

    assert result["code"] == "VALIDATED_EVIDENCE_UNSAFE"
    assert result["validated_evidence"] == {}
    assert result["application_allowed"] is False


def test_contract_cannot_arrive_with_prior_approval_signal():
    result = build_freshness_evidence_approval_signal(
        _contract(approval_granted=True),
        "APPROVE",
    )

    assert result["code"] == "APPROVAL_SIGNAL_ALREADY_PRESENT"
    assert result["signal_ready"] is False
    assert result["application_started"] is False
