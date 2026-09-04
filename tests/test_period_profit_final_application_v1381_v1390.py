from services.period_profit_return_cogs_final_application_service import (
    PeriodProfitReturnCogsFinalApplicationService,
)
from services.period_profit_tax_policy_summary_service import (
    PeriodProfitTaxPolicySummaryService,
)
from services.tax_service import TaxService


def _policy(mode, rate=None, minimum=1.0):
    return {
        "error": False,
        "configured": True,
        "policy": {
            "mode": mode,
            "tax_rate": rate,
            "minimum_tax_rate": minimum,
        },
    }


def _summary(tax=60.0, profit=340.0):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "product_cost": 300.0,
        "tax": tax,
        "profit": profit,
        "margin_percent": round(profit / 10.0, 2),
        "products": [],
        "account_level_ozon_accruals_included": True,
        "profit_scope": "OLD",
    }


def _committed_evidence(amount=100.0):
    return {
        "error": False,
        "return_cogs_profit_application_eligibility_confirmed": True,
        "return_cogs_profit_application_eligible_amount": amount,
        "return_cogs_profit_application_commit_confirmed": True,
        "return_cogs_profit_application_commit_records": [
            {
                "error": False,
                "application_commit_confirmed": True,
                "recognition_history_id": 11,
                "return_id": "ret-1",
                "posting_number": "post-1",
                "sku": "42",
                "committed_amount": amount,
                "currency": "RUB",
            }
        ],
        "return_cogs_profit_applied": False,
        "return_cogs_profit_application_amount": None,
        "profit_adjustment_allowed": False,
        "read_only": True,
        "executed": False,
    }


def test_v1381_none_tax_applies_committed_return_cogs_once_read_only():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("NONE"))
    first = service.apply(_summary(tax=0.0, profit=400.0), _committed_evidence())
    second = service.apply(_summary(tax=0.0, profit=400.0), _committed_evidence())

    for result in (first, second):
        assert result["error"] is False
        assert result["return_cogs_profit_applied"] is True
        assert result["return_cogs_profit_application_amount"] == 100.0
        assert result["summary"]["period_profit_before_return_cogs"] == 400.0
        assert result["summary"]["tax"] == 0.0
        assert result["summary"]["profit"] == 500.0
        assert result["summary"]["margin_percent"] == 50.0
        assert result["evidence"]["profit_adjustment_allowed"] is True
        assert result["read_only"] is True
        assert result["executed"] is False


def test_v1382_usn_income_keeps_revenue_tax_base_when_return_cogs_is_applied():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("USN_INCOME", 6.0))
    result = service.apply(_summary(tax=60.0, profit=340.0), _committed_evidence())

    assert result["error"] is False
    assert result["summary"]["tax"] == 60.0
    assert result["summary"]["tax_base"] == 1000.0
    assert result["summary"]["profit"] == 440.0


def test_v1383_usn_income_minus_expenses_recomputes_regular_and_minimum_tax():
    service = PeriodProfitReturnCogsFinalApplicationService(
        TaxService(), _policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0)
    )
    result = service.apply(_summary(tax=60.0, profit=340.0), _committed_evidence())

    assert result["error"] is False
    assert result["summary"]["tax_base"] == 500.0
    assert result["summary"]["regular_tax"] == 75.0
    assert result["summary"]["minimum_tax"] == 10.0
    assert result["summary"]["tax"] == 75.0
    assert result["summary"]["profit"] == 425.0


def test_v1384_missing_commit_does_not_infer_zero_adjustment():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("NONE"))
    evidence = _committed_evidence()
    evidence["return_cogs_profit_application_commit_confirmed"] = False
    evidence["return_cogs_profit_application_commit_records"] = []
    result = service.apply(_summary(tax=0.0, profit=400.0), evidence)

    assert result["error"] is False
    assert result["return_cogs_profit_applied"] is False
    assert result["return_cogs_profit_application_amount"] is None
    assert result["summary"]["return_cogs_profit_application_amount"] is None
    assert result["summary"]["profit"] == 400.0


