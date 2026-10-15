from services.period_profit_final_application_query_service import (
    PeriodProfitFinalApplicationQueryService,
)
from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
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


class _RuntimeBase(_Base):
    def __init__(self):
        super().__init__()
        self.current_error = False

    def query(self, period_code=None, date_from=None, date_to=None, compare_previous=False, today=None):
        self.compare_flags.append(compare_previous)
        if self.current_error:
            return {
                "error": True,
                "code": "TEST_CURRENT_SUMMARY_UNAVAILABLE",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        current_summary = self.summary_service.calculate(
            "2026-09-13",
            "2026-09-19",
            self.product_provider(),
        )
        return {
            "error": False,
            "request": {
                "status": "PERIOD_PROFIT_REQUEST_READY",
                "mode": "PRESET",
                "period_code": "7D",
                "date_from": "2026-09-13",
                "date_to": "2026-09-19",
            },
            "summary": current_summary,
            "previous_summary": None,
        }


class _Summary:
    def __init__(self):
        self.calls = []

    def calculate(self, date_from, date_to, products):
        self.calls.append((date_from, date_to, products))
        result = _summary()
        result.update(date_from=date_from, date_to=date_to)
        return result


class _Application:
    def apply(self, summary, evidence):
        return {"error": False, "summary": summary, "evidence": evidence}


class _FailingReturnLoader:
    def __init__(self, failure_code):
        self.failure_code = failure_code
        self.calls = []

    def load(self, date_from, date_to):
        self.calls.append((date_from, date_to))
        if self.failure_code is not None and date_to == "2026-09-12":
            raise RuntimeError(self.failure_code)
        return {"error": False, "status": "RETURN_EVIDENCE_READY"}


class _RecoveryEvidence:
    def analyze(self, return_evidence, products):
        return {"error": False, "status": "RECOVERY_READY"}


class _PreviousApplicationFailure(_Application):
    def apply(self, summary, evidence):
        if summary.get("date_from") == "2026-09-06":
            return {"error": True, "code": "TEST_PREVIOUS_APPLICATION_FAILED"}
        return super().apply(summary, evidence)


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


def test_runtime_keeps_finalized_current_when_previous_return_loader_raises():
    base = _RuntimeBase()
    base.return_evidence_service = _FailingReturnLoader(
        "TEST_PREVIOUS_RETURN_LOADER_FAILED"
    )
    base.return_cogs_recovery_evidence_service = _RecoveryEvidence()
    summary = base.summary_service
    service = PeriodProfitFinalApplicationQueryService(base, _Application())
    runtime = AssistantPeriodProfitRuntimeService(service)

    result = runtime.handle_callback(
        "PERIOD_PROFIT:7D",
        today="2026-09-19",
    )

    assert result["error"] is False
    assert result["summary"]["profit"] == 0.0
    assert result["comparison"] is None
    assert result["comparison_status"] == "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
    assert result["comparison_error_code"] == (
        "PERIOD_PROFIT_FINAL_PREVIOUS_RETURN_EVIDENCE_UNAVAILABLE"
    )
    assert "Сравнение с прошлым периодом недоступно" in result["text"]
    assert base.compare_flags == [False]
    assert summary.calls == [
        ("2026-09-13", "2026-09-19", [{"sku": "selected"}]),
        ("2026-09-06", "2026-09-12", [{"sku": "selected"}]),
    ]
    assert base.return_evidence_service.calls == [("2026-09-06", "2026-09-12")]


def test_runtime_keeps_finalized_current_when_previous_application_fails():
    base = _RuntimeBase()
    base.return_evidence_service = _FailingReturnLoader(None)
    base.return_cogs_recovery_evidence_service = _RecoveryEvidence()
    summary = base.summary_service
    service = PeriodProfitFinalApplicationQueryService(
        base,
        _PreviousApplicationFailure(),
    )
    runtime = AssistantPeriodProfitRuntimeService(service)

    result = runtime.handle_callback(
        "PERIOD_PROFIT:7D",
        today="2026-09-19",
    )

    assert result["error"] is False
    assert result["summary"]["profit"] == 0.0
    assert result["comparison"] is None
    assert result["comparison_status"] == "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
    assert result["comparison_error_code"] == "TEST_PREVIOUS_APPLICATION_FAILED"
    assert base.compare_flags == [False]
    assert summary.calls == [
        ("2026-09-13", "2026-09-19", [{"sku": "selected"}]),
        ("2026-09-06", "2026-09-12", [{"sku": "selected"}]),
    ]


def test_runtime_preserves_mandatory_current_failure_without_retry():
    base = _RuntimeBase()
    base.current_error = True
    service = PeriodProfitFinalApplicationQueryService(base, _Application())
    runtime = AssistantPeriodProfitRuntimeService(service)

    result = runtime.handle_callback(
        "PERIOD_PROFIT:7D",
        today="2026-09-19",
    )

    assert result["error"] is True
    assert result["code"] == "TEST_CURRENT_SUMMARY_UNAVAILABLE"
    assert base.compare_flags == [False]
    assert base.summary_service.calls == []
