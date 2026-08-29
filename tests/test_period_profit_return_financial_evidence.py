from period_profit_return_financial_evidence import build_period_profit_return_financial_evidence


def test_requires_explicit_policy_before_financial_support():
    result = build_period_profit_return_financial_evidence(
        [{"fee_breakdown": {"Возвратная логистика": -50}}],
        [],
    )
    assert result["policy_configured"] is False
    assert result["matched_operation_count"] == 0
    assert result["financial_impact_supported"] is False
    assert result["returns_profit_adjustment_allowed"] is False


def test_matches_only_exact_allowed_operation_names():
    rows = [{
        "fee_breakdown": {
            "Возвратная логистика": -50,
            "Возвратная логистика дополнительная": -10,
            "Обычная логистика": -100,
        }
    }]
    result = build_period_profit_return_financial_evidence(
        rows,
        ["Возвратная логистика"],
    )
    assert result["matched_operation_count"] == 1
    assert result["matched_amount"] == -50
    assert result["matched_operations"][0]["operation_name"] == "Возвратная логистика"
    assert result["financial_impact_supported"] is True
    assert result["returns_profit_adjustment_allowed"] is False


def test_unknown_rows_are_ignored_without_inference():
    result = build_period_profit_return_financial_evidence(
        [None, {}, {"fee_breakdown": []}],
        ["Возврат"],
    )
    assert result["matched_operation_count"] == 0
    assert result["matched_amount"] == 0
    assert result["financial_impact_supported"] is False
