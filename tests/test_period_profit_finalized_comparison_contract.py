from services.period_profit_final_application_query_service import (
    PeriodProfitFinalApplicationQueryService,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class _Products:
    def __call__(self):
        return [{"sku": "fixture"}]


class _Summaries:
    def __init__(self, previous_tax_rate=6.0):
        self.calls = []
        self.previous_tax_rate = previous_tax_rate

    def calculate(self, date_from, date_to, _products):
        self.calls.append((date_from, date_to))
        profit = 100.0 if date_from == "2026-09-13" else 90.0
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SUMMARY_READY",
            "date_from": date_from,
            "date_to": date_to,
            "profit_scope": "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V3",
            "returns_included": False,
            "advertising_included": False,
            "storage_included": False,
            "revenue": 1000.0,
            "discount_points": 100.0,
            "revenue_tax_base": 900.0,
            "net_accrual": 600.0,
            "product_cost": 100.0,
            "tax": 60.0,
            "profit": profit,
            "margin_percent": profit / 10,
            "units_sold": 10,
            "tax_mode": "USN_INCOME",
            "tax_rate_percent": (
                self.previous_tax_rate
                if date_from == "2026-09-06"
                else 6.0
            ),
            "minimum_tax_rate_percent": None,
            "return_cogs_profit_applied": False,
            "return_cogs_profit_application_amount": None,
            "products": [],
        }


class _SkuSummaries(_Summaries):
    def calculate(self, date_from, date_to, products):
        result = super().calculate(date_from, date_to, products)
        result["products"] = [
            {
                "sku": "sku-current" if date_from == "2026-09-13" else "sku-previous",
                "product_id": "product-1",
                "offer_id": "offer-1",
                "profit": 45.0 if date_from == "2026-09-13" else 35.0,
            }
        ]
        result["product_count"] = 1
        result["finance_sku_scope_applied"] = True
        result["product_revenue_reconciled"] = True
        return result


class _ExternalEvidence:
    def __init__(self, fail_previous=False):
        self.calls = []
        self.fail_previous = fail_previous

    def load(self, date_from, date_to):
        self.calls.append((date_from, date_to))
        if self.fail_previous and date_to == "2026-09-12":
            raise RuntimeError("private source detail")
        amount = 5.0 if date_from == "2026-09-13" else 3.0
        return {
            "error": False,
            "status": "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "coverage_complete": True,
            "observed_expense_total": amount,
            "complete_expense_total": amount,
        }


class _FinalApplication:
    def apply(self, summary, evidence):
        finalized = dict(summary)
        finalized["profit"] += 7.0
        finalized["tax"] -= 7.0
        finalized["margin_percent"] = finalized["profit"] / 10
        finalized["return_cogs_profit_applied"] = True
        finalized["return_cogs_profit_tax_recomputed"] = True
        finalized["return_cogs_profit_application_amount"] = 7.0
        return {
            "error": False,
            "summary": finalized,
            "evidence": evidence,
        }


class _Base:
    def __init__(self, external, summary_service=None):
        self.product_provider = _Products()
        self.summary_service = summary_service or _Summaries()
        self.return_evidence_service = None
        self.return_cogs_recovery_evidence_service = None
        self.external_expense_evidence_service = external
        self.external_adjustment_inputs = []

    def query(self, period_code=None, **_kwargs):
        request = {
            "error": False,
            "status": "PERIOD_PROFIT_REQUEST_READY",
            "mode": "PRESET",
            "period_code": period_code,
            "date_from": "2026-09-13",
            "date_to": "2026-09-19",
        }
        summary = self.summary_service.calculate(
            request["date_from"], request["date_to"], self.product_provider()
        )
        evidence = self.external_expense_evidence_service.load(
            request["date_from"], request["date_to"]
        )
        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "request": request,
            "summary": summary,
            "coverage": {"error": False, "coverage_status": "COMPLETE"},
            "external_expense_evidence": evidence,
            "external_expense_adjustment": None,
            "previous_summary": None,
            "comparison": None,
        }

    def _external_expense_adjustment(self, summary, evidence):
        self.external_adjustment_inputs.append(summary["profit"])
        amount = evidence["complete_expense_total"]
        adjusted = summary["profit"] - amount
        return {
            "error": False,
            "profit_adjustment_complete": evidence["coverage_complete"],
            "observed_profit_after_external_expenses": adjusted,
            "observed_margin_percent": adjusted / 10,
            "complete_profit_after_external_expenses": adjusted,
            "complete_margin_percent": adjusted / 10,
        }


