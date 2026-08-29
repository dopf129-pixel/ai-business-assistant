ALLOWED_SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}
ALLOWED_INCIDENT_CATEGORIES = {
    "CATALOG_EVIDENCE_UNAVAILABLE",
    "CATALOG_DRIFT",
    "FRESHNESS",
    "REVIEW_REQUIREMENT",
    "REOPENED_OTHER_EXPLICIT_REASON",
}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def build_review_incident_intake(audit_receipt, incident_handoff):
    """v164: bind a validated incident audit to its human-only handoff."""
    audit = _dict(audit_receipt)
    handoff = _dict(incident_handoff)
    if (
        audit.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY"
        or audit.get("error") is not False
        or audit.get("incident_detected") is not True
        or audit.get("human_rereview_required") is not True
        or audit.get("handoff_ready") is not True
        or handoff.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY"
        or handoff.get("error") is not False
        or handoff.get("human_rereview_required") is not True
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INCIDENT_AUDIT_REQUIRED")
    lineage = _lineage(audit)
    if not _valid_lineage(lineage) or lineage != _lineage(handoff):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_LINEAGE_MISMATCH")
    categories = _categories(audit.get("incident_categories"))
    handoff_categories = _categories(handoff.get("incident_categories"))
    if categories is None or handoff_categories is None or categories != handoff_categories or not categories:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INCIDENT_CATEGORIES_INVALID")
    if not _permissions_disabled(handoff):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_MUTATION_PERMISSION_INVALID")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INTAKE_READY",
        "scope": lineage[0],
        "revision_id": lineage[1],
        "mapping_id": lineage[2],
        "incident_categories": categories,
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


def assign_review_incident_priority(intake):
    """v165: assign deterministic operational priority from validated explicit categories only."""
    source = _dict(intake)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INTAKE_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INTAKE_REQUIRED")
    categories = _categories(source.get("incident_categories"))
    if categories is None or not categories or not _valid_lineage(_lineage(source)):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INCIDENT_CATEGORIES_INVALID")
    priority, basis = _expected_priority(categories)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_READY",
        "scope": source.get("scope"),
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "incident_categories": categories,
        "priority": priority,
        "priority_basis": basis,
        "human_rereview_required": True,
        "automatic_priority_only": True,
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


def build_review_queue_item(intake, priority):
    """v166: produce a canonical immutable queue item for human review."""
    source = _dict(intake)
    ranked = _dict(priority)
    categories = _categories(source.get("incident_categories"))
    ranked_categories = _categories(ranked.get("incident_categories"))
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INTAKE_READY"
        or ranked.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_READY"
        or source.get("error") is not False
        or ranked.get("error") is not False
        or not _valid_lineage(_lineage(source))
        or _lineage(source) != _lineage(ranked)
        or categories is None
        or categories != ranked_categories
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_INPUT_REQUIRED")
    expected_priority, expected_basis = _expected_priority(categories)
    if ranked.get("priority") != expected_priority or ranked.get("priority_basis") != expected_basis:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_INCONSISTENT")
    lineage = _lineage(source)
    queue_key = "|".join(lineage)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_READY",
        "queue_key": queue_key,
        "scope": lineage[0],
        "revision_id": lineage[1],
        "mapping_id": lineage[2],
        "incident_categories": categories,
        "priority": expected_priority,
        "priority_basis": expected_basis,
        "human_rereview_required": True,
        "review_state": "PENDING_HUMAN_REREVIEW",
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


def build_review_queue_snapshot(items):
    """v167: aggregate canonical queue items without persisting or mutating them."""
    if not isinstance(items, (list, tuple)):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEMS_REQUIRED")
    normalized = []
    seen = set()
    for raw in items:
        item = _dict(raw)
        categories = _categories(item.get("incident_categories"))
        if (
            item.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_READY"
            or item.get("error") is not False
            or item.get("review_state") != "PENDING_HUMAN_REREVIEW"
            or item.get("priority") not in PRIORITY_ORDER
            or item.get("human_rereview_required") is not True
            or categories is None
            or not _permissions_disabled(item)
        ):
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_INVALID")
        expected_priority, expected_basis = _expected_priority(categories)
        if item.get("priority") != expected_priority or item.get("priority_basis") != expected_basis:
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_INCONSISTENT")
        lineage = _lineage(item)
        if not _valid_lineage(lineage):
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_LINEAGE_INVALID")
        key = item.get("queue_key")
        expected_key = "|".join(lineage)
        if key != expected_key or key in seen:
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_DUPLICATE_OR_KEY_INVALID")
        seen.add(key)
        normalized.append({
            "queue_key": key,
            "scope": lineage[0],
            "revision_id": lineage[1],
            "mapping_id": lineage[2],
            "incident_categories": categories,
            "priority": expected_priority,
            "review_state": item.get("review_state"),
        })
    normalized.sort(key=lambda row: (PRIORITY_ORDER[row["priority"]], row["scope"], row["revision_id"], row["mapping_id"]))
    counts = {priority: 0 for priority in PRIORITY_ORDER}
    for row in normalized:
        counts[row["priority"]] += 1
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_READY",
        "items": normalized,
        "item_count": len(normalized),
        "priority_counts": counts,
        "human_rereview_required_count": len(normalized),
        "registry_write_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_review_queue_readiness_summary(snapshot):
    """v168: expose deterministic operational readiness without resolving any review."""
    source = _dict(snapshot)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_REQUIRED")
    items = source.get("items")
    counts = source.get("priority_counts")
    if not isinstance(items, list) or not isinstance(counts, dict):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_SCHEMA_INVALID")
    expected_counts = {priority: 0 for priority in PRIORITY_ORDER}
    seen = set()
    for row in items:
        if not isinstance(row, dict):
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_SCHEMA_INVALID")
        categories = _categories(row.get("incident_categories"))
        lineage = _lineage(row)
        if categories is None or not _valid_lineage(lineage):
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_SCHEMA_INVALID")
        expected_priority, _ = _expected_priority(categories)
        expected_key = "|".join(lineage)
        if row.get("priority") != expected_priority or row.get("queue_key") != expected_key or expected_key in seen:
            return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_INCONSISTENT")
        seen.add(expected_key)
        expected_counts[expected_priority] += 1
    if counts != expected_counts or source.get("item_count") != len(items) or source.get("human_rereview_required_count") != len(items):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_INCONSISTENT")
    highest_priority = next((priority for priority in PRIORITY_ORDER if expected_counts[priority] > 0), None)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_READINESS_READY",
        "queue_empty": len(items) == 0,
        "pending_human_rereview_count": len(items),
        "highest_pending_priority": highest_priority,
        "priority_counts": expected_counts,
        "operationally_clear": len(items) == 0,
        "human_action_required": len(items) > 0,
        "review_resolution_allowed": False,
        "registry_write_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def _expected_priority(categories):
    if "CATALOG_EVIDENCE_UNAVAILABLE" in categories:
        return "P0", ["CATALOG_EVIDENCE_UNAVAILABLE"]
    if "CATALOG_DRIFT" in categories:
        return "P1", ["CATALOG_DRIFT"]
    if "FRESHNESS" in categories:
        return "P2", ["FRESHNESS"]
    return "P3", list(categories)


def _categories(value):
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item in ALLOWED_INCIDENT_CATEGORIES for item in value):
        return None
    return sorted(set(value))


def _lineage(value):
    source = _dict(value)
    return (source.get("scope"), source.get("revision_id"), source.get("mapping_id"))


def _valid_lineage(lineage):
    return (
        isinstance(lineage[0], str)
        and lineage[0] in ALLOWED_SCOPES
        and isinstance(lineage[1], str)
        and bool(lineage[1].strip())
        and isinstance(lineage[2], str)
        and bool(lineage[2].strip())
    )


def _permissions_disabled(source):
    return (
        source.get("mapping_build_allowed") is False
        and source.get("registry_save_allowed") is False
        and source.get("activation_allowed") is False
        and source.get("automatic_remap_allowed") is False
        and source.get("automatic_activation_allowed") is False
        and source.get("profit_adjustment_allowed") is False
        and source.get("ozon_mutation") is False
        and source.get("executed") is False
    )


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_UNAVAILABLE",
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "registry_write_allowed": False,
        "review_resolution_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
