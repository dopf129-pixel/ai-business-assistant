from period_profit_coverage import build_period_profit_coverage


def _summary(**values):
    result = {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "fee_components_included": True,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
    }
    result.update(values)
    return result


def test_partial_coverage_lists_included_and_missing_components():
    result = build_period_profit_coverage(_summary())
    assert result["status"] == "PERIOD_PROFIT_COVERAGE_READY"
    assert result["coverage_status"] == "PARTIAL"
    assert result["included_components"] == ["ozon_fee_components"]
    assert result["missing_components"] == ["returns", "advertising", "storage"]
    assert result["all_tracked_components_included"] is False
    assert result["accounting_net_profit_claim_allowed"] is False
    assert result["executed"] is False


def test_complete_means_only_all_tracked_components_are_present():
    result = build_period_profit_coverage(_summary(
        returns_included=True,
        advertising_included=True,
        storage_included=True,
    ))
    assert result["coverage_status"] == "COMPLETE"
    assert result["all_tracked_components_included"] is True
    assert result["missing_components"] == []
    assert result["accounting_net_profit_claim_allowed"] is False


def test_invalid_summary_blocks():
    result = build_period_profit_coverage({"error": True})
    assert result["code"] == "PERIOD_PROFIT_COVERAGE_SUMMARY_REQUIRED"
