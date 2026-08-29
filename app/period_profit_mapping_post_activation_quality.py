SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}


def build_post_activation_validation_request(activation_audit):
    """v149: bind post-activation quality validation to the exact explicitly activated mapping."""
    source = _dict(activation_audit)
    scope = _scope(source.get("scope"))
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REPLACEMENT_ACTIVATION_AUDIT_READY"
        or source.get("error") is not False
        or source.get("decision") != "APPLY"
        or source.get("explicit_human_apply") is not True
        or source.get("registry_verified") is not True
        or source.get("automatic_activation") is not False
        or source.get("profit_adjustment_allowed") is not False
        or source.get("ozon_mutation") is not False
        or source.get("executed") is not False
        or scope not in SCOPES
        or not source.get("revision_id")
        or not source.get("mapping_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_AUDIT_REQUIRED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_VALIDATION_REQUEST_READY",
        "scope": scope,
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "exact_catalog_evidence_required": True,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def refresh_post_activation_quality(quality_service, validation_request):
    """v150: read the existing quality service after activation and bind its scope result to the activated lineage."""
    request = _dict(validation_request)
    if request.get("status") != "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_VALIDATION_REQUEST_READY" or request.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_VALIDATION_REQUEST_REQUIRED")
    report = quality_service.report()
    if report.get("error") is not False or report.get("status") != "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY":
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REPORT_REQUIRED")
    scope = request.get("scope")
    scope_quality = _dict(_dict(report.get("scopes")).get(scope))
    if not scope_quality or scope_quality.get("mapping_available") is not True:
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_ACTIVE_MAPPING_REQUIRED")
    if (
        scope_quality.get("active_revision_id") != request.get("revision_id")
        or scope_quality.get("mapping_id") != request.get("mapping_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_LINEAGE_MISMATCH")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REFRESHED",
        "scope": scope,
        "revision_id": request.get("revision_id"),
        "mapping_id": request.get("mapping_id"),
        "catalog_available": scope_quality.get("catalog_available") is True,
        "freshness_status": scope_quality.get("freshness_status"),
        "missing_type_ids": list(scope_quality.get("missing_type_ids") or []),
        "renamed_operations": [dict(row) for row in scope_quality.get("renamed_operations") or [] if isinstance(row, dict)],
        "catalog_drift_detected": scope_quality.get("catalog_drift_detected") is True,
        "review_required": scope_quality.get("review_required") is True,
        "quality_score": scope_quality.get("quality_score"),
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def evaluate_post_activation_review_closure(refreshed_quality):
    """v151-v152: close only with current exact-catalog evidence; otherwise stay unresolved and fail closed."""
    source = _dict(refreshed_quality)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REFRESHED" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REFRESHED_QUALITY_REQUIRED")

    reasons = []
    if source.get("catalog_available") is not True:
        reasons.append("CATALOG_UNAVAILABLE")
    if source.get("missing_type_ids"):
        reasons.append("MISSING_TYPE_IDS")
    if source.get("renamed_operations"):
        reasons.append("RENAMED_OPERATIONS")
    if source.get("catalog_drift_detected") is True and not (source.get("missing_type_ids") or source.get("renamed_operations")):
        reasons.append("CATALOG_DRIFT")
    if source.get("freshness_status") != "FRESH":
        reasons.append("FRESHNESS_NOT_FRESH")
    if source.get("review_required") is True and not reasons:
        reasons.append("REVIEW_STILL_REQUIRED")

    closed = not reasons
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REVIEW_CLOSED" if closed else "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REVIEW_UNRESOLVED",
        "scope": source.get("scope"),
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "review_closed": closed,
        "unresolved_reasons": reasons,
        "catalog_available": source.get("catalog_available") is True,
        "quality_score": source.get("quality_score"),
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_post_activation_completion_report(validation_request, refreshed_quality, closure):
    """v153: emit a deterministic read-only completion report for the replacement review lifecycle."""
    request = _dict(validation_request)
    refreshed = _dict(refreshed_quality)
    result = _dict(closure)
    if (
        request.get("status") != "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_VALIDATION_REQUEST_READY"
        or refreshed.get("status") != "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_REFRESHED"
        or result.get("status") not in {"PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REVIEW_CLOSED", "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_REVIEW_UNRESOLVED"}
        or request.get("error") is not False
        or refreshed.get("error") is not False
        or result.get("error") is not False
    ):
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_INPUT_REQUIRED")
    lineage = (request.get("scope"), request.get("revision_id"), request.get("mapping_id"))
    if lineage != (refreshed.get("scope"), refreshed.get("revision_id"), refreshed.get("mapping_id")) or lineage != (result.get("scope"), result.get("revision_id"), result.get("mapping_id")):
        return _error("PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_LINEAGE_MISMATCH")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_REPORT_READY",
        "scope": request.get("scope"),
        "revision_id": request.get("revision_id"),
        "mapping_id": request.get("mapping_id"),
        "review_closed": result.get("review_closed") is True,
        "unresolved_reasons": list(result.get("unresolved_reasons") or []),
        "catalog_available": refreshed.get("catalog_available") is True,
        "freshness_status": refreshed.get("freshness_status"),
        "quality_score": refreshed.get("quality_score"),
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def _scope(value):
    return str(value or "").strip().upper()


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_QUALITY_UNAVAILABLE",
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
