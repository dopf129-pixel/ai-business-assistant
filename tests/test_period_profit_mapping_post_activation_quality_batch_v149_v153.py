from period_profit_mapping_post_activation_quality import (
    build_post_activation_completion_report,
    build_post_activation_validation_request,
    evaluate_post_activation_review_closure,
    refresh_post_activation_quality,
)


class FakeQualityService:
    def __init__(self, scope_quality):
        self.scope_quality = dict(scope_quality)

    def report(self):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY",
            "scopes": {"RETURN": dict(self.scope_quality)},
            "automatic_remap_allowed": False,
            "automatic_activation_allowed": False,
            "profit_adjustment_allowed": False,
            "ozon_mutation": False,
            "read_only": True,
            "executed": False,
        }


def _audit():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_AUDIT_READY",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "decision": "APPLY",
        "explicit_human_apply": True,
        "registry_verified": True,
        "automatic_activation": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


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


def test_v149_requires_verified_explicit_activation_audit():
    request = build_post_activation_validation_request(_audit())
    assert request["status"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_VALIDATION_REQUEST_READY"
    assert request["revision_id"] == "return-mapping-r2"
    assert request["exact_catalog_evidence_required"] is True
    assert request["automatic_remap_allowed"] is False

    tampered = dict(_audit(), explicit_human_apply=False)
    blocked = build_post_activation_validation_request(tampered)
    assert blocked["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_AUDIT_REQUIRED"


def test_v150_refresh_binds_quality_to_exact_active_lineage():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(FakeQualityService(_quality()), request)
    assert refreshed["status"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REFRESHED"
    assert refreshed["revision_id"] == request["revision_id"]
    assert refreshed["mapping_id"] == request["mapping_id"]
    assert refreshed["catalog_available"] is True


def test_v150_lineage_mismatch_fails_closed():
    request = build_post_activation_validation_request(_audit())
    service = FakeQualityService(_quality(active_revision_id="return-mapping-r3"))
    result = refresh_post_activation_quality(service, request)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_LINEAGE_MISMATCH"
    assert result["automatic_activation_allowed"] is False


def test_v151_closes_only_fresh_catalog_clean_mapping():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(FakeQualityService(_quality()), request)
    closure = evaluate_post_activation_review_closure(refreshed)
    assert closure["status"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REVIEW_CLOSED"
    assert closure["review_closed"] is True
    assert closure["unresolved_reasons"] == []
    assert closure["profit_adjustment_allowed"] is False


def test_v152_catalog_unavailable_stays_unresolved():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(
        FakeQualityService(_quality(catalog_available=False, review_required=True, quality_score=70)),
        request,
    )
    closure = evaluate_post_activation_review_closure(refreshed)
    assert closure["review_closed"] is False
    assert "CATALOG_UNAVAILABLE" in closure["unresolved_reasons"]
    assert closure["automatic_remap_allowed"] is False


def test_v152_drift_and_stale_evidence_stay_unresolved():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(
        FakeQualityService(_quality(
            freshness_status="STALE",
            missing_type_ids=[9],
            renamed_operations=[{"type_id": 1, "mapped_name": "Old", "current_name": "New"}],
            catalog_drift_detected=True,
            review_required=True,
            quality_score=30,
        )),
        request,
    )
    closure = evaluate_post_activation_review_closure(refreshed)
    assert closure["review_closed"] is False
    assert closure["unresolved_reasons"] == ["MISSING_TYPE_IDS", "RENAMED_OPERATIONS", "FRESHNESS_NOT_FRESH"]


def test_v153_completion_report_preserves_exact_lineage_and_safety():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(FakeQualityService(_quality()), request)
    closure = evaluate_post_activation_review_closure(refreshed)
    report = build_post_activation_completion_report(request, refreshed, closure)
    assert report["status"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_REPORT_READY"
    assert report["review_closed"] is True
    assert report["revision_id"] == "return-mapping-r2"
    assert report["mapping_id"] == "return-financial-mapping:abc"
    assert report["ozon_mutation"] is False
    assert report["executed"] is False


def test_v153_mixed_lineage_cannot_produce_completion_report():
    request = build_post_activation_validation_request(_audit())
    refreshed = refresh_post_activation_quality(FakeQualityService(_quality()), request)
    closure = evaluate_post_activation_review_closure(refreshed)
    tampered = dict(closure, mapping_id="other")
    result = build_post_activation_completion_report(request, refreshed, tampered)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_LINEAGE_MISMATCH"
    assert result["automatic_remap_allowed"] is False
