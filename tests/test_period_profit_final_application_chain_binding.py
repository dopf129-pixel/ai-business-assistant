from copy import deepcopy

from services.period_profit_return_cogs_final_application_service import (
    PeriodProfitReturnCogsFinalApplicationService,
)
from services.tax_service import TaxService


def _policy():
    return {
        "error": False,
        "configured": True,
        "policy": {"mode": "NONE", "tax_rate": None, "minimum_tax_rate": 1.0},
    }


def _summary():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_SUMMARY_READY",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "product_cost": 300.0,
        "tax": 0.0,
        "profit": 400.0,
        "margin_percent": 40.0,
        "products": [],
    }


def _evidence():
    return {
        "error": False,
        "accounting_attribution_evidence_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY",
        "accounting_attribution_evidence_confirmed": True,
        "return_cogs_accounting_recognition_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "return_cogs_accounting_recognition_evidence_confirmed": True,
        "return_cogs_accounting_recognition_evidence_records": [
            {
                "error": False,
                "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
                "accounting_recognition_confirmed": True,
                "recognition_state": "COGS_RECOVERY_RECOGNIZED",
                "history_id": 11,
                "return_id": "ret-1",
                "posting_number": "post-1",
                "sku": "42",
                "recognized_amount": 100.0,
                "currency": "RUB",
                "recovery_accounting_date": "2026-09-04",
            }
        ],
        "return_cogs_profit_application_eligibility_status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY",
        "return_cogs_profit_application_eligibility_confirmed": True,
        "return_cogs_profit_application_eligible_amount": 100.0,
        "return_cogs_profit_application_authorization_records": [
            {
                "error": False,
                "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY",
                "application_authorization_confirmed": True,
                "application_state": "PROFIT_APPLICATION_AUTHORIZED",
                "application_already_applied": False,
                "history_id": 21,
                "recognition_history_id": 11,
                "return_id": "ret-1",
                "posting_number": "post-1",
                "sku": "42",
                "authorized_amount": 100.0,
                "currency": "RUB",
                "recovery_accounting_date": "2026-09-04",
            }
        ],
        "return_cogs_profit_application_commit_status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED",
        "return_cogs_profit_application_commit_confirmed": True,
        "return_cogs_profit_application_commit_records": [
            {
                "error": False,
                "application_commit_confirmed": True,
                "recognition_history_id": 11,
                "authorization_history_id": 21,
                "return_id": "ret-1",
                "posting_number": "post-1",
                "sku": "42",
                "committed_amount": 100.0,
                "currency": "RUB",
                "recovery_accounting_date": "2026-09-04",
            }
        ],
        "return_cogs_profit_applied": False,
        "read_only": True,
        "executed": False,
    }


def _apply(evidence):
    return PeriodProfitReturnCogsFinalApplicationService(
        TaxService(), _policy()
    ).apply(_summary(), evidence)


def test_final_application_requires_recognition_record_binding():
    evidence = _evidence()
    evidence["return_cogs_profit_application_commit_records"][0]["recognition_history_id"] = 99

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_COMMIT_RECOGNITION_BINDING_REQUIRED"
    assert result["return_cogs_profit_applied"] is False


def test_final_application_requires_authorization_record_binding():
    evidence = _evidence()
    evidence["return_cogs_profit_application_commit_records"][0]["authorization_history_id"] = 99

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_COMMIT_AUTHORIZATION_BINDING_REQUIRED"


def test_final_application_rejects_cross_stage_identity_mismatch():
    evidence = _evidence()
    evidence["return_cogs_profit_application_authorization_records"][0]["sku"] = "777"

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_CHAIN_IDENTITY_MISMATCH"


def test_final_application_rejects_cross_stage_amount_mismatch():
    evidence = _evidence()
    evidence["return_cogs_accounting_recognition_evidence_records"][0]["recognized_amount"] = 99.0

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_CHAIN_AMOUNT_MISMATCH"


def test_final_application_rejects_cross_stage_date_mismatch():
    evidence = _evidence()
    evidence["return_cogs_profit_application_authorization_records"][0]["recovery_accounting_date"] = "2026-09-03"

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_CHAIN_DATE_MISMATCH"


def test_final_application_requires_complete_recognition_and_authorization_coverage():
    evidence = _evidence()
    second = deepcopy(evidence["return_cogs_accounting_recognition_evidence_records"][0])
    second.update({"history_id": 12, "return_id": "ret-2", "posting_number": "post-2", "sku": "43"})
    evidence["return_cogs_accounting_recognition_evidence_records"].append(second)

    result = _apply(evidence)

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_APPLICATION_RECOGNITION_COVERAGE_MISMATCH"


def test_final_application_complete_bound_chain_applies_read_only():
    result = _apply(_evidence())

    assert result["error"] is False
    assert result["status"] == "PERIOD_PROFIT_RETURN_COGS_APPLICATION_APPLIED"
    assert result["return_cogs_profit_application_amount"] == 100.0
    assert result["return_cogs_final_application_chain_bound"] is True
    assert result["summary"]["profit"] == 500.0
    assert result["read_only"] is True
    assert result["executed"] is False
