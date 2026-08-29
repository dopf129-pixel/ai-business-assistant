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
            "fee_breakdown": {
                "Возвратная логистика": -5,
                "Обычная услуга": -10,
            },
            "fee_components_included": True,
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "profit_scope": "V1",
        }


def test_query_exposes_policy_driven_return_financial_evidence():
    query = PeriodProfitQueryService(
        Summary(),
        lambda: [{"sku": "1"}],
        return_financial_operation_names=["Возвратная логистика"],
    )
    result = query.query("7D", today="2026-08-29")
    evidence = result["return_financial_evidence"]
    assert evidence["policy_configured"] is True
    assert evidence["matched_operation_count"] == 1
    assert evidence["matched_amount"] == -5
    assert evidence["returns_profit_adjustment_allowed"] is False
    assert result["summary"]["profit"] == 54


def test_query_without_policy_does_not_infer_return_financial_operations():
    result = PeriodProfitQueryService(
        Summary(),
        lambda: [{"sku": "1"}],
    ).query("7D", today="2026-08-29")
    evidence = result["return_financial_evidence"]
    assert evidence["policy_configured"] is False
    assert evidence["matched_operation_count"] == 0
    assert evidence["financial_impact_supported"] is False
