from services.period_profit_return_evidence_service import PeriodProfitReturnEvidenceService


class Ozon:
    def __init__(self, response): self.response = response; self.calls = []
    def get_returns(self, **kwargs): self.calls.append(kwargs); return self.response


def test_loads_return_records_without_financial_inference():
    ozon = Ozon({"returns": [{"id": 1, "offer_id": "a", "status": "returned", "quantity": 1, "amount": 999}]})
    result = PeriodProfitReturnEvidenceService(ozon).load("2026-08-01", "2026-08-07", offer_id="a")
    assert result["status"] == "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
    assert result["return_record_count"] == 1
    assert result["returns_observed"] is True
    assert result["records"][0]["source"] == "OZON_RETURNS_API"
    assert "amount" not in result["records"][0]
    assert result["financial_impact_supported"] is False
    assert result["returns_profit_adjustment_allowed"] is False
    assert result["executed"] is False


def test_empty_success_is_valid_evidence_with_no_observed_returns():
    result = PeriodProfitReturnEvidenceService(Ozon({"items": []})).load("2026-08-01", "2026-08-07")
    assert result["returns_observed"] is False
    assert result["return_record_count"] == 0


def test_api_failure_blocks():
    result = PeriodProfitReturnEvidenceService(Ozon({"error": True, "message": "fail"})).load("2026-08-01", "2026-08-07")
    assert result["code"] == "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE"
    assert result["executed"] is False
