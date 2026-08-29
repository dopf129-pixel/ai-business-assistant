from period_profit_mapping_review_monitoring import (
    build_review_closure_checkpoint,
    build_review_reopen_handoff,
    evaluate_review_checkpoint,
    refresh_review_checkpoint,
)


class FakeQualityService:
    def __init__(self, scope_quality):
        self.scope_quality = dict(scope_quality)

    def report(self):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY",
            "scopes": {"RETURN": dict(self.scope_quality)},
        }


class FakeRegistry:
    def __init__(self, mapping):
        self.mapping = dict(mapping)

    def load_active(self, scope):
        return dict(self.mapping)


class FakeCatalog:
    def __init__(self, operations):
        self.operations = list(operations)

    def load(self):
        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
            "operations": list(self.operations),
        }


def _completion(**overrides):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_REPORT_READY",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "review_closed": True,
        "unresolved_reasons": [],
        "catalog_available": True,
        "freshness_status": "FRESH",
        "quality_score": 100,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }
    result.update(overrides)
    return result


def _quality(**overrides):
    result = {
        "scope": "RETURN",
        "active_revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "mapping_available": True,
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


def test_v154_checkpoint_requires_fully_closed_completion():
    checkpoint = build_review_closure_checkpoint(_completion())
    assert checkpoint["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_READY"
    assert checkpoint["monitoring_required"] is True
    blocked = build_review_closure_checkpoint(_completion(review_closed=False, unresolved_reasons=["DRIFT"]))
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_CLOSED_COMPLETION_REQUIRED"


def test_v155_refresh_binds_exact_lineage():
    checkpoint = build_review_closure_checkpoint(_completion())
    refreshed = refresh_review_checkpoint(FakeQualityService(_quality()), checkpoint)
    assert refreshed["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESHED"
    mismatch = refresh_review_checkpoint(FakeQualityService(_quality(active_revision_id="return-mapping-r3")), checkpoint)
    assert mismatch["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_LINEAGE_CHANGED"


def test_v156_clean_checkpoint_stays_closed():
    checkpoint = build_review_closure_checkpoint(_completion())
    refreshed = refresh_review_checkpoint(FakeQualityService(_quality()), checkpoint)
    result = evaluate_review_checkpoint(refreshed)
    assert result["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_STILL_CLOSED"
    assert result["review_reopened"] is False
    assert result["automatic_remap_allowed"] is False


def test_v157_drift_reopens_review_without_mutation():
    checkpoint = build_review_closure_checkpoint(_completion())
    refreshed = refresh_review_checkpoint(
        FakeQualityService(_quality(
            renamed_operations=[{"type_id": 1, "mapped_name": "Old", "current_name": "New"}],
            catalog_drift_detected=True,
            review_required=True,
        )),
        checkpoint,
    )
    result = evaluate_review_checkpoint(refreshed)
    assert result["status"] == "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED"
    assert result["review_reopened"] is True
    assert "RENAMED_OPERATIONS" in result["reopen_reasons"]
    assert result["human_rereview_required"] is True
    assert result["automatic_activation_allowed"] is False


def test_v158_reopened_review_hands_off_to_existing_human_rereview_candidate():
    checkpoint = build_review_closure_checkpoint(_completion())
    drift_quality = _quality(
        renamed_operations=[{"type_id": 1, "mapped_name": "Old", "current_name": "New"}],
        catalog_drift_detected=True,
        review_required=True,
    )
    evaluation = evaluate_review_checkpoint(refresh_review_checkpoint(FakeQualityService(drift_quality), checkpoint))
    mapping = {
        "mapping_id": "return-financial-mapping:abc",
        "scope": "RETURN",
        "operations": [{"type_id": 1, "name": "Old", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}],
    }
    catalog_ops = [{"type_id": 1, "name": "New", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}]
    candidate = build_review_reopen_handoff(
        FakeRegistry(mapping), FakeCatalog(catalog_ops), FakeQualityService(drift_quality), evaluation
    )
    assert candidate["status"] == "PERIOD_PROFIT_MAPPING_REREVIEW_CANDIDATE_READY"
    assert candidate["human_confirmation_required"] is True
    assert candidate["automatic_remap_allowed"] is False


def test_malformed_monitoring_quality_fails_closed():
    checkpoint = build_review_closure_checkpoint(_completion())
    malformed = _quality(renamed_operations="bad")
    result = refresh_review_checkpoint(FakeQualityService(malformed), checkpoint)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_QUALITY_SCHEMA_INVALID"
