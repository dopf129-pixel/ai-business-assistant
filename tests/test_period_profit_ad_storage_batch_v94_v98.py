from period_profit_expense_operation_review import build_period_profit_expense_operation_review
from period_profit_expense_operation_selection import build_period_profit_expense_operation_selection
from period_profit_expense_operation_authorized_mapping import (
    build_period_profit_expense_operation_authorization,
    build_period_profit_expense_operation_authorized_mapping,
)
from period_profit_response import build_period_profit_response


def _catalog():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
        "operations": [
            {"type_id": 2, "name": "Promo", "description": "Ads", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 10, "name": "Storage", "description": "Warehouse", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def _summary():
    return {
        "error": False, "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-08-01", "date_to": "2026-08-07",
        "revenue": 1000, "net_accrual": 800, "product_cost": 300, "tax": 60,
        "profit": 440, "margin_percent": 44, "fee_components_included": True,
        "commission": -100, "logistics": -50, "acquiring": -10, "other_fees": -40,
        "returns_included": False, "advertising_included": False, "storage_included": False,
        "profit_scope": "V1",
    }


def test_advertising_review_never_classifies_automatically():
    result = build_period_profit_expense_operation_review(_catalog(), "ADVERTISING")
    assert result["operations"][0]["expense_related"] is None
    assert result["automatic_classification_allowed"] is False
    assert result["mapping_activation_allowed"] is False


def test_selection_and_authorization_preserve_exact_source_rows():
    review = build_period_profit_expense_operation_review(_catalog(), "STORAGE")
    selection = build_period_profit_expense_operation_selection(review, [10])
    authorization = build_period_profit_expense_operation_authorization(selection, "AUTHORIZE")
    assert selection["selected_operation_names"] == ["Storage"]
    assert authorization["financial_evidence_mapping_allowed"] is True
    assert authorization["profit_adjustment_allowed"] is False


def test_authorized_mapping_is_deterministic_and_non_persistent():
    review = build_period_profit_expense_operation_review(_catalog(), "ADVERTISING")
    selection = build_period_profit_expense_operation_selection(review, [2])
    auth = build_period_profit_expense_operation_authorization(selection, "AUTHORIZE")
    first = build_period_profit_expense_operation_authorized_mapping(auth)
    second = build_period_profit_expense_operation_authorized_mapping(auth)
    assert first["mapping_id"] == second["mapping_id"]
    assert first["scope"] == "ADVERTISING"
    assert first["persistent"] is False
    assert first["automatic_activation_allowed"] is False
    assert first["profit_adjustment_allowed"] is False


def test_response_shows_authorized_advertising_and_storage_evidence_without_double_subtraction():
    advertising = {
        "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY", "authorized_mapping_applied": True,
        "authorized_mapping_id": "period-profit-advertising-mapping:abc", "matched_operation_count": 2, "matched_amount": -25,
    }
    storage = {
        "status": "PERIOD_PROFIT_EXPENSE_EVIDENCE_READY", "authorized_mapping_applied": True,
        "authorized_mapping_id": "period-profit-storage-mapping:def", "matched_operation_count": 1, "matched_amount": -5,
    }
    result = build_period_profit_response(_summary(), advertising_financial_evidence=advertising, storage_financial_evidence=storage)
    assert "Подтверждённые операции рекламы" in result["text"]
    assert "Подтверждённые операции хранения" in result["text"]
    assert "25.00 ₽" in result["text"]
    assert "5.00 ₽" in result["text"]
    assert "повторно не вычитаются" in result["text"]
