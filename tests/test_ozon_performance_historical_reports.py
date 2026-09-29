from decimal import Decimal
from unittest.mock import patch

import pytest

from api.ozon_performance_historical_reports import (
    HistoricalPerformanceReports, HistoricalReportError, parse_report_csv,
)
from services.period_profit_sku_advertising_service import PeriodProfitSkuAdvertisingService


def test_cpc_and_cpo_columns_do_not_double_count():
    cpc = ("Кампания;123\nSKU;Название товара;Расход, Р, с НДС;Клики\n"
           "3921245627;Test;12,50;3\nВсего;;12,50;3\n").encode()
    cpo = ("SKU;Расход, ₽;Расход (Оплата за клик), ₽\n"
           "3921245627;7,25;12,50\n").encode()
    assert parse_report_csv(cpc, "CPC")[0]["expense"] == Decimal("12.50")
    assert parse_report_csv(cpo, "CPO")[0]["expense"] == Decimal("7.25")


def test_unknown_columns_fail_closed():
    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(b"sku;revenue\n123;200\n", "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_HEADER_NOT_FOUND"


def test_cpc_summary_row_with_b_cero_marker_is_accepted_when_zero():
    report = (
        "sku;Название товара;Расход, Р, с НДС;Клики\n"
        "Bcero;;0;0\n"
    ).encode()

    assert parse_report_csv(report, "CPC") == []


def test_positive_campaign_total_without_sku_rows_stays_fail_closed():
    report = "SKU;Расход, Р, с НДС\nBcero;12,50\n".encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_SUMMARY_WITHOUT_SKU"


def test_missing_campaign_total_without_sku_rows_stays_fail_closed():
    report = "SKU;Расход, Р, с НДС\nBcero;\n".encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_SUMMARY_WITHOUT_SKU"


def test_unknown_row_label_fails_with_safe_format_stage():
    report = "SKU;Расход\nПримечание;0\n".encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_UNKNOWN_ROW_LABEL"


def test_load_returns_report_format_stage():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda: ["123"]

    def invalid_report(*_args):
        raise HistoricalReportError(
            "OZON_HISTORICAL_REPORT_FORMAT",
            report_format_stage="CSV_HEADER_NOT_FOUND",
        )

    service._generate = invalid_report
    result = service.load("2026-08-01", "2026-08-30")

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_stage"] == "CSV_HEADER_NOT_FOUND"


class _Client:
    def __init__(self, campaigns=None):
        self._token = {"access_token": "token"}
        self.campaigns = campaigns or [
            {"id": "123", "paymentType": "CPC"},
            {"id": "456", "paymentType": "CPM"},
            {"id": "789", "paymentType": "CPO"},
        ]

    def _access_token(self, force=False):
        return self._token

    def _request(self, method, endpoint, token, **kwargs):
        assert method == "get"
        assert endpoint == "/api/client/campaign"
        assert token == "token"
        assert kwargs["params"]["advObjectType"] == "SKU"
        return {"list": self.campaigns}


def test_campaign_list_skips_known_out_of_scope_payment_types():
    service = HistoricalPerformanceReports(_Client())
    assert service._campaign_ids() == ["123"]


def test_campaign_list_uses_sku_filter_when_payment_type_is_missing():
    service = HistoricalPerformanceReports(_Client([
        {"id": "42104957", "advObjectType": "SKU"},
        # advObjectType is optional in some campaign responses. The request
        # itself is filtered to SKU, so an omitted field still has that scope.
        {"id": "42104958"},
    ]))

    assert service._campaign_ids() == ["42104957", "42104958"]


def test_campaign_list_rejects_conflicting_scope_when_payment_type_is_missing():
    service = HistoricalPerformanceReports(_Client([
        {"id": "123", "advObjectType": "BANNER"},
    ]))

    with pytest.raises(HistoricalReportError) as exc:
        service._campaign_ids()

    assert exc.value.code == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert exc.value.campaign_payment_type == "MISSING"


def test_campaign_list_fails_closed_for_unrecognized_payment_types():
    service = HistoricalPerformanceReports(_Client([
        {"id": "123", "paymentType": "NEW_TYPE"},
    ]))
    with pytest.raises(HistoricalReportError) as exc:
        service._campaign_ids()
    assert exc.value.code == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert exc.value.campaign_payment_type == "NEW_TYPE"
    assert exc.value.campaign_id == "123"


def test_historical_campaign_error_returns_payment_type_diagnostic():
    service = HistoricalPerformanceReports(_Client([
        {"id": "123", "paymentType": "CAMPAIGN_TYPE_INVALID"},
    ]))

    result = service.load("2026-08-01", "2026-08-30")

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert result["campaign_payment_type"] == "CAMPAIGN_TYPE_INVALID"
    assert result["campaign_id"] == "123"


def test_historical_campaign_diagnostic_sanitizes_unexpected_values():
    assert HistoricalPerformanceReports._safe_campaign_payment_type(None) == "MISSING"
    assert HistoricalPerformanceReports._safe_campaign_payment_type(
        "private token=do-not-show"
    ) == "UNRECOGNIZED_VALUE"


def test_historical_requests_all_windows_and_types_without_manual_files():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda: ["123"]
    seen = []

    def generate(endpoint, payload, kind):
        seen.append((endpoint, payload, kind))
        return [{"sku": "3921245627", "expense": Decimal("1"), "kind": kind}]

    service._generate = generate
    result = service.load("2026-05-03", "2026-09-23")
    assert "error" not in result
    assert len([s for s in seen if s[2] == "CPC"]) == 3
    assert len([s for s in seen if s[2] == "CPO"]) == 3
    assert len(result["rows"]) == 6


def test_historical_failure_never_becomes_zero():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda: ["123"]
    def failed(*_args):
        raise HistoricalReportError("OZON_HISTORICAL_REPORT_FAILED")
    service._generate = failed
    assert service.load("2026-05-03", "2026-09-23")["error"] is True
