from period_profit_coverage import build_period_profit_coverage
from period_profit_expense_financial_evidence import build_period_profit_expense_financial_evidence
from period_profit_response import build_period_profit_response


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-08-01",
        "date_to": "2026-08-07",
        "revenue": 1000,
        "net_accrual": 800,
        "product_cost": 300,
        "tax": 60,
        "profit": 440,
        "margin_percent": 44,
        "fee_components_included": True,
        "commission": -100,
        "logistics": -50,
        "acquiring": -10,
        "other_fees": -40,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "profit_scope": "V1",
    }


def test_authorized_return_evidence_is_shown_without_double_subtraction():
    evidence = {
        "status": "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY",
        "authorized_mapping_applied": True,
        "authorized_mapping_id": "return-financial-mapping:abc",
        "matched_operation_count": 2,
        "matched_amount": -35,
    }
    result = build_period_profit_response(_summary(), return_financial_evidence=evidence)
    assert "Сумма по mapping: 35.00 ₽" in result["text"]
    assert "повторно из прибыли не вычитаются" in result["text"]


def test_return_evidence_does_not_mark_returns_as_included():
    evidence = {
        "status": "PERIOD_PROFIT_RETURN_FINANCIAL_EVIDENCE_READY",
        "authorized_mapping_applied": True,
        "financial_impact_supported": True,
    }
    result = build_period_profit_coverage(_summary(), evidence)
    assert result["coverage_status"] == "PARTIAL"
    assert "returns" in result["missing_components"]
    assert result["return_financial_evidence_status"] == "AUTHORIZED_MAPPING_APPLIED"
    assert result["return_financial_evidence_changes_profit"] is False


def test_advertising_evidence_uses_exact_names_only():
    result = build_period_profit_expense_financial_evidence(
        {"Продвижение": -20, "Продвижение extra": -99, "Хранение": -5},
        "ADVERTISING",
        ["Продвижение"],
    )
    assert result["matched_operation_count"] == 1
    assert result["matched_amount"] == -20
    assert result["profit_adjustment_allowed"] is False
    assert result["automatic_classification_allowed"] is False


def test_storage_without_policy_does_not_guess():
    result = build_period_profit_expense_financial_evidence(
        {"Хранение": -5},
        "STORAGE",
        [],
    )
    assert result["policy_configured"] is False
    assert result["matched_operation_count"] == 0
