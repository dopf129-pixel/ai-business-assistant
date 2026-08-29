from period_profit_mapping_post_activation_quality import (
    build_post_activation_validation_request,
    refresh_post_activation_quality,
)


def _request():
    return build_post_activation_validation_request({
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
        "executed": False,
    })


class MalformedScopeQualityService:
    def report(self):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY",
            "scopes": {
                "RETURN": {
                    "mapping_available": True,
                    "active_revision_id": "return-mapping-r2",
                    "mapping_id": "return-financial-mapping:abc",
                    "catalog_available": True,
                    "freshness_status": "FRESH",
                    "missing_type_ids": [],
                    "renamed_operations": {"type_id": 1},
                    "catalog_drift_detected": False,
                    "review_required": False,
                    "quality_score": 100,
                }
            },
        }


def test_malformed_drift_schema_cannot_be_normalized_into_false_clean_state():
    result = refresh_post_activation_quality(MalformedScopeQualityService(), _request())
    assert result["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_SCHEMA_INVALID"
    assert result["automatic_remap_allowed"] is False
    assert result["automatic_activation_allowed"] is False
