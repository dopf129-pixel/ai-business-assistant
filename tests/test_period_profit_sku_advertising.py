import pytest
from datetime import date, timedelta
from types import SimpleNamespace

from api.ozon_performance_historical_reports import HistoricalPerformanceReports
from services.period_profit_sku_advertising_service import PeriodProfitSkuAdvertisingService
from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService


class _Repository:
    def get_performance(self, tenant):
        return {"client_id": "performance-id", "client_secret": "secret"}


class _Client:
    calls = 0

    def __init__(self, client_id, client_secret):
        assert client_id == "performance-id"
        assert client_secret == "secret"

    def get_sku_expenses(self, date_from, date_to):
        type(self).calls += 1
        return {
            "rows": [
                {"campaignId": "c-1", "sku": "101", "expense": "125.50"},
                {"campaignId": "c-2", "sku": "999", "expense": "900"},
            ]
        }


class _HistoricalClient:
    def __init__(self, client_id, client_secret):
        assert client_id == "performance-id"
        assert client_secret == "secret"

    def _access_token(self, force=False):
        return {"access_token": "token"}

    def _request(self, method, endpoint, token, **kwargs):
        assert method == "get"
        if endpoint.endswith("/objects"):
            return {"list": []}
        assert endpoint == "/api/client/campaign"
        assert token == "token"
        return {"list": [{"id": "42104957"}]}


class _ReportChainClient:
    """Fake Ozon transport for campaign discovery through report CSV parsing."""

    BASE_URL = "https://performance.test"

    def __init__(self, client_id, client_secret):
        assert client_id == "performance-id"
        assert client_secret == "secret"
        self.created_reports = {}
        self.report_endpoints = []
        self.session = SimpleNamespace(get=self._download)

    def _access_token(self, force=False):
        return {"access_token": "token"}

    def _request(self, method, endpoint, token, **kwargs):
        assert token == "token"
        if endpoint == "/api/client/campaign":
            assert method == "get"
            assert kwargs["params"]["advObjectType"] == "SKU"
            return {"list": [
                {"id": "101", "paymentType": "CPC", "advObjectType": "SKU"},
                {"id": "202", "paymentType": "CPO", "advObjectType": "SKU"},
                # This campaign was created after the requested August
                # window. Its missing paymentType must not block that report.
                {"id": "42104957", "advObjectType": "SKU",
                 "fromDate": "2026-09-01",
                 "createdAt": "2026-09-01T00:00:00Z"},
            ]}
        if endpoint in HistoricalPerformanceReports.REPORT_DEPENDENCY_PREFIXES:
            self.report_endpoints.append((method, endpoint, kwargs))
            report_id = f"{len(self.report_endpoints):08d}-0000-0000-0000-000000000000"
            self.created_reports[report_id] = endpoint
            return {"UUID": report_id}
        if endpoint.startswith("/api/client/statistics/"):
            report_id = endpoint.rsplit("/", 1)[-1]
            assert report_id in self.created_reports
            return {"state": "OK", "link": "https://report.test/file.csv"}
        raise AssertionError(f"unexpected Ozon endpoint: {endpoint}")

    def _download(self, _url, params=None, **_kwargs):
        report_id = params["UUID"]
        endpoint = self.created_reports[report_id]
        reports = {
            "/api/client/statistics": (
                "SKU;Название товара;Расход, ₽, с НДС\n"
                "101;Target;5,00\n"
                "999;Other;90,00\n"
            ),
            "/api/client/statistic/orders/generate": (
                "Дата;ID заказа;SKU;SKU продвигаемого товара;Артикул;Расход, ₽\n"
                "2026-08-01;order-1;999;101;A;10,00\n"
            ),
            "/api/client/statistics/all_sku_promo/orders/generate": (
                "Дата;ID заказа;SKU;SKU продвигаемого товара;Артикул;Расход, ₽\n"
                "2026-08-02;order-2;999;101;A;20,00\n"
                "2026-08-02;order-3;999;999;B;80,00\n"
            ),
        }
        return SimpleNamespace(
            status_code=200,
            content=reports[endpoint].encode(),
        )


