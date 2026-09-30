from datetime import date
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
    cpo = ("SKU;SKU продвигаемого товара;Расход, ₽;Расход (Оплата за клик), ₽\n"
           "1234567890;3921245627;7,25;12,50\n").encode()
    assert parse_report_csv(cpc, "CPC")[0]["expense"] == Decimal("12.50")
    cpo_row = parse_report_csv(cpo, "CPO")[0]
    assert cpo_row["sku"] == "3921245627"
    assert cpo_row["expense"] == Decimal("7.25")


def test_cpo_product_settings_without_expense_are_not_a_spend_report():
    report = (
        "SKU;Артикул;Название товара;Категория товара;Продвижение;"
        "Предельная цена;Ставка, %;Ставка, ₽;Последнее изменение\n"
        "1234567890;ARTICLE;Product;Category;Enabled;100;5;10;2026-08-01\n"
    ).encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPO")

    assert exc.value.report_format_stage == "CSV_HEADER_NOT_FOUND"
    assert exc.value.report_format_kind == "CPO"
    assert "Ставка, ₽" in exc.value.report_format_columns
    assert "расход" not in " ".join(exc.value.report_format_columns).lower()


def test_unknown_columns_fail_closed():
    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(b"sku;revenue\n123;200\n", "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_HEADER_NOT_FOUND"


def test_cpc_expense_column_with_ruble_symbol_and_vat_is_supported():
    report = (
        "SKU;Название товара;Расход, ₽, с НДС\n"
        "3921245627;Test;12,50\n"
    ).encode()

    rows = parse_report_csv(report, "CPC")

    assert rows == [{"sku": "3921245627", "expense": Decimal("12.50"), "kind": "CPC"}]


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


def test_repeated_full_header_row_is_skipped():
    report = (
        "SKU продвигаемого товара;Название товара;Расход, ₽\n"
        "SKU продвигаемого товара;Название товара;Расход, ₽\n"
        "3921245627;Test;7,25\n"
    ).encode()

    assert parse_report_csv(report, "CPO") == [
        {"sku": "3921245627", "expense": Decimal("7.25"), "kind": "CPO"},
    ]


def test_unknown_row_label_fails_with_safe_format_context():
    report = "SKU;Расход\nПримечание;0\n".encode()

    with pytest.raises(HistoricalReportError) as exc:
        parse_report_csv(report, "CPC")

    assert exc.value.code == "OZON_HISTORICAL_REPORT_FORMAT"
    assert exc.value.report_format_stage == "CSV_UNKNOWN_ROW_LABEL"
    assert exc.value.report_format_kind == "CPC"
    assert exc.value.report_format_columns == ["SKU", "Расход"]
    assert "Примечание" not in str(exc.value.report_format_columns)


def test_load_returns_report_format_stage():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda *_args: ["123"]

    def invalid_report(*_args):
        raise HistoricalReportError(
            "OZON_HISTORICAL_REPORT_FORMAT",
            report_format_stage="CSV_UNKNOWN_ROW_LABEL",
            report_format_columns=["SKU продвигаемого товара", "Расход, ₽"],
            report_format_kind="CPO",
        )

    service._generate = invalid_report
    result = service.load("2026-08-01", "2026-08-30")

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_stage"] == "CSV_UNKNOWN_ROW_LABEL"
    assert result["report_format_columns"] == ["SKU продвигаемого товара", "Расход, ₽"]
    assert result["report_format_kind"] == "CPO"


class _Client:
    def __init__(self, campaigns=None):
        self._token = {"access_token": "token"}
        self.campaigns = campaigns or [
            {"id": "123", "paymentType": "CPC", "advObjectType": "SKU"},
            {"id": "456", "paymentType": "CPM", "advObjectType": "BANNER"},
            {"id": "789", "paymentType": "CPO", "advObjectType": "SKU"},
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

    def __init__(self, states, create_method="post",
                 create_endpoint="/api/client/statistics", download_content=None):
        self.states = list(states)
        self.create_method = create_method
        self.create_endpoint = create_endpoint
        self.create_kwargs = None
        self.download_content = download_content or (
            "SKU;Название;Расход, Р, с НДС\n3921245627;Test;1,25\n".encode()
        )
        self.poll_calls = 0
        self.session = SimpleNamespace(get=self._download)

    def _access_token(self, force=False):
        return {"access_token": "token"}

    def _request(self, method, endpoint, token, **kwargs):
        assert token == "token"
        if endpoint == self.create_endpoint:
            assert method == self.create_method
            self.create_kwargs = kwargs
            return {"UUID": "00000000-0000-0000-0000-000000000000"}
        assert method == "get"
        assert endpoint == "/api/client/statistics/00000000-0000-0000-0000-000000000000"
        self.poll_calls += 1
        return self.states[min(self.poll_calls - 1, len(self.states) - 1)]

    def _download(self, *_args, **_kwargs):
        return SimpleNamespace(
            status_code=200,
            content=self.download_content,
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


def test_all_sku_cpo_orders_report_uses_time_bounds_query_and_promoted_sku():
    content = (
        "Дата;ID заказа;SKU;SKU продвигаемого товара;Артикул;Расход, ₽\n"
        "2026-08-01;order-1;1234567890;3921245627;ARTICLE;7,25\n"
    ).encode()
    endpoint = "/api/client/statistics/all_sku_promo/orders/generate"
    client = _AsyncReportClient(
        [{"state": "OK", "link": "https://report.test/file.csv"}],
        create_method="get", create_endpoint=endpoint, download_content=content,
    )
    service = HistoricalPerformanceReports(client)
    params = {
        "timeBounds.from": "2026-08-01T00:00:00Z",
        "timeBounds.to": "2026-08-30T23:59:59Z",
    }

    rows = service._generate(
        endpoint, params, "CPO", method="get", query_params=True
    )

    assert client.create_kwargs == {"params": params}
    assert rows == [{"sku": "3921245627", "expense": Decimal("7.25"), "kind": "CPO"}]


def test_campaign_list_skips_known_out_of_scope_payment_types():
    service = HistoricalPerformanceReports(_Client())
    assert service._campaign_ids() == ["123"]


@pytest.mark.parametrize("campaign_dates", [
    {"fromDate": "2026-08-31"},
    {"createdAt": "2026-08-31T00:00:00Z"},
    {"toDate": "2026-07-31"},
])
def test_campaign_list_skips_campaigns_outside_requested_period(campaign_dates):
    service = HistoricalPerformanceReports(_Client([{
        "id": "42104957", "advObjectType": "SKU", **campaign_dates,
    }]))

    assert service._campaign_ids(date(2026, 8, 1), date(2026, 8, 30)) == []


def test_load_ignores_later_campaign_with_missing_payment_type():
    service = HistoricalPerformanceReports(_Client([{
        "id": "42104957", "advObjectType": "SKU",
        "fromDate": "2026-09-01", "createdAt": "2026-09-01T00:00:00Z",
    }]))
    generated = []
    service._generate = lambda endpoint, *_args, **_kwargs: generated.append(endpoint) or []

    result = service.load("2026-08-01", "2026-08-30")

    assert "error" not in result
    assert generated == [
        "/api/client/statistic/orders/generate",
        "/api/client/statistics/all_sku_promo/orders/generate",
    ]


def test_missing_payment_type_still_fails_when_campaign_overlaps_period():
    service = HistoricalPerformanceReports(_Client([{
        "id": "42104957", "advObjectType": "SKU",
        "fromDate": "2026-08-30", "createdAt": "2026-08-01T00:00:00Z",
    }]))

    with pytest.raises(HistoricalReportError) as exc:
        service._campaign_ids(date(2026, 8, 1), date(2026, 8, 30))

    assert exc.value.code == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert exc.value.campaign_id == "42104957"


@pytest.mark.parametrize("campaign", [
    {"id": "42104957", "advObjectType": "SKU"},
    # Some responses omit advObjectType too; neither missing field identifies
    # the payment model.
    {"id": "42104958"},
])
def test_campaign_list_fails_closed_when_payment_type_is_missing(campaign):
    service = HistoricalPerformanceReports(_Client([campaign]))

    with pytest.raises(HistoricalReportError) as exc:
        service._campaign_ids()

    assert exc.value.code == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert exc.value.campaign_payment_type == "MISSING"
    assert exc.value.campaign_id == campaign["id"]


def test_campaign_list_ignores_cpo_sku_campaigns_for_cpc_report():
    service = HistoricalPerformanceReports(_Client([
        {"id": "123", "paymentType": "CPO", "advObjectType": "SKU"},
    ]))

    assert service._campaign_ids() == []


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
        {"id": "42104957", "advObjectType": "SKU"},
    ]))

    result = service.load("2026-08-01", "2026-08-30")

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert result["campaign_payment_type"] == "MISSING"
    assert result["campaign_id"] == "42104957"


