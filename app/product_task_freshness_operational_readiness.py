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
