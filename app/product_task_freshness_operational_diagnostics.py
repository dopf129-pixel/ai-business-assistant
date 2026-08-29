from copy import deepcopy


ARTIFACTS = (
    ("preparation_audit", "get_preparation_audit"),
    ("executor_admission_audit", "get_executor_admission_audit"),
    ("write_protocol_audit", "get_write_protocol_audit"),
    ("adapter_boundary_audit", "get_adapter_boundary_audit"),
)

SAFETY_FIELDS = (
    "application_allowed",
    "application_started",
    "persistent",
    "product_decision_recomputed",
    "product_decision_mutated",
    "task_draft_mutated",
    "execution_allowed",
    "execution_ready",
    "executed",
)


def inspect_freshness_reader_capabilities(reader):
    capabilities = []
    for field, method_name in ARTIFACTS:
        method = getattr(reader, method_name, None) if reader is not None else None
        capabilities.append({
            "artifact": field,
            "method": method_name,
            "available": callable(method),
        })
    missing = [item["method"] for item in capabilities if not item["available"]]
    return {
        "error": False,
        "status": "FRESHNESS_READER_CAPABILITIES",
        "capabilities": capabilities,
        "capability_count": len(capabilities),
        "missing_capabilities": missing,
        "missing_capability_count": len(missing),
        "reader_complete": not missing,
        "read_only": True,
        "persistent": False,
        "executed": False,
    }


def collect_freshness_snapshot_diagnostics(reader):
    capability = inspect_freshness_reader_capabilities(reader)
    artifacts = []
    snapshot = {}

    for field, method_name in ARTIFACTS:
        method = getattr(reader, method_name, None) if reader is not None else None
        if not callable(method):
            artifacts.append(_artifact_result(field, method_name, "CAPABILITY_MISSING"))
            snapshot[field] = None
            continue
        try:
            value = method()
        except Exception:
            artifacts.append(_artifact_result(field, method_name, "READ_ERROR"))
            snapshot[field] = None
            continue
        if value is None:
            artifacts.append(_artifact_result(field, method_name, "MISSING"))
            snapshot[field] = None
            continue
        if not isinstance(value, dict):
            artifacts.append(_artifact_result(field, method_name, "MALFORMED"))
            snapshot[field] = None
            continue
        if _unsafe(value):
            artifacts.append(_artifact_result(field, method_name, "SAFETY_VIOLATION"))
            snapshot[field] = deepcopy(value)
            continue
        artifacts.append(_artifact_result(field, method_name, "AVAILABLE"))
        snapshot[field] = deepcopy(value)

    blockers = [
        "{}:{}".format(item["artifact"], item["state"])
        for item in artifacts
        if item["state"] not in {"AVAILABLE", "MISSING"}
    ]
    available_count = sum(item["state"] == "AVAILABLE" for item in artifacts)
    missing_count = sum(item["state"] == "MISSING" for item in artifacts)

    return {
        "error": False,
        "status": "FRESHNESS_SNAPSHOT_DIAGNOSTICS",
        "reader_complete": capability["reader_complete"],
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "available_count": available_count,
        "missing_count": missing_count,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "snapshot": snapshot,
        "snapshot_usable": not blockers,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }


def build_freshness_runtime_activation_readiness(diagnostics):
    source = deepcopy(diagnostics or {})
    if source.get("error") is not False or source.get("status") != "FRESHNESS_SNAPSHOT_DIAGNOSTICS":
        return _blocked("FRESHNESS_DIAGNOSTICS_REQUIRED")
    artifacts = source.get("artifacts")
    if not isinstance(artifacts, list) or source.get("artifact_count") != len(ARTIFACTS):
        return _blocked("FRESHNESS_DIAGNOSTICS_ARTIFACT_COUNT_MISMATCH")
    if source.get("blocker_count") != len(source.get("blockers") or []):
        return _blocked("FRESHNESS_DIAGNOSTICS_BLOCKER_COUNT_MISMATCH")

    active_states = [item.get("state") for item in artifacts]
    activation_ready = source.get("reader_complete") is True and all(
        state in {"AVAILABLE", "MISSING"} for state in active_states
    )
    return {
        "error": False,
        "status": "FRESHNESS_RUNTIME_ACTIVATION_READINESS",
        "activation_ready": activation_ready,
        "reader_complete": source.get("reader_complete") is True,
        "available_count": source.get("available_count"),
        "missing_count": source.get("missing_count"),
        "blockers": list(source.get("blockers") or []),
        "blocker_count": source.get("blocker_count"),
        "lifecycle_ready": False,
        "mutation_ready": False,
        "business_execution_ready": False,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }


def build_freshness_diagnostics_audit(diagnostics, activation):
    source = deepcopy(diagnostics or {})
    ready = deepcopy(activation or {})
    if source.get("status") != "FRESHNESS_SNAPSHOT_DIAGNOSTICS" or source.get("error") is not False:
        return _blocked("FRESHNESS_DIAGNOSTICS_AUDIT_INPUT_INVALID")
    if ready.get("status") != "FRESHNESS_RUNTIME_ACTIVATION_READINESS" or ready.get("error") is not False:
        return _blocked("FRESHNESS_DIAGNOSTICS_AUDIT_ACTIVATION_INVALID")
    expected = build_freshness_runtime_activation_readiness(source)
    for field in (
        "activation_ready", "reader_complete", "available_count", "missing_count",
        "blockers", "blocker_count",
    ):
        if ready.get(field) != expected.get(field):
            return _blocked("FRESHNESS_DIAGNOSTICS_AUDIT_CONTRADICTION")
    if any(ready.get(field) is not False for field in (
        "lifecycle_ready", "mutation_ready", "business_execution_ready",
        "application_allowed", "persistent", "task_draft_mutated",
        "execution_allowed", "executed",
    )):
        return _blocked("FRESHNESS_DIAGNOSTICS_AUDIT_SAFETY_VIOLATION")
    return {
        "error": False,
        "status": "FRESHNESS_DIAGNOSTICS_AUDIT_READY",
        "activation_ready": ready["activation_ready"],
        "reader_complete": ready["reader_complete"],
        "blockers": list(ready["blockers"]),
        "blocker_count": ready["blocker_count"],
        "read_only": True,
        "lifecycle_ready": False,
        "mutation_ready": False,
        "business_execution_ready": False,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }


def _artifact_result(field, method, state):
    return {"artifact": field, "method": method, "state": state}


def _unsafe(source):
    return any(source.get(field) is not False for field in SAFETY_FIELDS) or source.get("source_freshness_proven") is not False


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "FRESHNESS_DIAGNOSTICS_BLOCKED",
        "activation_ready": False,
        "lifecycle_ready": False,
        "mutation_ready": False,
        "business_execution_ready": False,
        "read_only": True,
        "application_allowed": False,
        "persistent": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "executed": False,
    }