def test_historical_campaign_diagnostic_sanitizes_unexpected_values():
    assert HistoricalPerformanceReports._safe_campaign_payment_type(None) == "MISSING"
    assert HistoricalPerformanceReports._safe_campaign_payment_type(
        "private token=do-not-show"
    ) == "UNRECOGNIZED_VALUE"


class _DependencyUnavailableClient:
    def __init__(self, failed_stage):
        self.failed_stage = failed_stage
        self.calls = 0

    def _access_token(self, force=False):
        return {"access_token": "token"}

    def _request(self, method, endpoint, token, **kwargs):
        self.calls += 1
        assert token == "token"
        if endpoint == "/api/client/campaign":
            if self.failed_stage == "CAMPAIGN_LIST":
                return {"error": True,
                        "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                        "dependency_error_type": "TIMEOUT"}
            return {"list": [{"id": "123", "paymentType": "CPC"}]}
        if endpoint in HistoricalPerformanceReports.REPORT_DEPENDENCY_PREFIXES:
            prefix = HistoricalPerformanceReports.REPORT_DEPENDENCY_PREFIXES[endpoint]
            if self.failed_stage == prefix + "_CREATE":
                return {"error": True,
                        "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                        "dependency_error_type": "TIMEOUT"}
            return {"UUID": "00000000-0000-0000-0000-000000000000"}
        if endpoint.startswith("/api/client/statistics/"):
            if self.failed_stage.endswith("_STATUS"):
                return {"error": True,
                        "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                        "dependency_error_type": "TIMEOUT"}
            return {"state": "OK", "link": "https://report.test/file.csv"}
        raise AssertionError("unexpected endpoint")


def test_campaign_list_dependency_failure_returns_safe_stage():
    client = _DependencyUnavailableClient("CAMPAIGN_LIST")
    with patch("api.ozon_performance_historical_reports.time.sleep") as sleep:
        result = HistoricalPerformanceReports(client).load("2026-08-01", "2026-08-30")

    assert result["code"] == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"
    assert result["dependency_stage"] == "CAMPAIGN_LIST"
    assert result["dependency_error_type"] == "TIMEOUT"
    assert client.calls == 2
    sleep.assert_called_once_with(1)


@pytest.mark.parametrize(("endpoint", "kind", "expected_stage"), [
    ("/api/client/statistics", "CPC", "CPC_REPORT_CREATE"),
    ("/api/client/statistic/orders/generate", "CPO",
     "CPO_SELECTED_ORDERS_REPORT_CREATE"),
    ("/api/client/statistics/all_sku_promo/orders/generate", "CPO",
     "CPO_ALL_SKU_ORDERS_REPORT_CREATE"),
])
def test_report_creation_dependency_failure_returns_specific_stage(
    endpoint, kind, expected_stage,
):
    client = _DependencyUnavailableClient(expected_stage)
    service = HistoricalPerformanceReports(client)
    method = "get" if "all_sku_promo" in endpoint else "post"

    with pytest.raises(HistoricalReportError) as exc:
        service._generate(
            endpoint, {}, kind, method=method, query_params=method == "get"
        )

    assert exc.value.code == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"
    assert exc.value.dependency_stage == expected_stage
    assert exc.value.dependency_error_type == "TIMEOUT"
    # A report-create GET is not idempotent just because its HTTP verb is GET.
    assert client.calls == 1


@pytest.mark.parametrize(("endpoint", "kind", "expected_stage"), [
    ("/api/client/statistics", "CPC", "CPC_REPORT_STATUS"),
    ("/api/client/statistic/orders/generate", "CPO",
     "CPO_SELECTED_ORDERS_REPORT_STATUS"),
    ("/api/client/statistics/all_sku_promo/orders/generate", "CPO",
     "CPO_ALL_SKU_ORDERS_REPORT_STATUS"),
])
def test_report_status_dependency_failure_returns_specific_stage(
    endpoint, kind, expected_stage,
):
    client = _DependencyUnavailableClient(expected_stage)
    service = HistoricalPerformanceReports(client)
    method = "get" if "all_sku_promo" in endpoint else "post"

    with patch("api.ozon_performance_historical_reports.time.sleep") as sleep:
        with pytest.raises(HistoricalReportError) as exc:
            service._generate(
                endpoint, {}, kind, method=method, query_params=method == "get"
            )

    assert exc.value.code == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"
    assert exc.value.dependency_stage == expected_stage
    assert exc.value.dependency_error_type == "TIMEOUT"
    assert client.calls == 3  # create, failed poll, retried poll
    sleep.assert_called_once_with(1)


def test_get_dependency_failure_retries_once_and_recovers():
    class _RecoveringClient:
        def __init__(self):
            self.calls = 0

        def _access_token(self, force=False):
            return {"access_token": "token"}

        def _request(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"error": True,
                        "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                        "dependency_error_type": "TIMEOUT"}
            return {"state": "IN_PROGRESS"}

    client = _RecoveringClient()
    service = HistoricalPerformanceReports(client)
    with patch("api.ozon_performance_historical_reports.time.sleep") as sleep:
        result = service._json(
            "get", "/api/client/statistics/00000000-0000-0000-0000-000000000000",
            dependency_stage="CPO_SELECTED_ORDERS_REPORT_STATUS",
        )

    assert result == {"state": "IN_PROGRESS"}
    assert client.calls == 2
    sleep.assert_called_once_with(1)


def test_post_dependency_failure_is_not_retried():
    class _UnavailableClient:
        def __init__(self):
            self.calls = 0

        def _access_token(self, force=False):
            return {"access_token": "token"}

        def _request(self, *_args, **_kwargs):
            self.calls += 1
            return {"error": True,
                    "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                    "dependency_error_type": "TIMEOUT"}

    client = _UnavailableClient()
    service = HistoricalPerformanceReports(client)
    with pytest.raises(HistoricalReportError) as exc:
        service._json(
            "post", "/api/client/statistic/orders/generate",
            dependency_stage="CPO_SELECTED_ORDERS_REPORT_CREATE",
            json={},
        )

    assert client.calls == 1
    assert exc.value.dependency_error_type == "TIMEOUT"


def test_historical_requests_all_windows_and_types_without_manual_files():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda *_args: ["123"]
    seen = []

    def generate(endpoint, payload, kind, **kwargs):
        seen.append((endpoint, payload, kind, kwargs))
        return [{"sku": "3921245627", "expense": Decimal("1"), "kind": kind}]

    service._generate = generate
    result = service.load("2026-05-03", "2026-09-23")
    assert "error" not in result
    assert len([s for s in seen if s[2] == "CPC"]) == 3
    selected_cpo = [s for s in seen if s[0] == "/api/client/statistic/orders/generate"]
    all_products_cpo = [
        s for s in seen
        if s[0] == "/api/client/statistics/all_sku_promo/orders/generate"
    ]
    assert len(selected_cpo) == 3
    assert len(all_products_cpo) == 3
    assert all(call[3] == {} for call in selected_cpo)
    assert all("from" in call[1] and "to" in call[1] for call in selected_cpo)
    assert all(call[3] == {"method": "get", "query_params": True}
               for call in all_products_cpo)
    assert all("timeBounds.from" in call[1] and "timeBounds.to" in call[1]
               for call in all_products_cpo)
    assert len(result["rows"]) == 9


def test_historical_failure_never_becomes_zero():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda *_args: ["123"]
    def failed(*_args):
        raise HistoricalReportError("OZON_HISTORICAL_REPORT_FAILED")
    service._generate = failed
    assert service.load("2026-05-03", "2026-09-23")["error"] is True
