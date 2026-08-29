from copy import deepcopy


ALLOWED_DECISIONS = {"APPROVE", "REJECT"}


def build_freshness_evidence_approval_signal(
    approval_contract,
    decision,
):
    contract = deepcopy(approval_contract or {})
    normalized_decision = str(decision or "").strip().upper()

    context_error = _context_error(contract)
    if context_error:
        return _blocked(contract, normalized_decision, context_error)

    if contract.get("status") != "APPROVAL_REQUIRED":
        return _blocked(contract, normalized_decision, "APPROVAL_CONTRACT_NOT_READY")
    if contract.get("approval_ready") is not True:
        return _blocked(contract, normalized_decision, "APPROVAL_NOT_READY")
    if contract.get("approval_required") is not True:
        return _blocked(contract, normalized_decision, "APPROVAL_NOT_REQUIRED")
    if contract.get("freshness_guard_validated") is not True:
        return _blocked(contract, normalized_decision, "FRESHNESS_NOT_VALIDATED")
    if contract.get("preview_freshness_status") != "FRESH":
        return _blocked(contract, normalized_decision, "FRESHNESS_NOT_VALIDATED")
    if contract.get("application_allowed") is not False:
        return _blocked(contract, normalized_decision, "APPLICATION_BOUNDARY_VIOLATION")
    if normalized_decision not in ALLOWED_DECISIONS:
        return _blocked(contract, normalized_decision, "APPROVAL_DECISION_INVALID")

    validated_evidence = deepcopy(contract.get("validated_evidence") or {})
    if not validated_evidence:
        return _blocked(contract, normalized_decision, "VALIDATED_EVIDENCE_REQUIRED")

    approved = normalized_decision == "APPROVE"
    return {
        "error": False,
        "signal_id": "evidence-signal:" + str(contract.get("approval_id")),
        "approval_id": contract.get("approval_id"),
        "request_id": contract.get("request_id"),
        "draft_id": contract.get("draft_id"),
        "sku": contract.get("sku"),
        "status": "APPROVED" if approved else "REJECTED",
        "decision": normalized_decision,
        "signal_ready": True,
        "approval_granted": approved,
        "approval_rejected": not approved,
        "validated_evidence": validated_evidence,
        "validated_evidence_count": len(validated_evidence),
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


def _context_error(contract):
    approval_id = str(contract.get("approval_id") or "").strip()
    request_id = str(contract.get("request_id") or "").strip()
    draft_id = str(contract.get("draft_id") or "").strip()
    sku = str(contract.get("sku") or "").strip()
    if not all((approval_id, request_id, draft_id, sku)):
        return "APPROVAL_CONTEXT_REQUIRED"
    return None


def _blocked(contract, decision, code):
    return {
        "error": True,
        "code": code,
        "signal_id": None,
        "approval_id": contract.get("approval_id"),
        "request_id": contract.get("request_id"),
        "draft_id": contract.get("draft_id"),
        "sku": contract.get("sku"),
        "status": "SIGNAL_BLOCKED",
        "decision": decision or None,
        "signal_ready": False,
        "approval_granted": False,
        "approval_rejected": False,
        "validated_evidence": {},
        "validated_evidence_count": 0,
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