def test_selected_sku_advertising_is_one_batched_performance_call(monkeypatch):
    monkeypatch.setattr(
        "services.period_profit_sku_advertising_service.get_current_tenant_user_id",
        lambda: "user::ozon::store",
    )
    _Client.calls = 0
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_Client
    )

    result = service.load((date.today() - timedelta(days=1)).isoformat(),
                          date.today().isoformat(), {"101", "old-101"})

    assert result == {
        "error": False,
        "status": "PERIOD_PROFIT_SKU_ADVERTISING_READY",
        "configured": True,
        "complete": True,
        "scope": "OZON_PERFORMANCE_CPC_SKU",
        "expense": 125.5,
        "matched_row_count": 1,
        "campaign_count": 1,
        "external_call_count": 1,
    }
    assert _Client.calls == 1


def test_historical_cpc_and_cpo_report_chain_attributes_spend_to_selected_sku():
    client = _ReportChainClient("performance-id", "secret")
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=lambda *_args: client
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result == {
        "error": False,
        "status": "PERIOD_PROFIT_SKU_ADVERTISING_READY",
        "configured": True,
        "complete": True,
        "scope": "OZON_PERFORMANCE_CPC_AND_CPO_SKU",
        "expense": 35.0,
        "matched_row_count": 3,
        "campaign_count": 0,
        "external_call_count": 10,
    }
    assert [(method, endpoint) for method, endpoint, _ in client.report_endpoints] == [
        ("post", "/api/client/statistics"),
        ("post", "/api/client/statistic/orders/generate"),
        ("get", "/api/client/statistics/all_sku_promo/orders/generate"),
    ]
    assert client.report_endpoints[0][2]["json"] == {
        "campaigns": ["101"], "dateFrom": "2026-08-01", "dateTo": "2026-08-30",
    }
    assert client.report_endpoints[1][2]["json"] == {
        "from": "2026-08-01T00:00:00Z", "to": "2026-08-30T23:59:59Z",
    }
    assert client.report_endpoints[2][2]["params"] == {
        "timeBounds.from": "2026-08-01T00:00:00Z",
        "timeBounds.to": "2026-08-30T23:59:59Z",
    }


def test_historical_campaign_payment_type_survives_advertising_service():
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_HistoricalClient
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert result["campaign_payment_type"] == "MISSING"
    assert result["campaign_id"] == "42104957"
    assert result["campaign_diagnostics"][0]["lookup_status"] == "FOUND"


def test_historical_report_format_stage_survives_advertising_service(monkeypatch):
    monkeypatch.setattr(
        HistoricalPerformanceReports,
        "load",
        lambda *_args: {
            "error": True,
            "code": "OZON_HISTORICAL_REPORT_FORMAT",
            "report_format_stage": "CSV_UNKNOWN_ROW_LABEL",
            "report_format_columns": ["SKU продвигаемого товара", "Расход, ₽"],
            "report_format_row_label": "Примечание",
            "report_format_kind": "CPO",
        },
    )
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_HistoricalClient
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_stage"] == "CSV_UNKNOWN_ROW_LABEL"
    assert result["report_format_columns"] == ["SKU продвигаемого товара", "Расход, ₽"]
    assert result["report_format_kind"] == "CPO"
    assert result["report_format_row_label"] == "Примечание"


def test_historical_dependency_stage_survives_advertising_service(monkeypatch):
    monkeypatch.setattr(
        HistoricalPerformanceReports,
        "load",
        lambda *_args: {
            "error": True,
            "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
            "dependency_stage": "CPO_ALL_SKU_ORDERS_REPORT_CREATE",
            "dependency_error_type": "TIMEOUT",
        },
    )
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_HistoricalClient
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result["error"] is True
    assert result["code"] == "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"
    assert result["dependency_stage"] == "CPO_ALL_SKU_ORDERS_REPORT_CREATE"
    assert result["dependency_error_type"] == "TIMEOUT"


def test_runtime_shows_safe_historical_campaign_diagnostic():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                "campaign_payment_type": "MISSING",
                "campaign_id": "42104957",
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert result["error"] is True
    assert result["campaign_payment_type"] == "MISSING"
    assert result["campaign_id"] == "42104957"
    assert "paymentType: MISSING" in result["message"]
    assert "ID кампании: 42104957" in result["message"]
    assert "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN" in result["message"]


def test_runtime_omits_non_numeric_campaign_id_from_diagnostic():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                "campaign_payment_type": "MISSING",
                "campaign_id": "123\nsecret",
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert "ID кампании" not in result["message"]
    assert "secret" not in result["message"]