def _run(external, summary_service=None):
    base = _Base(external, summary_service=summary_service)
    service = PeriodProfitFinalApplicationQueryService(base, _FinalApplication())
    token = set_current_tenant_user_id("owner-1::ozon::store-1")
    try:
        result = service.query(period_code="7D", compare_previous=True)
    finally:
        reset_current_tenant_user_id(token)
    return result, base


def test_production_wrapper_compares_finalized_b_and_e_using_both_period_evidence():
    result, base = _run(_ExternalEvidence())

    assert result["error"] is False
    contract = result["comparison_contract"]
    assert contract["profit_bases"]["B"]["status"] == "CONFIRMED"
    assert contract["profit_bases"]["B"]["current_value"] == 107.0
    assert contract["profit_bases"]["B"]["previous_value"] == 97.0
    assert contract["profit_bases"]["E"]["status"] == "CONFIRMED"
    assert contract["profit_bases"]["E"]["current_value"] == 102.0
    assert contract["profit_bases"]["E"]["previous_value"] == 94.0
    assert result["comparison_metrics"]["metrics"]["profit"]["delta"] == 10
    assert result["comparison_metrics"]["metrics"]["profit_after_external_expenses"]["delta"] == 8
    assert result["comparison_metrics"]["metrics"]["profit_after_external_expenses"]["delta_unit"] == "RUB"
    assert result["profit_bridge"]["B"]["status"] == "UNAVAILABLE"
    assert result["profit_bridge"]["code"] == "PERIOD_PROFIT_COMPARISON_BRIDGE_RECONCILIATION_FAILED"
    assert base.summary_service.calls == [
        ("2026-09-13", "2026-09-19"),
        ("2026-09-06", "2026-09-12"),
    ]
    assert base.external_adjustment_inputs == [107.0, 97.0]


def test_production_wrapper_exposes_sku_contribution_from_finalized_rows():
    result, _base = _run(_ExternalEvidence(), summary_service=_SkuSummaries())

    assert result["error"] is False
    contribution = result["sku_contribution"]
    assert contribution["status"] == "PERIOD_PROFIT_SKU_CONTRIBUTION_READY"
    assert contribution["top_growth"][0]["previous_sku"] == "sku-previous"
    assert contribution["top_growth"][0]["current_sku"] == "sku-current"
    assert contribution["top_growth"][0]["delta"] == 10.0
    assert contribution["store_profit_delta"] == 10.0
    assert contribution["store_minus_sku_delta"] == 0.0


def test_previous_external_expense_failure_preserves_confirmed_b_comparison():
    result, _base = _run(_ExternalEvidence(fail_previous=True))

    assert result["error"] is False
    assert result["comparison_contract"]["profit_bases"]["B"]["status"] == "CONFIRMED"
    assert result["comparison_contract"]["profit_bases"]["E"]["status"] == "UNAVAILABLE"
    assert result["comparison"]["status"] == "PERIOD_PROFIT_COMPARISON_READY"


def test_tax_policy_mismatch_keeps_current_result_and_suppresses_legacy_delta():
    result, _base = _run(
        _ExternalEvidence(),
        summary_service=_Summaries(previous_tax_rate=5.0),
    )

    assert result["error"] is False
    assert result["summary"]["profit"] == 107.0
    assert result["comparison"] is None
    assert result["comparison_status"] == "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
    assert result["comparison_contract"]["profit_bases"]["B"]["status"] == "UNAVAILABLE"
    assert result["comparison_metrics"]["metrics"]["revenue"]["delta"] == 0
    assert result["comparison_metrics"]["metrics"]["profit"]["delta"] is None
    assert result["profit_bridge"]["B"]["status"] == "UNAVAILABLE"
    assert "PERIOD_PROFIT_COMPARISON_TAX_POLICY_MISMATCH" in result["comparison_contract"]["profit_compatibility"]["reason_codes"]
