from copy import deepcopy


SAFE_PROVIDER_NAMES = {
    "ProductDecisionMetricsSource",
    "ProductUnitEconomicsQueryService",
}


def execute_read_only_refresh(capability_contract, providers):
    contract = deepcopy(capability_contract or {})
    provider_map = dict(providers or {})
    targets = contract.get("targets") or []

    if not targets:
        return _result(
            contract,
            status="NOT_REQUIRED",
            results=[],
            errors=[],
        )

    if contract.get("all_read_only") is not True:
        return _result(
            contract,
            status="BLOCKED",
            results=[],
            errors=["REFRESH_CAPABILITY_NOT_FULLY_READ_ONLY"],
        )

    sku = str(contract.get("sku") or "").strip()
    if not sku:
        return _result(
            contract,
            status="BLOCKED",
            results=[],
            errors=["SKU_REQUIRED"],
        )

    results = []
    errors = []

    for target in targets:
        provider_name = target.get("provider")
        method_name = target.get("method")
        component = target.get("component")

        if (
            target.get("supported") is not True
            or target.get("read_only") is not True
            or provider_name not in SAFE_PROVIDER_NAMES
        ):
            errors.append({
                "component": component,
                "code": "REFRESH_TARGET_NOT_ALLOWED",
            })
            continue

        provider = provider_map.get(provider_name)
        method = getattr(provider, str(method_name or ""), None)
        if provider is None or not callable(method):
            errors.append({
                "component": component,
                "code": "REFRESH_PROVIDER_UNAVAILABLE",
            })
            continue

        try:
            value = method(sku)
        except Exception as error:
            errors.append({
                "component": component,
                "code": "REFRESH_READ_FAILED",
                "message": str(error),
            })
            continue

        results.append({
            "component": component,
            "provider": provider_name,
            "method": method_name,
            "read_only": True,
            "may_use_cache": bool(target.get("may_use_cache")),
            "data": deepcopy(value),
            "source_freshness_proven": False,
        })

    status = "COMPLETED" if not errors else "PARTIAL" if results else "FAILED"
    return _result(contract, status=status, results=results, errors=errors)


def _result(contract, status, results, errors):
    return {
        "error": status in {"BLOCKED", "FAILED"},
        "request_id": contract.get("request_id"),
        "draft_id": contract.get("draft_id"),
        "sku": contract.get("sku"),
        "status": status,
        "results": deepcopy(results),
        "result_count": len(results),
        "errors": deepcopy(errors),
        "error_count": len(errors),
        "read_only_refresh": True,
        "persistent": False,
        "source_freshness_proven": False,
        "product_decision_recomputed": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
