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
            "fee_components_included": True,
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "profit_scope": "V1",
        }


class Returns:
    def __init__(self, result): self.result = result; self.calls = []
    def load(self, date_from, date_to):
        self.calls.append((date_from, date_to))
        return self.result


def test_query_exposes_return_evidence_without_marking_returns_included():
    evidence = Returns({
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
        "return_record_count": 2,
        "returns_observed": True,
        "financial_impact_supported": False,
        "returns_profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    })
    result = PeriodProfitQueryService(Summary(), lambda: [{"sku": "1"}], evidence).query("7D", today="2026-08-29")
    assert result["status"] == "PERIOD_PROFIT_QUERY_READY"
    assert result["return_evidence"]["return_record_count"] == 2
    assert result["summary"]["returns_included"] is False
    assert result["coverage"]["missing_components"] == ["returns", "advertising", "storage"]
    assert result["executed"] is False


def test_return_evidence_failure_blocks_query_instead_of_hiding_missing_data():
    evidence = Returns({"error": True, "code": "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE"})
    result = PeriodProfitQueryService(Summary(), lambda: [{"sku": "1"}], evidence).query("7D", today="2026-08-29")
    assert result["code"] == "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE"
