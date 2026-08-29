from period_profit_response import build_period_profit_response


def _summary():
    return {"error": False, "status": "PERIOD_PROFIT_SUMMARY_READY", "date_from": "2026-08-01", "date_to": "2026-08-07", "revenue": 1000, "net_accrual": 800, "product_cost": 300, "tax": 60, "profit": 440, "margin_percent": 44, "returns_included": False, "advertising_included": False, "storage_included": False, "profit_scope": "V1"}


def test_reports_observed_returns_without_claiming_financial_impact():
    evidence = {"status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY", "returns_observed": True, "return_record_count": 3}
    text = build_period_profit_response(_summary(), return_evidence=evidence)["text"]
    assert "Ozon зафиксировал возвраты за период: 3" in text
    assert "денежное влияние пока не включено" in text
    assert "возвраты" in text


def test_reports_no_return_records_without_marking_returns_included():
    evidence = {"status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY", "returns_observed": False, "return_record_count": 0}
    text = build_period_profit_response(_summary(), return_evidence=evidence)["text"]
    assert "не вернул записей о возвратах" in text
    assert "не доказывает отсутствие всех возвратных расходов" in text
    assert "пока не включены полностью: возвраты" in text
