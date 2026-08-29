from services.period_profit_query_service import PeriodProfitQueryService


class Summary:
    def calculate(self, date_from, date_to, products):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": date_from,
            "date_to": date_to,
            "revenue": 100,
            "net_accrual": 80,
            "product_cost": 20,
            "tax": 6,
            "profit": 54,
            "margin_percent": 54,
            "products": [],
            "fee_breakdown": {"Return fee": -5, "Other": -10},
            "fee_components_included": True,
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "profit_scope": "V1",
        }


def _mapping(**overrides):
    result = {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY",
        "mapping_id": "return-financial-mapping:test",
        "operation_names": ["Return fee"],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "immutable_artifact": True,
        "returns_profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
    }
    result.update(overrides)
    return result


def test_authorized_mapping_drives_exact_financial_evidence():
    service = PeriodProfitQueryService(Summary(), lambda: [], authorized_return_mapping=_mapping())
    result = service.query(period_code="TODAY", today="2026-08-29")
    evidence = result["return_financial_evidence"]
    assert evidence["matched_operation_count"] == 1
    assert evidence["matched_amount"] == -5
    assert evidence["authorized_mapping_applied"] is True
    assert evidence["authorized_mapping_id"] == "return-financial-mapping:test"
    assert evidence["returns_profit_adjustment_allowed"] is False
    assert result["summary"]["profit"] == 54


def test_unsafe_mapping_is_not_applied():
    service = PeriodProfitQueryService(
        Summary(),
        lambda: [],
        authorized_return_mapping=_mapping(returns_profit_adjustment_allowed=True),
    )
    result = service.query(period_code="TODAY", today="2026-08-29")
    evidence = result["return_financial_evidence"]
    assert evidence["authorized_mapping_applied"] is False
    assert evidence["matched_operation_count"] == 0
