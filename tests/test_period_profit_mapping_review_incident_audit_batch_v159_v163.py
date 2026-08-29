from period_profit_mapping_review_incident_audit import (
    build_monitoring_observation,
    build_monitoring_observation_delta,
    build_review_monitoring_audit_receipt,
    build_review_monitoring_incident_handoff,
    classify_review_monitoring_incident,
)


def _checkpoint():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_READY",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
    }


def _refresh(**overrides):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESHED",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "catalog_available": True,
        "freshness_status": "FRESH",
        "missing_type_ids": [],
        "renamed_operations": [],
        "catalog_drift_detected": False,
        "review_required": False,
        "quality_score": 100,
    }
    result.update(overrides)
    return result


def _evaluation(reopened=False, reasons=None):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED" if reopened else "PERIOD_PROFIT_MAPPING_REVIEW_STILL_CLOSED",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "review_reopened": reopened,
        "reopen_reasons": list(reasons or []),
        "human_rereview_required": reopened,
    }


def _observation(refresh=None, evaluation=None):
    return build_monitoring_observation(_checkpoint(), refresh or _refresh(), evaluation or _evaluation())


def test_v159_observation_binds_exact_lineage_and_normalizes_evidence():
    result = _observation(
        _refresh(
            renamed_operations=[
                {"type_id": 2, "mapped_name": "B", "current_name": "B2"},
                {"type_id": 1, "mapped_name": "A", "current_name": "A2"},
            ]
        ),
        _evaluation(True, ["RENAMED_OPERATIONS"]),
    )
    assert result["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_READY"
    assert [row["type_id"] for row in result["renamed_operations"]] == [1, 2]
    assert result["automatic_remap_allowed"] is False

    bad = dict(_evaluation(), mapping_id="other")
    blocked = build_monitoring_observation(_checkpoint(), _refresh(), bad)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_LINEAGE_MISMATCH"


def test_v160_delta_reports_only_changed_evidence_fields():
    previous = _observation()
    current = _observation(
        _refresh(catalog_available=False, review_required=True),
        _evaluation(True, ["CATALOG_UNAVAILABLE"]),
    )
    result = build_monitoring_observation_delta(previous, current)
    assert result["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_DELTA_READY"
    assert result["change_count"] > 0
    assert result["state_changed"] is True
    fields = {row["field"] for row in result["changes"]}
    assert "catalog_available" in fields
    assert "review_reopened" in fields


def test_v161_incident_classification_uses_only_explicit_reopen_reasons():
    previous = _observation()
    current = _observation(
        _refresh(missing_type_ids=[7], catalog_drift_detected=True, review_required=True),
        _evaluation(True, ["MISSING_TYPE_IDS"]),
    )
    delta = build_monitoring_observation_delta(previous, current)
    incident = classify_review_monitoring_incident(delta, current)
    assert incident["incident_detected"] is True
    assert incident["incident_categories"] == ["CATALOG_DRIFT"]
    assert incident["human_rereview_required"] is True


def test_v161_clean_observation_has_no_incident():
    current = _observation()
    delta = build_monitoring_observation_delta(current, current)
    incident = classify_review_monitoring_incident(delta, current)
    assert incident["incident_detected"] is False
    assert incident["incident_categories"] == []
    assert incident["human_rereview_required"] is False


def test_v162_handoff_requires_reopened_incident_and_grants_no_write_permission():
    previous = _observation()
    current = _observation(
        _refresh(freshness_status="STALE", review_required=True),
        _evaluation(True, ["FRESHNESS_NOT_FRESH"]),
    )
    delta = build_monitoring_observation_delta(previous, current)
    incident = classify_review_monitoring_incident(delta, current)
    handoff = build_review_monitoring_incident_handoff(incident, _evaluation(True, ["FRESHNESS_NOT_FRESH"]))
    assert handoff["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_INCIDENT_HANDOFF_READY"
    assert handoff["mapping_build_allowed"] is False
    assert handoff["registry_save_allowed"] is False
    assert handoff["activation_allowed"] is False


def test_v163_audit_requires_handoff_for_incident():
    previous = _observation()
    current = _observation(
        _refresh(catalog_available=False, review_required=True),
        _evaluation(True, ["CATALOG_UNAVAILABLE"]),
    )
    delta = build_monitoring_observation_delta(previous, current)
    incident = classify_review_monitoring_incident(delta, current)
    blocked = build_review_monitoring_audit_receipt(current, delta, incident)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_HANDOFF_REQUIRED"

    handoff = build_review_monitoring_incident_handoff(incident, _evaluation(True, ["CATALOG_UNAVAILABLE"]))
    audit = build_review_monitoring_audit_receipt(current, delta, incident, handoff)
    assert audit["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY"
    assert audit["incident_detected"] is True
    assert audit["handoff_ready"] is True
    assert audit["executed"] is False


def test_v163_clean_audit_needs_no_handoff():
    current = _observation()
    delta = build_monitoring_observation_delta(current, current)
    incident = classify_review_monitoring_incident(delta, current)
    audit = build_review_monitoring_audit_receipt(current, delta, incident)
    assert audit["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_AUDIT_READY"
    assert audit["incident_detected"] is False
    assert audit["handoff_ready"] is False


def test_malformed_observation_schema_fails_closed():
    blocked = build_monitoring_observation(
        _checkpoint(),
        _refresh(renamed_operations="not-a-list"),
        _evaluation(),
    )
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_SCHEMA_INVALID"
    assert blocked["activation_allowed"] is False
