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


def test_selected_sku_advertising_is_one_batched_performance_call(monkeypatch):
    monkeypatch.setattr(
        "services.period_profit_sku_advertising_service.get_current_tenant_user_id",
        lambda: "user::ozon::store",
    )
    _Client.calls = 0
    service = PeriodProfitSkuAdvertisingService(
        repository=_Repository(), client_factory=_Client
    )

    result = service.load("2026-09-01", "2026-09-30", {"101", "old-101"})

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
