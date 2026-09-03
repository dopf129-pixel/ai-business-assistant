from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.expense_repository import (
    ExpenseRepository,
)
from services.period_profit_external_expense_evidence_service import (
    PeriodProfitExternalExpenseEvidenceService,
)
from services.period_profit_query_service import (
    PeriodProfitQueryService,
)


def test_v1261_expense_coverage_is_explicit_persisted_evidence(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )

    result = repository.confirm_coverage(
        "2026-09-01",
        "2026-09-03",
        note="Все расходы внесены",
    )

    assert result["error"] is False
    assert result["date_from"] == "2026-09-01"
    assert result["date_to"] == "2026-09-03"

    rows = repository.get_coverage_by_period(
        "2026-09-02",
        "2026-09-02",
    )

    assert len(rows) == 1
    assert rows[0]["note"] == (
        "Все расходы внесены"
    )


def test_v1262_expense_input_rejects_bad_date_bool_and_nonfinite(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )

    bad_date = repository.add_expense(
        "03.09.2026",
        "Аренда",
        100,
    )
    bad_bool = repository.add_expense(
        "2026-09-03",
        "Аренда",
        True,
    )
    bad_nan = repository.add_expense(
        "2026-09-03",
        "Аренда",
        float("nan"),
    )

    assert bad_date["error"] is True
    assert bad_date["code"] == (
        "EXPENSE_DATE_INVALID"
    )
    assert bad_bool["error"] is True
    assert bad_nan["error"] is True
    assert repository.get_expenses_by_period(
        "2026-09-01",
        "2026-09-30",
    ) == []


def test_v1263_empty_uncovered_period_is_unknown_not_confirmed_zero(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )
    service = (
        PeriodProfitExternalExpenseEvidenceService(
            repository
        )
    )

    result = service.load(
        "2026-09-01",
        "2026-09-03",
    )

    assert result["error"] is False
    assert (
        result["status"]
        == "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL"
    )
    assert result["expense_count"] == 0
    assert result["observed_expense_total"] == 0.0
    assert result["complete_expense_total"] is None
    assert result["coverage_complete"] is False
    assert result["coverage_gaps"] == [{
        "date_from": "2026-09-01",
        "date_to": "2026-09-03",
    }]
    assert (
        result[
            "missing_expense_configuration_is_zero"
        ]
        is False
    )


def test_v1264_empty_fully_covered_period_is_explicit_zero(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )
    repository.confirm_coverage(
        "2026-09-01",
        "2026-09-03",
    )

    result = (
        PeriodProfitExternalExpenseEvidenceService(
            repository
        )
        .load(
            "2026-09-01",
            "2026-09-03",
        )
    )

    assert (
        result["status"]
        == "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY"
    )
    assert result["coverage_complete"] is True
    assert result["expense_count"] == 0
    assert result["complete_expense_total"] == 0.0
    assert (
        result["complete_profit_adjustment_allowed"]
        is True
    )


def test_v1265_adjacent_coverage_intervals_cover_whole_period(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )
    repository.confirm_coverage(
        "2026-09-01",
        "2026-09-02",
    )
    repository.confirm_coverage(
        "2026-09-03",
        "2026-09-05",
    )

    result = (
        PeriodProfitExternalExpenseEvidenceService(
            repository
        )
        .load(
            "2026-09-01",
            "2026-09-05",
        )
    )

    assert result["coverage_complete"] is True
    assert result["coverage_gaps"] == []


def test_v1266_partial_expenses_are_observed_but_not_complete(tmp_path):
    repository = ExpenseRepository(
        tmp_path / "expenses.db"
    )
    repository.add_expense(
        "2026-09-01",
        "Аренда",
        1000,
    )
    repository.add_expense(
        "2026-09-02",
        "Сервисы",
        200,
    )
    repository.add_expense(
        "2026-09-02",
        "Сервисы",
        300,
    )
    repository.confirm_coverage(
        "2026-09-01",
        "2026-09-01",
    )

    result = (
        PeriodProfitExternalExpenseEvidenceService(
            repository
        )
        .load(
            "2026-09-01",
            "2026-09-03",
        )
    )

    assert result["coverage_complete"] is False
    assert result["expense_count"] == 3
    assert result["observed_expense_total"] == 1500.0
    assert result["complete_expense_total"] is None
    assert result["category_breakdown"] == {
        "Аренда": 1000.0,
        "Сервисы": 500.0,
    }
    assert result["coverage_gaps"] == [{
        "date_from": "2026-09-02",
        "date_to": "2026-09-03",
    }]


class MalformedRepository:
    def get_expenses_by_period(
        self,
        date_from,
        date_to,
    ):
        return [{
            "id": 1,
            "expense_date": "2026-09-02",
            "category": "Аренда",
            "amount": float("inf"),
            "description": "",
        }]

    def get_coverage_by_period(
        self,
        date_from,
        date_to,
    ):
        return []


