from services.sales_context_provider import SalesContextProvider
from services.store_period_profit_service import StorePeriodProfitService


class _FifoScope:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get_scope_mode(self, product, *, date_from=None, date_to=None):
        self.calls.append((product, date_from, date_to))
        return dict(self.result)


class _FinanceAnalytics:
    def __init__(self):
        self.calls = []

    def get_period_finance(self, date_from, date_to, sku):
        self.calls.append((date_from, date_to, sku))
        return {
            "error": False,
            "sales_count": 2,
            "gross_sales": 200,
            "net_accrual": 150,
        }


class _Cost:
    def __init__(self):
        self.calls = []

    def get_cost(self, product_id):
        self.calls.append(product_id)
        return (product_id, None, None, 10)


class _Profit:
    def calculate(self, finance, cost):
        return {
            "error": False,
            "gross_sales": finance["gross_sales"],
            "gross_profit": finance["net_accrual"] - cost,
        }


def _service(scope_result):
    service = StorePeriodProfitService(
        finance_service=object(),
        cost_service=_Cost(),
        profit_service=_Profit(),
        fifo_cost_source_service=_FifoScope(scope_result),
    )
    service.finance_analytics = _FinanceAnalytics()
    return service


def _product():
    return {"product_id": "101", "offer_id": "offer-a", "sku": "sku-a"}


def test_active_fifo_blocks_aggregate_legacy_profit_before_reading_current_cost():
    service = _service({
        "error": False,
        "active": True,
        "code": "FIFO_COST_MODE_FIFO",
    })

    result = service.calculate_period_profit(
        "2026-11-06", "2026-11-06", [_product()],
    )

    assert result == {
        "error": True,
        "code": "PERIOD_PROFIT_FIFO_ALLOCATION_REQUIRED",
        "reason_code": "FIFO_COST_MODE_FIFO",
        "products_count": 0,
        "profits": [],
    }
    assert service.cost_service.calls == []
    assert service.finance_analytics.calls == []
    assert service.fifo_cost_source_service.calls == [
        (_product(), "2026-11-06", "2026-11-06"),
    ]


def test_period_through_fifo_cutoff_is_blocked_instead_of_using_legacy_cost():
    service = _service({
        "error": False,
        "active": True,
        "period_cutover_overlap": True,
        "code": "FIFO_PERIOD_SPANS_COST_CUTOFF",
    })

    result = service.calculate_period_profit(
        "2026-11-05", "2026-11-06", [_product()],
    )

    assert result["error"] is True
    assert result["reason_code"] == "FIFO_PERIOD_SPANS_COST_CUTOFF"
    assert service.cost_service.calls == []
    assert service.finance_analytics.calls == []


def test_period_before_fifo_cutoff_keeps_legacy_cost_path():
    service = _service({
        "error": False,
        "active": False,
        "code": "FIFO_COST_MODE_PRE_CUTOFF",
    })

    result = service.calculate_period_profit(
        "2026-11-04", "2026-11-05", [_product()],
    )

    assert result["error"] is False
    assert result["products_count"] == 1
    assert result["profits"][0]["gross_profit"] == 140
    assert service.cost_service.calls == ["101"]
    assert service.finance_analytics.calls == [
        ("2026-11-04", "2026-11-05", "sku-a"),
    ]


def test_fifo_scope_read_failure_fails_closed_before_legacy_profit():
    service = _service({"error": True, "code": "FIFO_STORAGE_UNAVAILABLE"})

    result = service.calculate_period_profit(
        "2026-11-06", "2026-11-06", [_product()],
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_FIFO_SCOPE_UNAVAILABLE"
    assert service.cost_service.calls == []
    assert service.finance_analytics.calls == []


def test_sales_context_does_not_report_decline_when_fifo_profit_is_blocked():
    period_profit = _service({
        "error": False,
        "active": True,
        "code": "FIFO_COST_MODE_FIFO",
    })

    class Products:
        def load_products(self):
            return [_product()]

    class Analytics:
        def get_period(self):
            return {"error": False, "date_from": "2026-11-06", "date_to": "2026-11-06"}

        def get_previous_period(self):
            return {"error": False, "date_from": "2026-11-05", "date_to": "2026-11-05"}

    result = SalesContextProvider(
        product_service=Products(),
        period_profit_service=period_profit,
        analytics_service=Analytics(),
    ).build()

    assert result["report"] == {
        "sales_down": False,
        "sales_evidence_available": False,
    }
    assert period_profit.cost_service.calls == []
