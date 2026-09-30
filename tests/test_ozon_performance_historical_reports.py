from decimal import Decimal
from types import SimpleNamespace
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


def test_unknown_header_reports_safe_column_names_without_data_rows():
    report = (
        "Кампания № 42104957, период 01.08.2026-30.08.2026\n"
        "SKU товара;Расходы на продвижение, ₽;Выручка, ₽\n"
        "3921245627;12,50;100,00\n"
    ).encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPC")

    assert exc.value.report_format_stage == "CSV_HEADER_NOT_FOUND"
    assert exc.value.report_format_kind == "CPC"
    assert exc.value.report_format_columns == [
        "SKU товара", "Расходы на продвижение, ₽", "Выручка, ₽",
    ]
    assert "3921245627" not in str(exc.value.report_format_columns)
    assert "12,50" not in str(exc.value.report_format_columns)


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
            report_format_columns=["SKU товара", "Сумма расходов"],
            report_format_kind="CPO",
        )

    service._generate = invalid_report
    result = service.load("2026-08-01", "2026-08-30")

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_stage"] == "CSV_HEADER_NOT_FOUND"
    assert result["report_format_columns"] == ["SKU товара", "Сумма расходов"]
    assert result["report_format_kind"] == "CPO"


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


class _AsyncReportClient:
    BASE_URL = "https://performance.test"

    def __init__(self, states):
        self.states = list(states)
        self.poll_calls = 0
        self.session = SimpleNamespace(get=self._download)

    def _access_token(self, force=False):
        return {"access_token": "token"}

    def _request(self, method, endpoint, token, **kwargs):
        assert token == "token"
        if method == "post":
            assert endpoint == "/api/client/statistics"
            return {"UUID": "00000000-0000-0000-0000-000000000000"}
        assert method == "get"
        assert endpoint == "/api/client/statistics/00000000-0000-0000-0000-000000000000"
        self.poll_calls += 1
        return self.states[min(self.poll_calls - 1, len(self.states) - 1)]

    @staticmethod
    def _download(*_args, **_kwargs):
        return SimpleNamespace(
            status_code=200,
            content="SKU;Название;Расход, Р, с НДС\n3921245627;Test;1,25\n".encode(),
        )


def test_async_report_polling_waits_past_previous_timeout_limit():
    client = _AsyncReportClient(
        [{"state": "IN_PROGRESS"}] * 12
        + [{"state": "OK", "link": "https://report.test/file.csv"}]
    )
    service = HistoricalPerformanceReports(client)

    with patch("api.ozon_performance_historical_reports.time.sleep") as sleep:
        rows = service._generate(
            "/api/client/statistics", {"campaigns": ["123"]}, "CPC"
        )

    assert rows[0]["sku"] == "3921245627"
    assert rows[0]["expense"] == Decimal("1.25")
    assert client.poll_calls == 13
    assert sleep.call_count == 12
    sleep.assert_called_with(5)


def test_async_report_polling_still_times_out_at_the_bounded_limit():
    client = _AsyncReportClient([{"state": "IN_PROGRESS"}])
    service = HistoricalPerformanceReports(client)

    with patch("api.ozon_performance_historical_reports.time.sleep") as sleep:
        with pytest.raises(HistoricalReportError) as exc:
            service._generate(
                "/api/client/statistics", {"campaigns": ["123"]}, "CPC"
            )

    assert exc.value.code == "OZON_HISTORICAL_REPORT_TIMEOUT"
    assert client.poll_calls == HistoricalPerformanceReports.MAX_POLLS
    assert sleep.call_count == HistoricalPerformanceReports.MAX_POLLS - 1


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