def test_v1267_malformed_external_expense_row_fails_closed():
    result = (
        PeriodProfitExternalExpenseEvidenceService(
            MalformedRepository()
        )
        .load(
            "2026-09-01",
            "2026-09-03",
        )
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_EXTERNAL_EXPENSE_ROW_INVALID"
    )


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "date_from": "2026-09-01",
        "date_to": "2026-09-03",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "commission": -100.0,
        "logistics": -100.0,
        "acquiring": -10.0,
        "other_fees": -90.0,
        "product_cost": 300.0,
        "tax": 60.0,
        "profit": 340.0,
        "margin_percent": 34.0,
        "products": [],
        "fee_breakdown": {},
        "fee_components_included": True,
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "ozon_account_reconciliation": 0.0,
        "profit_scope": (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
        ),
    }


def _external_evidence(
    *,
    total=100.0,
    count=1,
    complete=False,
):
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL"
        ),
        "coverage_configured": complete,
        "coverage_complete": complete,
        "coverage_intervals": (
            [{
                "id": 1,
                "date_from": "2026-09-01",
                "date_to": "2026-09-03",
                "note": "",
                "source": "LOCAL_EXPENSE_COVERAGE",
            }]
            if complete
            else []
        ),
        "coverage_gaps": (
            []
            if complete
            else [{
                "date_from": "2026-09-02",
                "date_to": "2026-09-03",
            }]
        ),
        "expense_count": count,
        "expenses": [],
        "category_breakdown": (
            {"Аренда": total}
            if count
            else {}
        ),
        "observed_expense_total": total,
        "complete_expense_total": (
            total
            if complete
            else None
        ),
        "observed_expense_adjustment_supported": True,
        "complete_profit_adjustment_allowed": complete,
        "missing_expense_configuration_is_zero": False,
        "read_only": True,
        "executed": False,
    }


class SummaryService:
    def calculate(
        self,
        date_from,
        date_to,
        products,
    ):
        return {
            **_summary(),
            "date_from": date_from,
            "date_to": date_to,
        }


class ExternalService:
    def __init__(self, evidence):
        self.evidence = evidence

    def load(
        self,
        date_from,
        date_to,
    ):
        return dict(self.evidence)


def test_v1268_query_derives_observed_profit_but_blocks_complete_claim():
    service = PeriodProfitQueryService(
        SummaryService(),
        lambda: [{"sku": "100"}],
        external_expense_evidence_service=(
            ExternalService(
                _external_evidence(
                    total=100.0,
                    complete=False,
                )
            )
        ),
    )

    result = service.query(
        date_from="2026-09-01",
        date_to="2026-09-03",
    )

    assert result["error"] is False
    adjustment = result[
        "external_expense_adjustment"
    ]
    assert (
        adjustment[
            "observed_profit_after_external_expenses"
        ]
        == 240.0
    )
    assert (
        adjustment["observed_margin_percent"]
        == 24.0
    )
    assert (
        adjustment[
            "complete_profit_after_external_expenses"
        ]
        is None
    )
    assert (
        adjustment["profit_adjustment_complete"]
        is False
    )
    assert (
        result["coverage"][
            "external_expense_evidence_status"
        ]
        == "PARTIAL"
    )


def test_v1269_partial_response_labels_observed_profit_as_incomplete():
    evidence = _external_evidence(
        total=100.0,
        complete=False,
    )
    adjustment = (
        PeriodProfitQueryService
        ._external_expense_adjustment(
            _summary(),
            evidence,
        )
    )

    text = build_period_profit_response(
        _summary(),
        external_expense_evidence=evidence,
        external_expense_adjustment=(
            adjustment
        ),
    )["text"]

    assert (
        "Прибыль до внешних расходов: "
        "340.00 ₽ (34.00%)"
        in text
    )
    assert (
        "🏢 Внешние расходы — внесённые: "
        "100.00 ₽ (10.00%)"
        in text
    )
    assert (
        "Наблюдаемая прибыль после внесённых "
        "внешних расходов: 240.00 ₽ (24.00%)"
        in text
    )
    assert (
        "Учёт внешних расходов не покрывает "
        "весь период"
        in text
    )
    assert (
        "Прибыль после внешних расходов: "
        not in text
    )


def test_v1270_complete_coverage_allows_full_external_expense_adjustment():
    evidence = _external_evidence(
        total=100.0,
        complete=True,
    )
    adjustment = (
        PeriodProfitQueryService
        ._external_expense_adjustment(
            _summary(),
            evidence,
        )
    )

    text = build_period_profit_response(
        _summary(),
        external_expense_evidence=evidence,
        external_expense_adjustment=(
            adjustment
        ),
    )["text"]
    coverage = build_period_profit_coverage(
        _summary(),
        external_expense_evidence=evidence,
    )

    assert (
        adjustment[
            "complete_profit_after_external_expenses"
        ]
        == 240.0
    )
    assert (
        adjustment["complete_margin_percent"]
        == 24.0
    )
    assert (
        adjustment["profit_adjustment_complete"]
        is True
    )
    assert (
        "Coverage расходов: полный"
        in text
    )
    assert (
        "Прибыль после внешних расходов: "
        "240.00 ₽ (24.00%)"
        in text
    )
    assert (
        coverage[
            "external_expense_evidence_status"
        ]
        == "COMPLETE"
    )
    assert (
        coverage[
            "external_expense_complete_total"
        ]
        == 100.0
    )
    assert (
        coverage["accounting_net_profit_claim_allowed"]
        is False
    )
