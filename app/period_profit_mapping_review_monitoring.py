from period_profit_mapping_rereview import build_mapping_rereview_candidate


SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}


def build_review_closure_checkpoint(completion_report):
    """v154: freeze a read-only checkpoint only from a fully closed post-activation review."""
    source = _dict(completion_report)
    scope = _scope(source.get("scope"))
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_POST_ACTIVATION_COMPLETION_REPORT_READY"
        or source.get("error") is not False
        or source.get("review_closed") is not True
        or source.get("catalog_available") is not True
        or source.get("freshness_status") != "FRESH"
        or source.get("unresolved_reasons") not in ([], ())
        or source.get("automatic_remap_allowed") is not False
        or source.get("automatic_activation_allowed") is not False
        or source.get("profit_adjustment_allowed") is not False
        or source.get("ozon_mutation") is not False
        or source.get("executed") is not False
        or scope not in SCOPES
        or not source.get("revision_id")
        or not source.get("mapping_id")
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_CLOSED_COMPLETION_REQUIRED")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_READY",
        "scope": scope,
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "closure_quality_score": source.get("quality_score"),
        "review_closed": True,
        "monitoring_required": True,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def refresh_review_checkpoint(quality_service, checkpoint):
    """v155: re-read current quality and bind it to the exact closed lineage."""
    source = _dict(checkpoint)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_READY" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_CLOSURE_CHECKPOINT_REQUIRED")
    try:
        report = quality_service.report()
    except Exception:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_QUALITY_REQUIRED")
    if not isinstance(report, dict) or report.get("error") is not False or report.get("status") != "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY":
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_QUALITY_REQUIRED")
    quality = _dict(_dict(report.get("scopes")).get(source.get("scope")))
    if quality.get("mapping_available") is not True:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_ACTIVE_MAPPING_REQUIRED")
    if quality.get("active_revision_id") != source.get("revision_id") or quality.get("mapping_id") != source.get("mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_LINEAGE_CHANGED")
    missing = quality.get("missing_type_ids")
    renamed = quality.get("renamed_operations")
    if not isinstance(missing, list) or not isinstance(renamed, list) or not all(isinstance(row, dict) for row in renamed):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_QUALITY_SCHEMA_INVALID")
    if not isinstance(quality.get("catalog_drift_detected"), bool) or not isinstance(quality.get("review_required"), bool):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_QUALITY_SCHEMA_INVALID")
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESHED",
        "scope": source.get("scope"),
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "catalog_available": quality.get("catalog_available") is True,
        "freshness_status": quality.get("freshness_status"),
        "missing_type_ids": list(missing),
        "renamed_operations": [dict(row) for row in renamed],
        "catalog_drift_detected": quality.get("catalog_drift_detected"),
        "review_required": quality.get("review_required"),
        "quality_score": quality.get("quality_score"),
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def evaluate_review_checkpoint(refresh):
    """v156-v157: keep closure only on clean evidence; otherwise reopen review descriptively."""
    source = _dict(refresh)
    if source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESHED" or source.get("error") is not False:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_REFRESH_REQUIRED")
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
        reasons.append("REVIEW_REQUIRED")
    reopened = bool(reasons)
    return {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED" if reopened else "PERIOD_PROFIT_MAPPING_REVIEW_STILL_CLOSED",
        "scope": source.get("scope"),
        "revision_id": source.get("revision_id"),
        "mapping_id": source.get("mapping_id"),
        "review_reopened": reopened,
        "reopen_reasons": reasons,
        "human_rereview_required": reopened,
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "read_only": True,
        "executed": False,
    }


def build_review_reopen_handoff(registry_service, catalog_service, quality_service, evaluation):
    """v158: hand reopened drift back to the existing human re-review candidate builder."""
    source = _dict(evaluation)
    if (
        source.get("status") != "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED"
        or source.get("error") is not False
        or source.get("review_reopened") is not True
        or source.get("human_rereview_required") is not True
    ):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_REOPENED_STATE_REQUIRED")
    try:
        quality_report = quality_service.report()
        catalog = catalog_service.load()
        active_mapping = registry_service.load_active(source.get("scope"))
    except Exception:
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_REOPEN_HANDOFF_EVIDENCE_REQUIRED")
    if not isinstance(quality_report, dict) or not isinstance(catalog, dict) or not isinstance(active_mapping, dict):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_REOPEN_HANDOFF_EVIDENCE_REQUIRED")
    quality = _dict(_dict(quality_report.get("scopes")).get(source.get("scope")))
    if quality.get("active_revision_id") != source.get("revision_id") or active_mapping.get("mapping_id") != source.get("mapping_id"):
        return _error("PERIOD_PROFIT_MAPPING_REVIEW_REOPEN_HANDOFF_LINEAGE_CHANGED")
    candidate = build_mapping_rereview_candidate(quality, active_mapping, catalog)
    if candidate.get("error") is not False:
        return candidate
    return candidate


def _scope(value):
    return str(value or "").strip().upper()


def _dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _error(code):
    return {
        "error": True,
        "code": code,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_MONITORING_UNAVAILABLE",
        "automatic_remap_allowed": False,
        "automatic_activation_allowed": False,
        "profit_adjustment_allowed": False,
        "ozon_mutation": False,
        "executed": False,
    }
