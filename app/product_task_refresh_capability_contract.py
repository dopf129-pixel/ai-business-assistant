from copy import deepcopy


REFRESH_CAPABILITIES = {
    "sales": {
        "provider": "ProductDecisionMetricsSource",
        "method": "sales",
        "read_only": True,
        "may_use_cache": False,
        "source_timestamp_expected": False,
    },
    "stock": {
        "provider": "ProductDecisionMetricsSource",
        "method": "stock",
        "read_only": True,
        "may_use_cache": False,
        "source_timestamp_expected": False,
    },
    "unit_economics": {
        "provider": "ProductUnitEconomicsQueryService",
        "method": "query",
        "read_only": True,
        "may_use_cache": True,
        "source_timestamp_expected": False,
    },
}


def build_refresh_capability_contract(refresh_request):
    request = deepcopy(refresh_request or {})
    targets = []

    for target in request.get("targets") or []:
        component = str(target.get("component") or "").strip()
        capability = REFRESH_CAPABILITIES.get(component)
        if capability is None:
            targets.append({
                "component": component or None,
                "supported": False,
                "reason": "REFRESH_PROVIDER_NOT_DEFINED",
                "execution_allowed": False,
            })
            continue

        item = deepcopy(target)
        item.update({
            "supported": True,
            **deepcopy(capability),
            "source_freshness_proven": False,
            "refresh_execution_connected": False,
            "execution_allowed": False,
        })
        targets.append(item)

    supported_count = sum(
        1 for item in targets if item.get("supported") is True
    )
    all_supported = bool(targets) and supported_count == len(targets)

    return {
        "error": False,
        "request_id": request.get("request_id"),
        "draft_id": request.get("draft_id"),
        "sku": request.get("sku"),
        "status": (
            "CAPABILITY_READY"
            if all_supported
            else "CAPABILITY_PARTIAL"
            if supported_count
            else "CAPABILITY_UNAVAILABLE"
        ),
        "targets": targets,
        "target_count": len(targets),
        "supported_count": supported_count,
        "all_read_only": all_supported and all(
            item.get("read_only") is True
            for item in targets
        ),
        "persistent": False,
        "refresh_started": False,
        "source_freshness_proven": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
