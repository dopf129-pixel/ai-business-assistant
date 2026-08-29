from app.product_task_refresh_capability_contract import (
    build_refresh_capability_contract,
)


def _request(*components):
    return {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "targets": [
            {
                "component": component,
                "action": "REFRESH_SOURCE_DATA",
            }
            for component in components
        ],
        "execution_allowed": False,
        "executed": False,
    }


def test_sales_and_stock_use_read_only_metrics_source():
    result = build_refresh_capability_contract(
        _request("sales", "stock")
    )

    assert result["status"] == "CAPABILITY_READY"
    assert result["all_read_only"] is True
    mapped = {item["component"]: item for item in result["targets"]}
    assert mapped["sales"]["provider"] == "ProductDecisionMetricsSource"
    assert mapped["sales"]["method"] == "sales"
    assert mapped["sales"]["may_use_cache"] is False
    assert mapped["stock"]["method"] == "stock"
    assert result["execution_allowed"] is False


def test_unit_economics_declares_cache_without_proving_freshness():
    result = build_refresh_capability_contract(
        _request("unit_economics")
    )

    target = result["targets"][0]
    assert target["provider"] == "ProductUnitEconomicsQueryService"
    assert target["method"] == "query"
    assert target["may_use_cache"] is True
    assert target["source_timestamp_expected"] is False
    assert target["source_freshness_proven"] is False
    assert result["source_freshness_proven"] is False


def test_unknown_component_is_not_assumed_safe():
    result = build_refresh_capability_contract(
        _request("sales", "advertising")
    )

    assert result["status"] == "CAPABILITY_PARTIAL"
    assert result["supported_count"] == 1
    assert result["all_read_only"] is False
    unknown = next(
        item for item in result["targets"]
        if item["component"] == "advertising"
    )
    assert unknown["supported"] is False
    assert unknown["reason"] == "REFRESH_PROVIDER_NOT_DEFINED"
    assert unknown["execution_allowed"] is False


def test_empty_request_stays_non_executable():
    result = build_refresh_capability_contract({
        "request_id": None,
        "targets": [],
    })

    assert result["status"] == "CAPABILITY_UNAVAILABLE"
    assert result["target_count"] == 0
    assert result["refresh_started"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
