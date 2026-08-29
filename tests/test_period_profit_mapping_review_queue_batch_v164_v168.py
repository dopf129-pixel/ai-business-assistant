from period_profit_mapping_review_queue import (
    assign_review_incident_priority,
    build_review_incident_intake,
    build_review_queue_item,
    build_review_queue_readiness_summary,
    build_review_queue_snapshot,
)


def _audit(**overrides):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY",
        "scope": "RETURN",
        "revision_id": "return-r2",
        "mapping_id": "return-map:abc",
        "incident_detected": True,
        "incident_categories": ["CATALOG_DRIFT"],
        "human_rereview_required": True,
        "handoff_ready": True,
    }
    result.update(overrides)
    return result


def _handoff(**overrides):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY",
        "scope": "RETURN",
        "revision_id": "return-r2",
        "mapping_id": "return-map:abc",
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
    result.update(overrides)
    return result


def _queue_item(scope="RETURN", revision="r2", mapping="map:2", priority="P1"):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_ITEM_READY",
        "queue_key": f"{scope}|{revision}|{mapping}",
        "scope": scope,
        "revision_id": revision,
        "mapping_id": mapping,
        "incident_categories": ["CATALOG_DRIFT"],
        "priority": priority,
        "priority_basis": ["CATALOG_DRIFT"],
        "human_rereview_required": True,
        "review_state": "PENDING_HUMAN_REREVIEW",
        "mapping_build_allowed": False,
        "registry_save_allowed": False,
        "activation_allowed": False,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }


def test_v164_intake_requires_exact_audit_handoff_lineage_and_categories():
    intake = build_review_incident_intake(_audit(), _handoff())
    assert intake["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INTAKE_READY"
    assert intake["incident_categories"] == ["CATALOG_DRIFT"]
    mismatch = build_review_incident_intake(_audit(), _handoff(mapping_id="return-map:other"))
    assert mismatch["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_LINEAGE_MISMATCH"
    category_mismatch = build_review_incident_intake(_audit(), _handoff(incident_categories=["FRESHNESS"]))
    assert category_mismatch["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_INCIDENT_CATEGORIES_INVALID"


def test_v164_intake_rejects_any_mutation_permission():
    blocked = build_review_incident_intake(_audit(), _handoff(registry_save_allowed=True))
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_MUTATION_PERMISSION_INVALID"
    assert blocked["registry_save_allowed"] is False


def test_v165_priority_is_deterministic_from_explicit_categories_only():
    intake = build_review_incident_intake(
        _audit(incident_categories=["FRESHNESS", "CATALOG_DRIFT"]),
        _handoff(incident_categories=["CATALOG_DRIFT", "FRESHNESS"]),
    )
    priority = assign_review_incident_priority(intake)
    assert priority["priority"] == "P1"
    assert priority["priority_basis"] == ["CATALOG_DRIFT"]

    unavailable = build_review_incident_intake(
        _audit(incident_categories=["CATALOG_EVIDENCE_UNAVAILABLE", "CATALOG_DRIFT"]),
        _handoff(incident_categories=["CATALOG_DRIFT", "CATALOG_EVIDENCE_UNAVAILABLE"]),
    )
    assert assign_review_incident_priority(unavailable)["priority"] == "P0"


def test_v166_queue_item_has_stable_exact_lineage_key_and_no_permissions():
    intake = build_review_incident_intake(_audit(), _handoff())
    priority = assign_review_incident_priority(intake)
    item = build_review_queue_item(intake, priority)
    assert item["queue_key"] == "RETURN|return-r2|return-map:abc"
    assert item["review_state"] == "PENDING_HUMAN_REREVIEW"
    assert item["mapping_build_allowed"] is False
    assert item["activation_allowed"] is False


def test_v167_snapshot_orders_by_priority_then_exact_lineage():
    snapshot = build_review_queue_snapshot([
        _queue_item(scope="STORAGE", revision="s2", mapping="sm2", priority="P2"),
        _queue_item(scope="RETURN", revision="r2", mapping="rm2", priority="P0"),
        _queue_item(scope="ADVERTISING", revision="a2", mapping="am2", priority="P1"),
    ])
    assert snapshot["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_SNAPSHOT_READY"
    assert [row["priority"] for row in snapshot["items"]] == ["P0", "P1", "P2"]
    assert snapshot["priority_counts"] == {"P0": 1, "P1": 1, "P2": 1, "P3": 0}


def test_v167_snapshot_rejects_duplicate_lineage_key():
    item = _queue_item()
    blocked = build_review_queue_snapshot([item, dict(item)])
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_DUPLICATE_OR_KEY_INVALID"


def test_v168_readiness_is_descriptive_only():
    snapshot = build_review_queue_snapshot([
        _queue_item(scope="RETURN", revision="r2", mapping="rm2", priority="P1"),
        _queue_item(scope="STORAGE", revision="s2", mapping="sm2", priority="P3"),
    ])
    summary = build_review_queue_readiness_summary(snapshot)
    assert summary["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_QUEUE_READINESS_READY"
    assert summary["queue_empty"] is False
    assert summary["pending_human_rereview_count"] == 2
    assert summary["highest_pending_priority"] == "P1"
    assert summary["human_action_required"] is True
    assert summary["review_resolution_allowed"] is False
    assert summary["registry_write_allowed"] is False


def test_v168_empty_queue_is_operationally_clear_without_executing_anything():
    snapshot = build_review_queue_snapshot([])
    summary = build_review_queue_readiness_summary(snapshot)
    assert summary["queue_empty"] is True
    assert summary["operationally_clear"] is True
    assert summary["human_action_required"] is False
    assert summary["executed"] is False
