from period_profit_mapping_review_queue import (
    assign_review_incident_priority,
    build_review_incident_intake,
    build_review_queue_item,
    build_review_queue_readiness_summary,
    build_review_queue_snapshot,
)


def _audit():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY",
        "scope": "RETURN",
        "revision_id": "r2",
        "mapping_id": "m2",
        "incident_detected": True,
        "incident_categories": ["CATALOG_DRIFT"],
        "human_rereview_required": True,
        "handoff_ready": True,
    }


def _handoff():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY",
        "scope": "RETURN",
        "revision_id": "r2",
        "mapping_id": "m2",
        "incident_categories": ["CATALOG_DRIFT"],
        "human_rereview_required": True,
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }


def test_v166_forged_priority_is_recomputed_and_rejected():
    intake = build_review_incident_intake(_audit(), _handoff())
    priority = assign_review_incident_priority(intake)
    forged = dict(priority, priority="P0", priority_basis=["CATALOG_EVIDENCE_UNAVAILABLE"])
    blocked = build_review_queue_item(intake, forged)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_INCONSISTENT"


def test_v167_forged_queue_item_priority_is_rejected():
    intake = build_review_incident_intake(_audit(), _handoff())
    item = build_review_queue_item(intake, assign_review_incident_priority(intake))
    forged = dict(item, priority="P0", priority_basis=["CATALOG_EVIDENCE_UNAVAILABLE"])
    blocked = build_review_queue_snapshot([forged])
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_PRIORITY_INCONSISTENT"


def test_v164_non_string_lineage_fails_closed():
    audit = _audit()
    handoff = _handoff()
    audit["revision_id"] = 2
    handoff["revision_id"] = 2
    blocked = build_review_incident_intake(audit, handoff)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_LINEAGE_MISMATCH"


def test_v167_unknown_incident_category_fails_closed():
    intake = build_review_incident_intake(_audit(), _handoff())
    item = build_review_queue_item(intake, assign_review_incident_priority(intake))
    forged = dict(item, incident_categories=["SOMETHING_NEW"])
    blocked = build_review_queue_snapshot([forged])
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_INVALID"


def test_v168_tampered_snapshot_counts_fail_closed():
    intake = build_review_incident_intake(_audit(), _handoff())
    item = build_review_queue_item(intake, assign_review_incident_priority(intake))
    snapshot = build_review_queue_snapshot([item])
    forged = dict(snapshot, priority_counts={"P0": 1, "P1": 0, "P2": 0, "P3": 0})
    blocked = build_review_queue_readiness_summary(forged)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_INCONSISTENT"
