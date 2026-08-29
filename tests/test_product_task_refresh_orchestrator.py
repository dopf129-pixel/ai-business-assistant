from app.product_task_refresh_orchestrator import execute_read_only_refresh


class _MetricsSource:
    def __init__(self):
        self.calls = []

    def sales(self, sku):
        self.calls.append(("sales", sku))
        return {"sku": sku, "sales_observed_at": "2026-08-29T12:00:00+00:00"}

    def stock(self, sku):
        self.calls.append(("stock", sku))
        return {"sku": sku, "stock_observed_at": "2026-08-29T12:00:00+00:00"}


class _EconomicsQuery:
    def __init__(self):
        self.calls = []

    def query(self, sku):
        self.calls.append(("query", sku))
        return {
            "sku": sku,
            "available": True,
            "cache": {"status": "hit"},
        }


class _FailingMetricsSource:
    def sales(self, sku):
        raise RuntimeError("read failed")


def _contract(*targets, all_read_only=True):
    return {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "all_read_only": all_read_only,
        "targets": list(targets),
        "execution_allowed": False,
    }


def _target(component, provider, method, may_use_cache=False):
    return {
        "component": component,
        "supported": True,
        "provider": provider,
        "method": method,
        "read_only": True,
        "may_use_cache": may_use_cache,
    }


def test_executes_only_declared_read_only_targets():
    metrics = _MetricsSource()
    contract = _contract(
        _target("sales", "ProductDecisionMetricsSource", "sales"),
        _target("stock", "ProductDecisionMetricsSource", "stock"),
    )

    result = execute_read_only_refresh(
        contract,
        {"ProductDecisionMetricsSource": metrics},
    )

    assert result["status"] == "COMPLETED"
    assert metrics.calls == [("sales", "hook-2"), ("stock", "hook-2")]
    assert result["result_count"] == 2
    assert result["source_freshness_proven"] is False
    assert result["product_decision_recomputed"] is False
    assert result["task_draft_mutated"] is False
    assert result["executed"] is False


def test_blocks_partial_or_non_read_only_capability_before_provider_calls():
    metrics = _MetricsSource()
    contract = _contract(
        _target("sales", "ProductDecisionMetricsSource", "sales"),
        all_read_only=False,
    )

    result = execute_read_only_refresh(
        contract,
        {"ProductDecisionMetricsSource": metrics},
    )

    assert result["status"] == "BLOCKED"
    assert metrics.calls == []
    assert result["errors"] == ["REFRESH_CAPABILITY_NOT_FULLY_READ_ONLY"]
    assert result["execution_allowed"] is False


def test_unit_economics_cache_result_does_not_prove_source_freshness():
    economics = _EconomicsQuery()
    contract = _contract(
        _target(
            "unit_economics",
            "ProductUnitEconomicsQueryService",
            "query",
            may_use_cache=True,
        )
    )

    result = execute_read_only_refresh(
        contract,
        {"ProductUnitEconomicsQueryService": economics},
    )

    item = result["results"][0]
    assert item["may_use_cache"] is True
    assert item["data"]["cache"]["status"] == "hit"
    assert item["source_freshness_proven"] is False
    assert result["source_freshness_proven"] is False


def test_provider_failure_is_observational_and_does_not_enable_execution():
    contract = _contract(
        _target("sales", "ProductDecisionMetricsSource", "sales")
    )

    result = execute_read_only_refresh(
        contract,
        {"ProductDecisionMetricsSource": _FailingMetricsSource()},
    )

    assert result["status"] == "FAILED"
    assert result["error_count"] == 1
    assert result["errors"][0]["code"] == "REFRESH_READ_FAILED"
    assert result["persistent"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
