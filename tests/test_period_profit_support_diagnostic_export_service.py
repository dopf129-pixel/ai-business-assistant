import json
from datetime import datetime, timezone

from services.period_profit_support_diagnostic_export_service import (
    PeriodProfitSupportDiagnosticExportService,
)


def _diagnostic():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_DIAGNOSTICS_READY",
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "reason_codes": ["PARTIAL_COVERAGE", "TIME_BUDGET_EXHAUSTED"],
        "source_completeness": {
            "financial_base": "CONFIRMED",
            "sku_quantity": "PARTIAL",
            "unknown_field": "secret-status",
        },
        "operation": {
            "operation_id": "a" * 32,
            "operation_type": "secret.operation.type",
            "started_at_utc": "2026-08-31T12:00:00Z",
            "stage_code": "Bearer.secret-stage",
            "budget_reason_code": "TIME_BUDGET_EXHAUSTED",
            "events_total": 700,
            "events_dropped": 444,
            "http_attempts": 1200,
            "http_attempt_cap": 300,
            "rows_attempted": 14,
            "rows_completed": 11,
            "rows_unknown": 3,
            "elapsed_seconds": 600,
            "events": [{"endpoint": "https://api/?token=never-export"}],
        },
        "amounts": {"profit": "999999.99"},
        "exception": "secret exception text",
        "label": "sk-live-support-label",
    }


def _context():
    return {
        "operation_id": "b" * 32,
        "operation_type": "https://api/?Client-Id=private",
        "started_at_utc": "2026-08-31T12:00:00+03:00",
        "budget_reason_code": "TIME_BUDGET_EXHAUSTED",
        "_identifier_values": [
            {"field": "finance_sku", "kind": "SKU", "value": "private-sku-1"},
            {"field": "catalog_sku", "kind": "SKU", "value": "private-sku-1"},
            {"field": "product_id", "kind": "PRODUCT", "value": "private-product"},
        ],
        "telegram_user_id": "505204945",
        "store_tenant": "store-secret",
        "headers": {"Authorization": "Bearer abc"},
        "raw_response": [{"nested": "private-response"}],
        "exception": "private traceback",
        "endpoint": "https://seller-api/?Client-Id=123",
        "filename": "C:/private/path.json",
        "label": "sk-live-context-label",
        "money": 123456.78,
    }


def test_support_diagnostic_export_is_allowlisted_and_masks_repeated_identifiers():
    service = PeriodProfitSupportDiagnosticExportService(
        utc_clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)
    )
    built = service.build_snapshot(_diagnostic(), _context())

    assert built["error"] is False
    snapshot = built["snapshot"]
    assert snapshot["operation"]["id"] == "b" * 32
    assert snapshot["operation"]["type"] == "PERIOD_PROFIT"
    assert snapshot["operation"]["started_at_utc"] == "2026-08-31T09:00:00Z"
    assert snapshot["counts"] == {
        "events_total": 700,
        "events_dropped": 444,
        "http_attempts": 1200,
        "http_attempt_cap": 300,
        "rows_attempted": 14,
        "rows_completed": 11,
        "rows_unknown": 3,
        "elapsed_seconds": 600,
    }
    assert snapshot["identifier_references"] == {
        "finance_sku": "SKU_0001",
        "catalog_sku": "SKU_0001",
        "product_id": "PRODUCT_0001",
    }
    assert snapshot["source_completeness"] == {
        "financial_base": "CONFIRMED",
        "sku_quantity": "PARTIAL",
    }
    assert set(snapshot) == {
        "schema", "schema_version", "application", "operation", "period",
        "status_codes", "reason_codes", "source_completeness", "counts",
        "identifier_references", "field_types",
    }

    exported = service.export(snapshot, {"revision": "1a2b3c4", "started_at_utc": "invalid"})
    assert exported["error"] is False
    assert exported["document_kind"] == "support_diagnostic"
    assert exported["filename"] == "period_profit_support_diagnostic.json"
    document = json.loads(exported["file_content"].decode("utf-8"))
    serialized = exported["file_content"].decode("utf-8")
    assert document["application"] == {
        "revision": "1a2b3c4",
        "started_at_utc": None,
    }
    for secret in (
        "private-sku-1", "private-product", "505204945", "store-secret",
        "abc", "private-response", "private traceback", "Client-Id",
        "never-export", "999999.99", "123456.78", "private/path",
        "sk-live-support-label", "sk-live-context-label",
    ):
        assert secret not in serialized


def test_support_export_rejects_invalid_period_and_defaults_malicious_values():
    service = PeriodProfitSupportDiagnosticExportService(
        utc_clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)
    )
    invalid = service.build_snapshot(
        {**_diagnostic(), "date_from": "2026-09-01", "date_to": "2026-08-01"},
        _context(),
    )
    assert invalid["error"] is True

    hostile = _diagnostic()
    hostile["status"] = []
    assert service.build_snapshot(hostile, _context())["code"] == (
        "PERIOD_PROFIT_SUPPORT_DIAGNOSTIC_UNAVAILABLE"
    )

    malformed = _diagnostic()
    malformed["operation"]["budget_reason_code"] = {"token": "do-not-export"}
    malformed["source_completeness"]["financial_base"] = ["secret"]
    malformed_context = _context()
    malformed_context["budget_reason_code"] = ["secret"]
    malformed_context["_identifier_values"] = [
        {"field": ["secret"], "kind": "SKU", "value": "leak"},
        {"field": "finance_sku", "kind": "SKU", "value": "leak"},
        {"field": "posting_number", "kind": "POSTING", "value": "not-allowed"},
    ]
    built = service.build_snapshot(malformed, malformed_context)
    assert built["error"] is False
    assert built["snapshot"]["status_codes"]["budget_reason"] == "NONE"
    assert built["snapshot"]["source_completeness"] == {
        "sku_quantity": "PARTIAL",
    }
    assert built["snapshot"]["identifier_references"] == {
        "finance_sku": "SKU_0001",
    }


def test_export_reconstructs_strict_shape_and_drops_unknown_nested_payloads():
    service = PeriodProfitSupportDiagnosticExportService(
        utc_clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)
    )
    snapshot = service.build_snapshot(_diagnostic(), _context())["snapshot"]
    snapshot["unknown"] = {
        "deep": [{"Authorization": "secret-header", "amount": 99.5}]
    }
    snapshot["counts"]["unknown"] = "secret-count"
    snapshot["operation"]["endpoint"] = "https://secret-endpoint"
    result = service.export(snapshot, {"revision": "not-a-git-sha", "nested": {"secret": "x"}})

    assert result["error"] is False
    payload = result["file_content"].decode("utf-8")
    parsed = json.loads(payload)
    assert "unknown" not in parsed
    assert "endpoint" not in parsed["operation"]
    assert "Authorization" not in payload
    assert "secret-endpoint" not in payload
    assert parsed["application"]["revision"] == "UNAVAILABLE"
    assert "unknown" not in parsed["counts"]
