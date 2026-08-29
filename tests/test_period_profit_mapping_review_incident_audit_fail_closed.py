from period_profit_mapping_review_incident_audit import build_monitoring_observation


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


def _evaluation(reopened, reasons):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED" if reopened else "PERIOD_PROFIT_MAPPING_REVIEW_STILL_CLOSED",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "review_reopened": reopened,
        "reopen_reasons": list(reasons),
    }


def test_forged_clean_evaluation_cannot_hide_catalog_drift():
    blocked = build_monitoring_observation(
        _checkpoint(),
        _refresh(missing_type_ids=[7], catalog_drift_detected=True, review_required=True),
        _evaluation(False, []),
    )
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_STATE_INVALID"
    assert blocked["automatic_remap_allowed"] is False
    assert blocked["activation_allowed"] is False


def test_forged_reopen_reason_cannot_change_incident_evidence():
    blocked = build_monitoring_observation(
        _checkpoint(),
        _refresh(catalog_available=False, review_required=True),
        _evaluation(True, ["FRESHNESS_NOT_FRESH"]),
    )
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_STATE_INVALID"


def test_malformed_missing_type_id_fails_closed():
    blocked = build_monitoring_observation(
        _checkpoint(),
        _refresh(missing_type_ids=["not-an-id"], catalog_drift_detected=True, review_required=True),
        _evaluation(True, ["MISSING_TYPE_IDS"]),
    )
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_SCHEMA_INVALID"


def test_non_boolean_drift_flags_fail_closed():
    blocked = build_monitoring_observation(
        _checkpoint(),
        _refresh(catalog_drift_detected="false"),
        _evaluation(False, []),
    )
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_OBSERVATION_SCHEMA_INVALID"
