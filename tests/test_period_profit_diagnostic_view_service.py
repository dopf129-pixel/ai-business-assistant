from services.period_profit_diagnostic_view_service import (
    PeriodProfitDiagnosticViewService,
)


def test_diagnostic_view_reports_only_confirmed_codes_and_bounded_counters():
    service = PeriodProfitDiagnosticViewService()
    completeness = {
        "error": False,
        "diagnostic_statuses": {
            "cost": "UNKNOWN",
            "external_expenses": "PARTIAL",
            "source_freshness": "STALE",
            "private": "SECRET",
        },
        "diagnostic_reason_codes": [
            "SOURCE_STALE",
            "COST_MISSING",
            "DROP_THIS",
        ],
        "actions": ["cost", "external_expenses", "unknown"],
    }
    operation = {
        "operation_id": "a" * 32,
        "operation_type": "telegram_callback",
        "started_at_utc": "2026-10-17T00:00:00Z",
        "elapsed_seconds": 30,
        "stage_code": "posting_identity_probe",
        "events_total": 300,
        "events_dropped": 44,
        "http_attempts": 12,
        "http_attempt_cap": 20,
        "rows_attempted": 8,
        "rows_completed": 6,
        "rows_unknown": 2,
        "budget_reason_code": "NONE",
        "finance_sku": "secret-sku",
        "amount": 9876.54,
        "nested": {"api_key": "secret"},
    }

    result = service.build("2026-08-01", "2026-08-31", completeness, operation)

    assert result["status"] == "PERIOD_PROFIT_DIAGNOSTICS_READY"
    assert result["reason_codes"] == [
        "SOURCE_STALE",
        "COST_MISSING",
        "PARTIAL_COVERAGE",
    ]
    assert result["actions"] == ["cost", "external_expenses", "refresh"]
    assert result["operation"]["http_attempts"] == 12
    assert result["operation"]["events_dropped"] == 44
    assert "secret-sku" not in result["text"]
    assert "9876.54" not in result["text"]
    assert "api_key" not in repr(result)
    assert "DROP_THIS" not in repr(result)
    assert "PRIVATE" not in repr(result)


def test_diagnostic_view_marks_budget_exhaustion_and_offers_explicit_refresh():
    result = PeriodProfitDiagnosticViewService().build(
        "2026-08-01",
        "2026-08-31",
        {
            "error": False,
            "diagnostic_statuses": {},
            "diagnostic_reason_codes": [],
            "actions": [],
        },
        {
            "budget_reason_code": "HTTP_ATTEMPT_BUDGET_EXHAUSTED",
        },
    )

    assert result["reason_codes"] == ["HTTP_ATTEMPT_BUDGET_EXHAUSTED"]
    assert result["actions"] == ["refresh"]
    assert "достигнут лимит запросов" in result["text"]


def test_diagnostic_view_rejects_wrong_period_and_unknown_reason_fields():
    service = PeriodProfitDiagnosticViewService()

    unavailable = service.build(
        "2026-08-32",
        "2026-08-31",
        {"error": False},
    )
    safe = service.build(
        "2026-08-01",
        "2026-08-31",
        {
            "error": False,
            "diagnostic_statuses": {"external_expenses": "SECRET"},
            "diagnostic_reason_codes": ["SECRET_API_KEY", "COST_MISSING"],
            "actions": ["secret"],
        },
        {
            "operation_id": "../../private-path",
            "started_at_utc": "authorization: secret",
            "http_attempts": -1,
            "budget_reason_code": "token=secret",
        },
    )

    assert unavailable["status"] == "PERIOD_PROFIT_DIAGNOSTICS_UNAVAILABLE"
    assert safe["reason_codes"] == ["COST_MISSING"]
    assert safe["source_completeness"] == {}
    assert safe["operation"]["operation_id"] == "unknown"
    assert safe["operation"]["started_at_utc"] == "unknown"
    assert safe["operation"]["http_attempts"] == 0
    assert safe["operation"]["budget_reason_code"] == "UNKNOWN"
