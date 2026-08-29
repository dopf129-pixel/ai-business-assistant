from return_financial_operation_authorized_mapping import (
    build_return_financial_operation_authorized_mapping,
)


def _authorization():
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED",
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": [
            {"type_id": 10, "name": "B", "description": "BB", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
            {"type_id": 2, "name": "A", "description": "AA", "source": "OZON_FINANCE_ACCRUAL_TYPES"},
        ],
    }


def test_mapping_is_deterministic_and_immutable():
    first = build_return_financial_operation_authorized_mapping(_authorization())
    second = build_return_financial_operation_authorized_mapping(_authorization())
    assert first["status"] == "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY"
    assert first["mapping_id"] == second["mapping_id"]
    assert first["type_ids"] == [2, 10]
    assert first["operation_names"] == ["A", "B"]
    assert first["immutable_artifact"] is True
    assert first["persistent"] is False
    assert first["returns_profit_adjustment_allowed"] is False
    assert first["automatic_activation_allowed"] is False
    assert first["executed"] is False


def test_unauthorized_input_blocks():
    result = build_return_financial_operation_authorized_mapping({"error": False})
    assert result["code"] == "RETURN_FINANCIAL_OPERATION_AUTHORIZATION_REQUIRED"
