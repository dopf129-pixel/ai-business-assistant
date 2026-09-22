from services.period_profit_final_application_query_service import (
    PeriodProfitFinalApplicationQueryService,
)


class _Base:
    def __init__(self):
        self.compare_flags = []
        self.product_provider = lambda: [{"sku": "selected"}]
        self.summary_service = _Summary()
        self.return_evidence_service = None
        self.return_cogs_recovery_evidence_service = None

    def query(self, compare_previous=False, **_kwargs):
        self.compare_flags.append(compare_previous)
        return {
            "error": False,
            "request": {
                "status": "PERIOD_PROFIT_REQUEST_READY",
                "mode": "PRESET",
                "period_code": "7D",
                "date_from": "2026-09-13",
                "date_to": "2026-09-19",
            },
            "summary": _summary(),
            "previous_summary": None,
        }


class _Summary:
    def __init__(self):
        self.calls = []

    def calculate(self, date_from, date_to, products):
        self.calls.append((date_from, date_to, products))
        return _summary()


class _Application:
    def apply(self, summary, evidence):
        return {"error": False, "summary": summary, "evidence": evidence}


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "profit_scope": "FULL_PERIOD",
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "products": [],
        "revenue": 0.0,
        "net_accrual": 0.0,
        "commission": 0.0,
        "logistics": 0.0,
        "acquiring": 0.0,
        "other_fees": 0.0,
        "product_cost": 0.0,
        "tax": 0.0,
        "profit": 0.0,
        "fee_breakdown": [],
    }


def test_final_query_does_not_make_base_recalculate_previous_period():
    base = _Base()
    service = PeriodProfitFinalApplicationQueryService(base, _Application())

    result = service.query(period_code="7D", compare_previous=True)

    assert result["error"] is False
    assert base.compare_flags == [False]
    assert len(base.summary_service.calls) == 1


def test_selected_sku_current_profit_survives_unprovable_previous_identity():
    base = _Base()
    base.product_provider = lambda: [{
        "sku": "selected",
        "_period_profit_selected_scope": True,
    }]
    base.summary_service.calculate = lambda *_args: {
        "error": True,
        "code": "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_UNRESOLVED",
    }
    service = PeriodProfitFinalApplicationQueryService(base, _Application())

    result = service.query(period_code="7D", compare_previous=True)

    assert result["error"] is False
    assert result["summary"]["status"] == "PERIOD_PROFIT_SUMMARY_READY"
    assert result["previous_summary"] is None
    assert result["comparison"] is None
    assert result["comparison_error_code"] == (
        "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_UNRESOLVED"
    )


def test_store_wide_current_profit_survives_previous_failure_without_recalculation():
    base = _Base()
    base.product_provider = lambda: [{"sku": "catalog-sku"}]
    base.summary_service.calculate = lambda *_args: {
        "error": True,
        "code": "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE",
    }
    service = PeriodProfitFinalApplicationQueryService(base, _Application())

    result = service.query(period_code="7D", compare_previous=True)

    assert result["error"] is False
    assert base.compare_flags == [False]
    assert result["summary"]["status"] == "PERIOD_PROFIT_SUMMARY_READY"
    assert result["previous_summary"] is None
    assert result["comparison"] is None
    assert result["comparison_error_code"] == (
        "PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE"
    )