def test_runtime_shows_exact_campaign_lookup_and_safe_record_metadata():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                "campaign_payment_type": "MISSING",
                "campaign_id": "27107278",
                "campaign_unknown_count": 1,
                "campaign_diagnostics": [{
                    "campaign_id": "27107278",
                    "payment_type": "MISSING",
                    "adv_object_type": "SKU",
                    "state": "CAMPAIGN_STATE_FINISHED",
                    "from_date": "2026-08-01",
                    "to_date": "2026-08-30",
                    "created_at": "MISSING",
                    "lookup_status": "HTTP_400",
                }],
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert "lookup=HTTP_400" in result["message"]
    assert "state=CAMPAIGN_STATE_FINISHED" in result["message"]
    assert "fromDate=2026-08-01" in result["message"]


def test_runtime_preserves_safe_campaign_lookup_categories():
    diagnostics = PeriodProfitSkuRuntimeService._safe_historical_campaign_diagnostics([
        {"campaign_id": "1", "lookup_status": "HTTP_400"},
        {"campaign_id": "2", "lookup_status": "DEPENDENCY_TIMEOUT"},
        {"campaign_id": "3", "lookup_status": "HTTP_600"},
    ])

    assert [item["lookup_status"] for item in diagnostics] == [
        "HTTP_400", "DEPENDENCY_TIMEOUT", "UNAVAILABLE",
    ]


def test_runtime_filters_unsafe_campaign_metadata():
    assert PeriodProfitSkuRuntimeService._safe_historical_campaign_diagnostics([
        {
            "campaign_id": "27107278",
            "payment_type": "MISSING",
            "adv_object_type": "SKU\nTOKEN",
            "state": "campaign <private>",
            "from_date": ["not-a-date"],
            "to_date": "2026-08-30",
            "created_at": "MISSING",
            "lookup_status": "TOKEN=bad",
        },
        {"campaign_id": "id\ninjection"},
    ]) == [{
        "campaign_id": "27107278",
        "payment_type": "MISSING",
        "adv_object_type": "UNRECOGNIZED_VALUE",
        "state": "UNRECOGNIZED_VALUE",
        "from_date": "UNPARSEABLE",
        "to_date": "2026-08-30",
        "created_at": "MISSING",
        "lookup_status": "UNAVAILABLE",
    }]


def test_runtime_shows_safe_historical_report_format_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_REPORT_FORMAT",
                "report_format_stage": "CSV_UNKNOWN_ROW_LABEL",
                "report_format_kind": "CPO",
                "report_format_columns": ["SKU продвигаемого товара", "Расход, ₽"],
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert result["report_format_stage"] == "CSV_UNKNOWN_ROW_LABEL"
    assert "Этап: CSV_UNKNOWN_ROW_LABEL" in result["message"]
    assert "Тип отчёта: CPO" in result["message"]
    assert "Заголовки CSV: SKU продвигаемого товара; Расход, ₽" in result["message"]
    assert "OZON_HISTORICAL_REPORT_FORMAT" in result["message"]


def test_runtime_shows_safe_historical_dependency_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                "dependency_stage": "CPO_ALL_SKU_ORDERS_REPORT_CREATE",
                "dependency_error_type": "TIMEOUT",
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert result["error"] is True
    assert result["dependency_stage"] == "CPO_ALL_SKU_ORDERS_REPORT_CREATE"
    assert result["dependency_error_type"] == "TIMEOUT"
    assert "Этап запроса: CPO_ALL_SKU_ORDERS_REPORT_CREATE" in result["message"]
    assert "Тип сбоя: TIMEOUT" in result["message"]
    assert "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE" in result["message"]


def test_runtime_hides_unrecognized_historical_dependency_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE",
                "dependency_stage": "CPO_REPORT_CREATE\nsecret",
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert "dependency_stage" not in result
    assert "message" not in result
    assert "secret" not in str(result)


def test_runtime_filters_report_format_columns_to_safe_labels():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_REPORT_FORMAT",
                "report_format_stage": "CSV_HEADER_NOT_FOUND",
                "report_format_kind": "CPC",
                "report_format_columns": [
                    "SKU товара", "Расход, ₽", "3921245627",
                    "Итого: 12,50", "<script>alert(1)</script>",
                ],
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert "Заголовки CSV: SKU товара; Расход, ₽" in result["message"]
    assert "3921245627" not in result["message"]
    assert "12,50" not in result["message"]
    assert "<script>" not in result["message"]


