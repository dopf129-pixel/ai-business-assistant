from api.period_profit_ozon_client import PeriodProfitOzonClient
from api.period_profit_runtime_ozon_client import PeriodProfitRuntimeOzonClient
from services.period_profit_finance_service import PeriodProfitFinanceService


ENDPOINT = PeriodProfitRuntimeOzonClient.FINANCE_ACCRUAL_BY_DAY


def _money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def _response(commission):
    product = {"sku": "SKU-1"}
    if commission is not ...:
        product["commission"] = commission
    return {
        "error": False,
        "accruals": [
            {
                "accrued_category": "POSTING",
                "total_amount": _money("-25"),
                "posting": {"products": [product]},
            }
        ],
    }


def test_v1511_absent_commission_block_is_valid_nonsale_posting():
    result = PeriodProfitRuntimeOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        _response(...),
    )
    assert result.get("error") is not True
    commission = result["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "0"


def test_v1512_null_commission_block_is_valid_nonsale_posting():
    result = PeriodProfitRuntimeOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        _response(None),
    )
    assert result.get("error") is not True
    assert result["accruals"][0]["posting"]["products"][0]["commission"]["sale_amount"]["amount"] == "0"


def test_v1513_empty_commission_block_is_valid_nonsale_posting():
    result = PeriodProfitRuntimeOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        _response({}),
    )
    assert result.get("error") is not True


def test_v1514_partial_sale_components_remain_fail_closed():
    result = PeriodProfitRuntimeOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        _response({"sale_price": _money("60")}),
    )
    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


def test_v1515_malformed_commission_container_remains_fail_closed():
    result = PeriodProfitRuntimeOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        _response("bad"),
    )
    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


def test_v1516_finance_service_routes_production_client_but_preserves_test_doubles():
    service = PeriodProfitFinanceService()
    service.ozon = PeriodProfitOzonClient()
    assert type(service.ozon) is PeriodProfitRuntimeOzonClient

    class Fake:
        pass

    fake = Fake()
    service.ozon = fake
    assert service.ozon is fake