def test_v1385_commit_amount_or_currency_conflict_fails_closed():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("NONE"))
    mismatch = _committed_evidence(100.0)
    mismatch["return_cogs_profit_application_eligible_amount"] = 90.0
    bad_currency = _committed_evidence(100.0)
    bad_currency["return_cogs_profit_application_commit_records"][0]["currency"] = "USD"

    assert service.apply(_summary(), mismatch)["error"] is True
    assert service.apply(_summary(), bad_currency)["error"] is True


class BaseSummary:
    def calculate(self, date_from, date_to, products):
        return {
            **_summary(tax=0.0, profit=400.0),
            "date_from": date_from,
            "date_to": date_to,
            "products": [
                {
                    "error": False,
                    "sku": "42",
                    "offer_id": "offer-42",
                    "revenue": 1000.0,
                    "net_accrual": 700.0,
                    "product_cost": 300.0,
                    "tax": 0.0,
                    "profit": 400.0,
                    "margin_percent": 40.0,
                }
            ],
        }


def test_v1386_policy_summary_supports_usn_income_minus_expenses():
    service = PeriodProfitTaxPolicySummaryService(
        BaseSummary(),
        TaxService(),
        _policy("USN_INCOME_MINUS_EXPENSES", 15.0, 1.0),
    )
    result = service.calculate("2026-09-01", "2026-09-04", [{"sku": "42"}])

    assert result["error"] is False
    assert result["tax"] == 60.0
    assert result["regular_tax"] == 60.0
    assert result["minimum_tax"] == 10.0
    assert result["profit"] == 340.0
    assert result["products"][0]["tax"] == 60.0
    assert result["tax_policy_mode"] == "USN_INCOME_MINUS_EXPENSES"


def test_v1387_policy_summary_rejects_unknown_monetary_input_instead_of_zero():
    class UnknownBase(BaseSummary):
        def calculate(self, date_from, date_to, products):
            result = super().calculate(date_from, date_to, products)
            result["net_accrual"] = None
            return result

    result = PeriodProfitTaxPolicySummaryService(
        UnknownBase(), TaxService(), _policy("USN_INCOME", 6.0)
    ).calculate("2026-09-01", "2026-09-04", [{"sku": "42"}])

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_TAX_INPUT_INVALID"


def test_v1388_final_application_preserves_account_monetary_authority_and_no_ozon_mutation():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("USN_INCOME", 6.0))
    result = service.apply(_summary(tax=60.0, profit=340.0), _committed_evidence())

    assert result["summary"]["net_accrual"] == 700.0
    assert result["summary"]["product_cost"] == 300.0
    assert result["summary"]["return_cogs_profit_application_amount"] == 100.0
    assert result["summary"]["profit_scope"] == "OZON_ACCOUNT_ACCRUALS_COST_COMMITTED_RETURN_COGS_AND_CONFIGURED_TAX_V4"
    assert result["read_only"] is True
    assert result["executed"] is False


def test_v1389_tax_policy_modes_have_deterministic_period_profit_results():
    cases = [
        ("NONE", None, 0.0, 500.0),
        ("USN_INCOME", 6.0, 60.0, 440.0),
        ("USN_INCOME_MINUS_EXPENSES", 15.0, 75.0, 425.0),
    ]
    for mode, rate, expected_tax, expected_profit in cases:
        result = PeriodProfitReturnCogsFinalApplicationService(
            TaxService(), _policy(mode, rate, 1.0)
        ).apply(_summary(), _committed_evidence())
        assert result["summary"]["tax"] == expected_tax
        assert result["summary"]["profit"] == expected_profit


def test_v1390_application_requires_durable_commit_not_merely_eligibility():
    service = PeriodProfitReturnCogsFinalApplicationService(TaxService(), _policy("NONE"))
    evidence = _committed_evidence()
    evidence["return_cogs_profit_application_commit_confirmed"] = False
    evidence["return_cogs_profit_application_commit_records"] = []
    evidence["return_cogs_profit_application_eligibility_confirmed"] = True
    result = service.apply(_summary(tax=0.0, profit=400.0), evidence)

    assert result["status"] == "PERIOD_PROFIT_RETURN_COGS_APPLICATION_NOT_APPLIED"
    assert result["summary"]["profit"] == 400.0
    assert result["return_cogs_profit_application_amount"] is None
