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


class MalformedQualityService:
    def report(self):
        return None


class FailingQualityService:
    def report(self):
        raise RuntimeError("catalog unavailable")


def test_malformed_quality_report_fails_closed():
    result = refresh_post_activation_quality(MalformedQualityService(), _request())
    assert result["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REPORT_REQUIRED"
    assert result["automatic_remap_allowed"] is False
    assert result["automatic_activation_allowed"] is False


def test_quality_service_exception_fails_closed():
    result = refresh_post_activation_quality(FailingQualityService(), _request())
    assert result["code"] == "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REPORT_REQUIRED"
    assert result["profit_adjustment_allowed"] is False
    assert result["ozon_mutation"] is False
