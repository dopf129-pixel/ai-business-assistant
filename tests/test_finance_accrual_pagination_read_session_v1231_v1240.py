from api.ozon_client import OzonClient
from services.finance_service import FinanceService
from services.period_profit_summary_service import (
    PeriodProfitSummaryService,
)


class PagingOzon(OzonClient):
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def _post(
        self,
        endpoint,
        data,
        timeout=20,
        max_attempts=3,
    ):
        self.calls.append({
            "endpoint": endpoint,
            "data": dict(data),
            "timeout": timeout,
            "max_attempts": max_attempts,
        })
        return self.pages.pop(0)


def test_v1231_first_accrual_page_sends_required_empty_last_id():
    client = PagingOzon([
        {
            "accruals": [],
            "last_id": "",
        }
    ])

    result = client.get_accruals_by_day(
        "2026-06-06"
    )

    assert result["error"] is not True
    assert client.calls[0]["endpoint"] == (
        "/v1/finance/accrual/by-day"
    )
    assert client.calls[0]["data"] == {
        "date": "2026-06-06",
        "last_id": "",
    }


def test_v1232_accrual_pages_are_combined_until_last_id_is_empty():
    client = PagingOzon([
        {
            "accruals": [{"page": 1}],
            "last_id": "cursor-1",
        },
        {
            "accruals": [{"page": 2}],
            "last_id": "",
        },
    ])

    result = client.get_accruals_by_day(
        "2026-06-06"
    )

    assert result["accruals"] == [
        {"page": 1},
        {"page": 2},
    ]
    assert result["pages_loaded"] == 2
    assert client.calls[1]["data"]["last_id"] == (
        "cursor-1"
    )


def test_v1233_malformed_accrual_page_fails_closed():
    client = PagingOzon([
        {
            "accruals": "bad",
            "last_id": "",
        }
    ])

    result = client.get_accruals_by_day(
        "2026-06-06"
    )

    assert result["error"] is True
    assert result["code"] == (
        "OZON_FINANCE_ACCRUAL_RESPONSE_INVALID"
    )


def test_v1234_repeated_accrual_cursor_fails_closed():
    client = PagingOzon([
        {
            "accruals": [{"page": 1}],
            "last_id": "cursor-1",
        },
        {
            "accruals": [{"page": 2}],
            "last_id": "cursor-1",
        },
    ])

    result = client.get_accruals_by_day(
        "2026-06-06"
    )

    assert result["error"] is True
    assert result["code"] == (
        "OZON_FINANCE_ACCRUAL_CURSOR_INVALID"
    )


def test_v1235_page_cap_does_not_return_partial_finance_as_complete():
    client = PagingOzon([
        {
            "accruals": [{"page": 1}],
            "last_id": "cursor-1",
        }
    ])

    result = client.get_accruals_by_day(
        "2026-06-06",
        max_pages=1,
    )

    assert result["error"] is True
    assert result["code"] == (
        "OZON_FINANCE_ACCRUAL_PAGE_LIMIT_REACHED"
    )


class DailyOzon:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get_accruals_by_day(self, day):
        self.calls += 1
        return self.response


def _finance_with_ozon(ozon):
    service = FinanceService()
    service.ozon = ozon
    service.accrual_types = {
        1: {
            "name": "acquiring",
            "description": "acquiring",
        }
    }
    return service


def test_v1236_same_day_is_loaded_once_for_multiple_skus_in_read_session():
    service = _finance_with_ozon(
        DailyOzon({
            "accruals": [],
            "last_id": "",
        })
    )

    first = service.get_daily_finance(
        "2026-06-06",
        sku="100",
    )
    second = service.get_daily_finance(
        "2026-06-06",
        sku="200",
    )

    assert first["error"] is False
    assert second["error"] is False
    assert service.ozon.calls == 1


def test_v1237_new_read_session_clears_daily_accrual_cache():
    service = _finance_with_ozon(
        DailyOzon({
            "accruals": [],
            "last_id": "",
        })
    )

    service.get_daily_finance(
        "2026-06-06",
        sku="100",
    )
    service.get_daily_finance(
        "2026-06-06",
        sku="200",
    )
    service.begin_read_session()
    service.get_daily_finance(
        "2026-06-06",
        sku="100",
    )

    assert service.ozon.calls == 2


class SessionFinance:
    def __init__(self):
        self.session_count = 0

    def begin_read_session(self):
        self.session_count += 1

    def get_daily_finance(
        self,
        day,
        sku=None,
    ):
        return {
            "error": False,
            "sales_count": 1,
            "gross_sales": 100.0,
            "net_accrual": 80.0,
            "commission": -10.0,
            "logistics": -5.0,
            "acquiring": -2.0,
            "other_fees": -3.0,
            "fee_breakdown": {},
        }


class Costs:
    def get_cost(self, product_id):
        return (
            str(product_id),
            "hook-2",
            "100",
            20.0,
            "RUB",
            None,
        )


def test_v1238_period_profit_starts_one_finance_read_session():
    finance = SessionFinance()

    result = PeriodProfitSummaryService(
        finance,
        Costs(),
        tax_rate=0.06,
    ).calculate(
        "2026-06-06",
        "2026-06-06",
        [("10", "hook-2", "100")],
    )

    assert result["error"] is False
    assert finance.session_count == 1


class BrokenSessionFinance(SessionFinance):
    def begin_read_session(self):
        raise RuntimeError(
            "private session failure"
        )


def test_v1239_read_session_failure_is_contained():
    result = PeriodProfitSummaryService(
        BrokenSessionFinance(),
        Costs(),
        tax_rate=0.06,
    ).calculate(
        "2026-06-06",
        "2026-06-06",
        [("10", "hook-2", "100")],
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_FINANCE_UNAVAILABLE"
    )
    assert "private session failure" not in str(
        result
    )


def _posting_accrual(sku):
    return {
        "accrued_category": "POSTING",
        "total_amount": {
            "amount": "80.00",
        },
        "posting": {
            "products": [{
                "sku": str(sku),
                "commission": {
                    "sale_amount": {
                        "amount": "100.00",
                    },
                    "sale_commission": {
                        "amount": "-10.00",
                    },
                },
                "delivery": {
                    "services": [],
                },
            }],
        },
        "item_fees": {
            "fees": [],
        },
    }


def test_v1240_finance_includes_target_sku_from_second_accrual_page():
    client = PagingOzon([
        {
            "accruals": [
                _posting_accrual("other")
            ],
            "last_id": "cursor-1",
        },
        {
            "accruals": [
                _posting_accrual("100")
            ],
            "last_id": "",
        },
    ])
    service = _finance_with_ozon(
        client
    )

    result = service.get_daily_finance(
        "2026-06-06",
        sku="100",
    )

    assert result["error"] is False
    assert result["sales_count"] == 1
    assert result["gross_sales"] == 100.0
    assert result["net_accrual"] == 80.0
    assert len(client.calls) == 2
