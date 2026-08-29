def build_monitoring_observation(checkpoint, refresh, evaluation):
    """v159: freeze one deterministic read-only monitoring observation."""
    base = _dict(checkpoint)
    current = _dict(refresh)
    result = _dict(evaluation)
    if (
        base.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_READY"
        or base.get("error") is not False
        or current.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESHED"
        or current.get("error") is not False
        or result.get("status") not in {"PERIOD_PROFIT_MAPPING_REVIEW_STILL_CLOSED", "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED"}
        or result.get("error") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_INPUT_REQUIRED")
    lineage = _lineage(base)
    if lineage != _lineage(current) or lineage != _lineage(result):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_LINEAGE_MISMATCH")
    if (
        not isinstance(current.get("catalog_available"), bool)
        or not isinstance(current.get("catalog_drift_detected"), bool)
        or not isinstance(current.get("review_required"), bool)
        or not isinstance(result.get("review_reopened"), bool)
        or not isinstance(result.get("reopen_reasons"), list)
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_SCHEMA_INVALID")
    missing = _normalized_missing(current.get("missing_type_ids"))
    renamed = _normalized_renamed(current.get("renamed_operations"))
    if missing is None or renamed is None:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_SCHEMA_INVALID")
    expected_reasons = _expected_reopen_reasons(current, missing, renamed)
    reasons = list(result.get("reopen_reasons"))
    reopened = result.get("review_reopened")
    if (
        reasons != expected_reasons
        or reopened != bool(expected_reasons)
        or reopened != (result.get("status") == "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_STATE_INVALID")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_READY",
        "scope": lineage[0],
        "revision_id": lineage[1],
        "mapping_id": lineage[2],
        "catalog_available": current.get("catalog_available"),
        "freshness_status": current.get("freshness_status"),
        "missing_type_ids": missing,
        "renamed_operations": renamed,
        "catalog_drift_detected": current.get("catalog_drift_detected"),
        "review_required": current.get("review_required"),
        "quality_score": current.get("quality_score"),
        "review_reopened": reopened,
        "reopen_reasons": reasons,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_monitoring_observation_delta(previous_observation, current_observation):
    """v160: compare two observations without inferring operation semantics."""
    previous = _dict(previous_observation)
    current = _dict(current_observation)
    required = "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_READY"
    if previous.get("status") != required or current.get("status") != required or previous.get("error") is not False or current.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATIONS_REQUIRED")
    if _lineage(previous) != _lineage(current):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_DELTA_LINEAGE_MISMATCH")
    fields = (
        "catalog_available", "freshness_status", "missing_type_ids", "renamed_operations",
        "catalog_drift_detected", "review_required", "quality_score", "review_reopened", "reopen_reasons",
    )
    changes = [
        {"field": field, "before": previous.get(field), "after": current.get(field)}
        for field in fields if previous.get(field) != current.get(field)
    ]
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_DELTA_READY",
        "scope": current.get("scope"),
        "revision_id": current.get("revision_id"),
        "mapping_id": current.get("mapping_id"),
        "changes": changes,
        "change_count": len(changes),
        "state_changed": previous.get("review_reopened") != current.get("review_reopened"),
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def classify_review_monitoring_incident(delta, current_observation):
    """v161: classify only explicit monitoring evidence; no semantic guessing."""
    change = _dict(delta)
    current = _dict(current_observation)
    if (
        change.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_DELTA_READY"
        or change.get("error") is not False
        or current.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_READY"
        or current.get("error") is not False
        or _lineage(change) != _lineage(current)
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_INPUT_REQUIRED")
    categories = []
    reasons = set(current.get("reopen_reasons") or [])
    if "CATALOG_UNAVAILABLE" in reasons:
        categories.append("CATALOG_EVIDENCE_UNAVAILABLE")
    if reasons.intersection({"MISSING_TYPE_IDS", "RENAMED_OPERATIONS", "CATALOG_DRIFT"}):
        categories.append("CATALOG_DRIFT")
    if "FRESHNESS_NOT_FRESH" in reasons:
        categories.append("FRESHNESS")
    if reasons.intersection({"REVIEW_REQUIRED", "REVIEW_STILL_REQUIRED"}):
        categories.append("REVIEW_REQUIREMENT")
    incident = current.get("review_reopened") is True
    if incident and not categories:
        categories.append("REOPENED_OTHER_EXPLICIT_REASON")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_READY",
        "scope": current.get("scope"),
        "revision_id": current.get("revision_id"),
        "mapping_id": current.get("mapping_id"),
        "incident_detected": incident,
        "incident_categories": categories,
        "reopen_reasons": list(current.get("reopen_reasons") or []),
        "change_count": change.get("change_count"),
        "human_rereview_required": incident,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_review_monitoring_incident_handoff(incident, evaluation):
    """v162: produce a human-only escalation handoff for a reopened review."""
    source = _dict(incident)
    result = _dict(evaluation)
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_READY"
        or source.get("error") is not False
        or source.get("incident_detected") is not True
        or source.get("human_rereview_required") is not True
        or result.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED"
        or result.get("error") is not False
        or result.get("review_reopened") is not True
        or source.get("reopen_reasons") != result.get("reopen_reasons")
        or _lineage(source) != _lineage(result)
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_REQUIRED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY",
        "scope": source.get("scope"),
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "incident_categories": list(source.get("incident_categories") or []),
        "reopen_reasons": list(source.get("reopen_reasons") or []),
        "human_rereview_required": True,
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_review_monitoring_audit_receipt(observation, delta, incident, handoff=None):
    """v163: aggregate deterministic read-only evidence for monitoring audit."""
    current = _dict(observation)
    change = _dict(delta)
    source = _dict(incident)
    if (
        current.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_READY"
        or change.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_DELTA_READY"
        or source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_READY"
        or current.get("error") is not False or change.get("error") is not False or source.get("error") is not False
        or _lineage(current) != _lineage(change) or _lineage(current) != _lineage(source)
        or source.get("reopen_reasons") != current.get("reopen_reasons")
        or source.get("incident_detected") != current.get("review_reopened")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_INPUT_REQUIRED")
    handoff_source = _dict(handoff)
    if source.get("incident_detected") is True:
        if (
            handoff_source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY"
            or handoff_source.get("error") is not False
            or _lineage(current) != _lineage(handoff_source)
            or handoff_source.get("reopen_reasons") != current.get("reopen_reasons")
        ):
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_HANDOFF_REQUIRED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY",
        "scope": current.get("scope"),
        "revision_id": current.get("revision_id"),
        "mapping_id": current.get("mapping_id"),
        "incident_detected": source.get("incident_detected") is True,
        "incident_categories": list(source.get("incident_categories") or []),
        "change_count": change.get("change_count"),
        "review_reopened": current.get("review_reopened") is True,
        "human_rereview_required": source.get("human_rereview_required") is True,
        "handoff_ready": handoff_source.get("status") == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY",
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def _expected_reopen_reasons(current, missing, renamed):
    reasons = []
    if current.get("catalog_available") is not True:
        reasons.append("CATALOG_UNAVAILABLE")
    if missing:
        reasons.append("MISSING_TYPE_IDS")
    if renamed:
        reasons.append("RENAMED_OPERATIONS")
    if current.get("catalog_drift_detected") is True and not (missing or renamed):
        reasons.append("CATALOG_DRIFT")
    if current.get("freshness_status") != "FRESH":
        reasons.append("FRESHNESS_NOT_FRESH")
    if current.get("review_required") is True and not reasons:
        reasons.append("REVIEW_REQUIRED")
    return reasons


def _normalized_missing(values):
    if not isinstance(values, list):
        return None
    normalized = []
    try:
        for value in values:
            normalized.append(int(value))
    except (TypeError, ValueError):
        return None
    return sorted(normalized)


def _normalized_renamed(rows):
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    normalized = []
    for row in rows:
        if row.get("type_id") is None:
            return None
        try:
            item = dict(row)
            item["type_id"] = int(item.get("type_id"))
        except (TypeError, ValueError):
            return None
        normalized.append(item)
    return sorted(normalized, key=lambda row: (row.get("type_id"), str(row.get("mapped_name")), str(row.get("current_name"))))


def _lineage(value):
    source = _dict(value)
    return (source.get("scope"), source.get("revision_id"), source.get("mapping_id"))


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_UNAVAILABLE",
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
