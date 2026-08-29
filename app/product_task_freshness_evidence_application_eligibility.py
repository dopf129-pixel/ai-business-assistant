from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


def build_freshness_evidence_application_eligibility(
    approval_contract,
    approval_signal,
):
    contract = deepcopy(approval_contract or {})
    signal = deepcopy(approval_signal or {})

    context_error = _context_error(contract, signal)
    if context_error:
        return _blocked(contract, signal, context_error)

    if contract.get("status") != "APPROVAL_REQUIRED":
        return _blocked(contract, signal, "APPROVAL_CONTRACT_NOT_READY")
    if contract.get("approval_ready") is not True:
        return _blocked(contract, signal, "APPROVAL_NOT_READY")
    if contract.get("approval_required") is not True:
        return _blocked(contract, signal, "APPROVAL_NOT_REQUIRED")
    if contract.get("freshness_guard_validated") is not True:
        return _blocked(contract, signal, "FRESHNESS_NOT_VALIDATED")
    if contract.get("preview_freshness_status") != "FRESH":
        return _blocked(contract, signal, "FRESHNESS_NOT_VALIDATED")
    if contract.get("application_allowed") is not False:
        return _blocked(contract, signal, "APPLICATION_BOUNDARY_VIOLATION")

    if signal.get("status") != "APPROVED":
        return _blocked(contract, signal, "APPROVAL_SIGNAL_NOT_APPROVED")
    if signal.get("decision") != "APPROVE":
        return _blocked(contract, signal, "APPROVAL_SIGNAL_NOT_APPROVED")
    if signal.get("signal_ready") is not True:
        return _blocked(contract, signal, "APPROVAL_SIGNAL_NOT_READY")
    if signal.get("approval_granted") is not True:
        return _blocked(contract, signal, "APPROVAL_SIGNAL_NOT_APPROVED")
    if signal.get("approval_rejected") is not False:
        return _blocked(contract, signal, "APPROVAL_SIGNAL_CONFLICT")
    if signal.get("application_allowed") is not False:
        return _blocked(contract, signal, "APPLICATION_BOUNDARY_VIOLATION")
    if signal.get("application_started") is not False:
        return _blocked(contract, signal, "APPLICATION_ALREADY_STARTED")
    if signal.get("persistent") is not False:
        return _blocked(contract, signal, "SIGNAL_PERSISTENCE_BOUNDARY_VIOLATION")
    if any(signal.get(field) is not False for field in (
        "product_decision_recomputed",
        "product_decision_mutated",
        "task_draft_mutated",
        "execution_allowed",
        "execution_ready",
        "executed",
    )):
        return _blocked(contract, signal, "SIGNAL_SAFETY_BOUNDARY_VIOLATION")

    contract_evidence = _safe_evidence(contract.get("validated_evidence") or {})
    signal_evidence = _safe_evidence(signal.get("validated_evidence") or {})
    if not contract_evidence or not signal_evidence:
        return _blocked(contract, signal, "VALIDATED_EVIDENCE_REQUIRED")
    if contract_evidence != contract.get("validated_evidence"):
        return _blocked(contract, signal, "CONTRACT_EVIDENCE_UNSAFE")
    if signal_evidence != signal.get("validated_evidence"):
        return _blocked(contract, signal, "SIGNAL_EVIDENCE_UNSAFE")
    if contract_evidence != signal_evidence:
        return _blocked(contract, signal, "APPROVED_EVIDENCE_MISMATCH")

    return {
        "error": False,
        "eligibility_id": "evidence-eligibility:" + str(signal.get("signal_id")),
        "signal_id": signal.get("signal_id"),
        "approval_id": signal.get("approval_id"),
        "request_id": signal.get("request_id"),
        "draft_id": signal.get("draft_id"),
        "sku": signal.get("sku"),
        "status": "ELIGIBLE_FOR_APPLICATION_REVIEW",
        "application_eligible": True,
        "application_review_required": True,
        "application_allowed": False,
        "application_started": False,
        "approved_evidence": signal_evidence,
        "approved_evidence_count": len(signal_evidence),
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _context_error(contract, signal):
    keys = ("approval_id", "request_id", "draft_id", "sku")
    contract_values = {key: str(contract.get(key) or "").strip() for key in keys}
    signal_values = {key: str(signal.get(key) or "").strip() for key in keys}
    signal_id = str(signal.get("signal_id") or "").strip()

    if not all(contract_values.values()) or not all(signal_values.values()) or not signal_id:
        return "APPLICATION_CONTEXT_REQUIRED"
    for key in keys:
        if contract_values[key] != signal_values[key]:
            return key.upper() + "_MISMATCH"
    if contract_values["approval_id"] != "evidence-approval:" + contract_values["draft_id"]:
        return "APPROVAL_ID_MISMATCH"
    if signal_id != "evidence-signal:" + signal_values["approval_id"]:
        return "SIGNAL_ID_MISMATCH"
    return None


def _safe_evidence(values):
    return {
        field: deepcopy(value)
        for field, value in dict(values or {}).items()
        if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
    }


def _blocked(contract, signal, code):
    return {
        "error": True,
        "code": code,
        "eligibility_id": None,
        "signal_id": signal.get("signal_id"),
        "approval_id": signal.get("approval_id") or contract.get("approval_id"),
        "request_id": signal.get("request_id") or contract.get("request_id"),
        "draft_id": signal.get("draft_id") or contract.get("draft_id"),
        "sku": signal.get("sku") or contract.get("sku"),
        "status": "APPLICATION_INELIGIBLE",
        "application_eligible": False,
        "application_review_required": False,
        "application_allowed": False,
        "application_started": False,
        "approved_evidence": {},
        "approved_evidence_count": 0,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