def test_runtime_hides_unrecognized_report_format_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_REPORT_FORMAT",
                "report_format_stage": "CSV_HEADER_NOT_FOUND\nsecret",
                "report_format_kind": "CPC\nsecret",
                "report_format_columns": [
                    "SKU товара", "secret\namount", "3921245627",
                    "<script>alert(1)</script>",
                ],
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert "report_format_stage" not in result
    assert "message" not in result
    assert "secret" not in str(result)
    assert "report_format_columns" not in result
    assert "report_format_kind" not in result


def test_runtime_replaces_already_booked_finance_ad_with_exact_sku_ad():
    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    row = {
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "other_fees": -100.0,
        "product_cost": 200.0,
        "tax": 60.0,
    }

    adjusted = runtime._apply_advertising(
        row,
        {"finance_advertising_amount": -40.0, "expense": 125.0},
    )

    assert adjusted["other_fees"] == -60.0
    assert adjusted["net_accrual"] == 615.0
    assert adjusted["advertising_cost"] == 125.0
    assert adjusted["profit"] == 355.0
    assert adjusted["margin_percent"] == 35.5


def test_runtime_fails_closed_when_double_count_cannot_be_excluded():
    class _Advertising:
        def load(self, *_args):
            return {"error": False, "configured": True, "expense": 10.0}

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {"advertising_financial_evidence": {"policy_configured": False}},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        {"sku": "101"},
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SKU_ADVERTISING_MAPPING_REQUIRED"



def test_runtime_sanitizes_campaign_objects_lookup_status():
    assert PeriodProfitSkuRuntimeService._safe_historical_campaign_diagnostics([
        {
            "campaign_id": "27107278",
            "payment_type": "MISSING",
            "adv_object_type": "SKU",
            "state": "CAMPAIGN_STATE_INACTIVE",
            "from_date": "2026-05-17",
            "to_date": "MISSING",
            "created_at": "2026-05-17",
            "lookup_status": "FOUND",
            "objects_lookup_status": "private payload",
        },
    ])[0]["objects_lookup_status"] == "UNAVAILABLE"


def test_runtime_sanitizes_unknown_csv_row_label():
    safe = PeriodProfitSkuRuntimeService._safe_historical_report_format_row_label
    assert safe("  Примечание  ") == "Примечание"
    assert safe("row\n<private>") == "UNRECOGNIZED_VALUE"



@pytest.mark.parametrize(
    ("row_label", "expected_label"),
    [("Примечание", "Примечание"), ("", "(пусто)")],
)
def test_cpo_unknown_row_label_reaches_runtime_user_message(row_label, expected_label):
    csv_data = (
        "Дата;ID заказа;Номер заказа;SKU;SKU продвигаемого товара;"
        "Артикул;Источник заказов;Название товара;Количество;"
        "Стоимость продажи, ₽;Стоимость, ₽;Ставка, %;Ставка, ₽;Расход, ₽\n"
        "01.08.2026;123;123;3921245627;" + row_label + ";A-1;Поиск;Товар;"
        "1;100;5;5;1;5\n"
    ).encode("utf-8")

    class _CsvClient:
        BASE_URL = "https://performance.test"

        def __init__(self, *_args):
            self.session = SimpleNamespace(get=self._download)

        def _access_token(self, force=False):
            return {"access_token": "token"}

        def _request(self, method, endpoint, token, **kwargs):
            if endpoint == "/api/client/campaign":
                return {"list": []}
            if endpoint == "/api/client/statistic/orders/generate":
                return {"UUID": "12345678-1234-1234-1234-123456789abc"}
            if endpoint == "/api/client/statistics/12345678-1234-1234-1234-123456789abc":
                return {"state": "OK", "link": "https://performance.test/report"}
            raise AssertionError("Unexpected Ozon Performance endpoint: " + endpoint)

        def _download(self, *_args, **_kwargs):
            return SimpleNamespace(status_code=200, content=csv_data)

    advertising = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_CsvClient
    )
    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = advertising

    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "3921245627"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "3921245627"},
    )

    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_row_label"] == expected_label
    assert "Нераспознанная метка в столбце SKU: " + expected_label in result["message"]
