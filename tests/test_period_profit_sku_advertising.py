from datetime import date, timedelta

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
        assert endpoint == "/api/client/campaign"
        assert token == "token"
        return {"list": [{"id": "1001", "paymentType": "CAMPAIGN_TYPE_INVALID"}]}


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


def test_historical_campaign_payment_type_survives_advertising_service():
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_HistoricalClient
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN"
    assert result["campaign_payment_type"] == "CAMPAIGN_TYPE_INVALID"
    assert result["campaign_id"] == "1001"


def test_historical_report_format_stage_survives_advertising_service(monkeypatch):
    monkeypatch.setattr(
        HistoricalPerformanceReports,
        "load",
        lambda *_args: {
            "error": True,
            "code": "OZON_HISTORICAL_REPORT_FORMAT",
            "report_format_stage": "CSV_HEADER_NOT_FOUND",
        },
    )
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_HistoricalClient
    )

    result = service.load("2026-08-01", "2026-08-30", {"101"})

    assert result["error"] is True
    assert result["code"] == "OZON_HISTORICAL_REPORT_FORMAT"
    assert result["report_format_stage"] == "CSV_HEADER_NOT_FOUND"


def test_runtime_shows_safe_historical_campaign_diagnostic():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_CAMPAIGN_TYPE_UNKNOWN",
                "campaign_payment_type": "CAMPAIGN_TYPE_INVALID",
                "campaign_id": "1001",
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
    assert result["campaign_payment_type"] == "CAMPAIGN_TYPE_INVALID"
    assert result["campaign_id"] == "1001"
    assert "paymentType: CAMPAIGN_TYPE_INVALID" in result["message"]
    assert "ID кампании: 1001" in result["message"]
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


def test_runtime_shows_safe_historical_report_format_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_REPORT_FORMAT",
                "report_format_stage": "CSV_HEADER_NOT_FOUND",
            }

    runtime = object.__new__(PeriodProfitSkuRuntimeService)
    runtime.advertising_service = _Advertising()
    result = runtime._load_advertising(
        {},
        {"products": [{"sku": "101"}]},
        {"date_from": "2026-08-01", "date_to": "2026-08-30"},
        {"sku": "101"},
    )

    assert result["report_format_stage"] == "CSV_HEADER_NOT_FOUND"
    assert "Этап: CSV_HEADER_NOT_FOUND" in result["message"]
    assert "OZON_HISTORICAL_REPORT_FORMAT" in result["message"]


def test_runtime_hides_unrecognized_report_format_stage():
    class _Advertising:
        def load(self, *_args):
            return {
                "error": True,
                "code": "OZON_HISTORICAL_REPORT_FORMAT",
                "report_format_stage": "CSV_HEADER_NOT_FOUND\nsecret",
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
