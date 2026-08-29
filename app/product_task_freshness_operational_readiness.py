from copy import deepcopy

SAFETY_FIELDS = (
    "application_allowed", "application_started", "persistent",
    "product_decision_recomputed", "product_decision_mutated",
    "task_draft_mutated", "execution_allowed", "execution_ready", "executed",
)

STAGES = (
    ("PREPARATION", "preparation_audit", "APPLICATION_PREPARATION_AUDIT_READY"),
    ("EXECUTOR_ADMISSION", "executor_admission_audit", "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY"),
    ("WRITE_PROTOCOL", "write_protocol_audit", "APPLICATION_WRITE_PROTOCOL_AUDIT_READY"),
    ("ADAPTER_BOUNDARY", "adapter_boundary_audit", "WRITE_ADAPTER_BOUNDARY_AUDIT_READY"),
)


def build_freshness_operational_projection(snapshot):
    source = deepcopy(snapshot or {})
    stages = []
    blockers = []
    highest_complete = None

    for stage_name, field, expected_status in STAGES:
        artifact = source.get(field)
        state = _artifact_state(artifact, expected_status)
        stages.append({"stage": stage_name, "state": state})
        if state == "COMPLETE":
            highest_complete = stage_name
        elif state != "MISSING":
            blockers.append(_blocker(stage_name, state))

    blockers.extend(_lineage_blockers(source, stages))

    if highest_complete is None and not blockers:
        blockers.append("FRESHNESS_LIFECYCLE_EVIDENCE_MISSING")

    next_action = _next_action(stages, blockers)
    operationally_ready = highest_complete == "ADAPTER_BOUNDARY" and not blockers

    return {
        "error": False,
        "status": "FRESHNESS_OPERATIONAL_READINESS",
        "highest_complete_stage": highest_complete,
        "stages": stages,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "next_action": next_action,
        "operationally_ready": operationally_ready,
        "mutation_ready": False,
        "business_execution_ready": False,
        "human_action_required": not operationally_ready,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }


def build_freshness_readiness_summary(projection):
    source = deepcopy(projection or {})
    if source.get("status") != "FRESHNESS_OPERATIONAL_READINESS" or source.get("error") is not False:
        return _blocked("FRESHNESS_OPERATIONAL_PROJECTION_REQUIRED")
    if source.get("mutation_ready") is not False or source.get("business_execution_ready") is not False:
        return _blocked("FRESHNESS_OPERATIONAL_SAFETY_BOUNDARY_VIOLATION")
    blockers = source.get("blockers")
    if not isinstance(blockers, list) or source.get("blocker_count") != len(blockers):
        return _blocked("FRESHNESS_OPERATIONAL_BLOCKER_COUNT_MISMATCH")
    expected_ready = source.get("highest_complete_stage") == "ADAPTER_BOUNDARY" and not blockers
    if source.get("operationally_ready") is not expected_ready:
        return _blocked("FRESHNESS_OPERATIONAL_READY_CONTRADICTORY")
    return {
        "error": False,
        "status": "FRESHNESS_OPERATIONAL_READINESS_SUMMARY",
        "highest_complete_stage": source.get("highest_complete_stage"),
        "blockers": list(blockers),
        "blocker_count": len(blockers),
        "next_action": source.get("next_action"),
        "operationally_ready": expected_ready,
        "mutation_ready": False,
        "business_execution_ready": False,
        "human_action_required": not expected_ready,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }


def _artifact_state(artifact, expected_status):
    if artifact is None:
        return "MISSING"
    if not isinstance(artifact, dict):
        return "MALFORMED"
    if artifact.get("error") is not False:
        return "ERROR"
    if artifact.get("status") != expected_status:
        return "STATUS_MISMATCH"
    if any(artifact.get(field) is not False for field in SAFETY_FIELDS):
        return "SAFETY_VIOLATION"
    if artifact.get("source_freshness_proven") is not False:
        return "SAFETY_VIOLATION"
    return "COMPLETE"


def _lineage_blockers(source, stages):
    states = {item["stage"]: item["state"] for item in stages}
    blockers = []
    prep = source.get("preparation_audit") or {}
    executor = source.get("executor_admission_audit") or {}
    write = source.get("write_protocol_audit") or {}
    adapter = source.get("adapter_boundary_audit") or {}

    if states.get("PREPARATION") == states.get("EXECUTOR_ADMISSION") == "COMPLETE":
        if not _nonempty_equal(prep, executor, "preparation_decision_id"):
            blockers.append("PREPARATION_EXECUTOR_LINEAGE_MISMATCH")
        expected_prep_audit = "evidence-application-preparation-audit:" + str(prep.get("preparation_decision_id") or "")
        if prep.get("preparation_audit_id") != expected_prep_audit or executor.get("preparation_audit_id") != expected_prep_audit:
            blockers.append("PREPARATION_AUDIT_LINEAGE_MISMATCH")

    if states.get("EXECUTOR_ADMISSION") == states.get("WRITE_PROTOCOL") == "COMPLETE":
        auth = executor.get("executor_authorization_id")
        expected_executor_audit = "evidence-application-executor-admission-audit:" + str(auth or "")
        if not isinstance(auth, str) or not auth or executor.get("executor_admission_audit_id") != expected_executor_audit:
            blockers.append("EXECUTOR_AUDIT_LINEAGE_MISMATCH")
        if write.get("executor_authorization_id") != auth or write.get("executor_admission_audit_id") != expected_executor_audit:
            blockers.append("EXECUTOR_WRITE_LINEAGE_MISMATCH")
        if executor.get("target_revision_id") != write.get("expected_target_revision_id") or executor.get("target_version") != write.get("expected_target_version"):
            blockers.append("EXECUTOR_WRITE_TARGET_MISMATCH")

    if states.get("WRITE_PROTOCOL") == states.get("ADAPTER_BOUNDARY") == "COMPLETE":
        if not _nonempty_equal(write, adapter, "executor_authorization_id"):
            blockers.append("WRITE_ADAPTER_LINEAGE_MISMATCH")
        if adapter.get("write_protocol_audit_id") != write.get("write_protocol_audit_id"):
            blockers.append("WRITE_ADAPTER_AUDIT_LINEAGE_MISMATCH")
        if write.get("expected_target_revision_id") != adapter.get("expected_target_revision_id") or write.get("expected_target_version") != adapter.get("expected_target_version"):
            blockers.append("WRITE_ADAPTER_TARGET_MISMATCH")

    return blockers


def _nonempty_equal(left, right, field):
    value = left.get(field)
    return isinstance(value, str) and bool(value) and right.get(field) == value


def _blocker(stage, state):
    return "{}_{}".format(stage, state)


def _next_action(stages, blockers):
    if blockers:
        return "REVIEW_BLOCKERS"
    for item in stages:
        if item["state"] == "MISSING":
            return "CONTINUE_{}".format(item["stage"])
    return "AWAIT_REAL_WRITE_ADAPTER"


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "FRESHNESS_OPERATIONAL_READINESS_BLOCKED",
        "operationally_ready": False,
        "mutation_ready": False,
        "business_execution_ready": False,
        "human_action_required": True,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }
