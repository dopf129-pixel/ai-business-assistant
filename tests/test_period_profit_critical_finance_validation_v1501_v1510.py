from api.period_profit_ozon_client import PeriodProfitOzonClient
from services.period_profit_finance_service import PeriodProfitFinanceService
from services.period_profit_critical_finance_summary_service import (
    PeriodProfitCriticalFinanceSummaryService,
)
from services.period_profit_summary_service import PeriodProfitSummaryService


ENDPOINT = PeriodProfitOzonClient.FINANCE_ACCRUAL_BY_DAY


def _money(amount):
    return {"amount": str(amount), "currency": "RUB"}


def _posting(commission=None, delivery=None, item_fees=None):
    product = {
        "sku": "SKU-1",
        "commission": commission
        if commission is not None
        else {
            "sale_amount": _money("90"),
            "sale_commission": _money("-12"),
        },
    }
    if delivery is not None:
        product["delivery"] = delivery
    accrual = {
        "accrued_category": "POSTING",
        "total_amount": _money("20"),
        "posting": {"products": [product]},
    }
    if item_fees is not None:
        accrual["item_fees"] = item_fees
    return accrual


def _normalize(accrual):
    return PeriodProfitOzonClient()._normalize_period_profit_canonical_finance(
        ENDPOINT,
        {"error": False, "accruals": [accrual]},
    )


def test_v1501_diagnostic_seller_price_does_not_block_canonical_finance():
    result = _normalize(_posting())

    assert result.get("error") is not True
    diagnostics = result["_period_profit_revenue_diagnostics"]
    assert diagnostics["fields"]["seller_price"]["complete"] is False
    assert "_period_profit_finance_completeness" not in result


def test_v1502_missing_ancillary_fee_money_is_parser_safe_and_explicitly_incomplete():
    result = _normalize(
        _posting(
            commission={"sale_amount": _money("90")},
            delivery={"services": [{"type_id": 29, "accrued": None}]},
            item_fees={
                "fees": [
                    {
                        "sku": "SKU-1",
                        "fees": [{"type_id": 1, "accrued": None}],
                    }
                ]
            },
        )
    )

    assert result.get("error") is not True
    state = result["_period_profit_finance_completeness"]
    assert state["fee_components_included"] is False
    assert state["ancillary_incomplete_count"] == 3
    product = result["accruals"][0]["posting"]["products"][0]
    assert product["commission"]["sale_commission"]["amount"] == "0"
    assert product["delivery"]["services"][0]["accrued"]["amount"] == "0"
    fee = result["accruals"][0]["item_fees"]["fees"][0]["fees"][0]
    assert fee["accrued"]["amount"] == "0"


def test_v1503_malformed_ancillary_containers_do_not_hide_account_authority():
    result = _normalize(
        _posting(
            delivery="bad",
            item_fees="bad",
        )
    )

    assert result.get("error") is not True
    assert result["_period_profit_finance_completeness"]["fee_components_included"] is False
    accrual = result["accruals"][0]
    assert accrual["item_fees"] == {"fees": []}
    assert accrual["posting"]["products"][0]["delivery"] == {"services": []}


def test_v1504_unknown_total_amount_still_fails_closed():
    accrual = _posting()
    accrual["total_amount"] = None

    result = _normalize(accrual)

    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


def test_v1505_unrecoverable_sale_amount_still_fails_closed():
    result = _normalize(
        _posting(
            commission={
                "sale_amount": None,
                "sale_price": _money("60"),
                "bonus": _money("30"),
                "sale_commission": _money("-12"),
            }
        )
    )

    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


def test_v1506_sale_amount_recovery_uses_only_exact_three_components():
    result = _normalize(
        _posting(
            commission={
                "sale_price": _money("61.85"),
                "bonus": _money("27.53"),
                "coinvestment": _money("0.62"),
                "seller_price": _money("999"),
                "sale_commission": _money("-12"),
            }
        )
    )

    assert result.get("error") is not True
    commission = result["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "90.00"


def test_v1507_explicit_sale_amount_wins_when_diagnostic_components_are_unknown():
    result = _normalize(
        _posting(
            commission={
                "sale_amount": _money("90"),
                "sale_price": None,
                "bonus": None,
                "coinvestment": None,
                "seller_price": None,
                "sale_commission": _money("-12"),
            }
        )
    )

    assert result.get("error") is not True
    commission = result["accruals"][0]["posting"]["products"][0]["commission"]
    assert commission["sale_amount"]["amount"] == "90"


def test_v1508_malformed_formula_structure_still_fails_closed():
    accrual = _posting()
    accrual["posting"]["products"][0]["commission"] = "bad"

    result = _normalize(accrual)

    assert result == {
        "error": True,
        "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
        "complete": False,
    }


class _Ozon:
    def get_accruals_by_day(self, accrual_date):
        return {
            "error": False,
            "accruals": [],
            "_period_profit_finance_completeness": {
                "fee_components_included": False,
                "ancillary_incomplete_count": 2,
            },
        }


def test_v1509_finance_adapter_propagates_ancillary_completeness():
    service = PeriodProfitFinanceService()
    service.ozon = _Ozon()
    service.accrual_types = {999: {"name": "x", "description": "x"}}

    result = service.get_daily_account_finance("2026-08-09")

    assert result["error"] is False
    assert result["net_accrual"] == 0.0
    assert result["fee_components_included"] is False
    assert result["ancillary_incomplete_count"] == 2


def test_v1510_summary_adapter_never_promotes_incomplete_fee_decomposition(monkeypatch):
    class Finance:
        _daily_accrual_cache = {
            "2026-08-09": {
                "_period_profit_finance_completeness": {
                    "fee_components_included": False,
                    "ancillary_incomplete_count": 4,
                }
            }
        }

    monkeypatch.setattr(
        PeriodProfitSummaryService,
        "calculate",
        lambda self, date_from, date_to, products: {
            "error": False,
            "fee_components_included": True,
        },
    )
    service = PeriodProfitCriticalFinanceSummaryService(Finance(), object(), tax_rate=0)

    result = service.calculate("2026-08-09", "2026-08-09", [])

    assert result["error"] is False
    assert result["fee_components_included"] is False
    assert result["ancillary_finance_incomplete_count"] == 4
