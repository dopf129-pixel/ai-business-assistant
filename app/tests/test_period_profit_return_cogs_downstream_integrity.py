from copy import deepcopy

from services.period_profit_return_cogs_commit_integrity_service import (
    PeriodProfitReturnCogsCommitIntegrityService,
)
from services.period_profit_return_cogs_final_integrity_service import (
    PeriodProfitReturnCogsFinalIntegrityService,
)


IDENTITY = {"return_id": "ret-1", "posting_number": "post-1", "sku": "42"}


def _recognition(amount=100.0):
    return {
        "error": False,
        "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
        "history_id": 11,
        **IDENTITY,
        "accounting_recognition_confirmed": True,
        "recognition_state": "COGS_RECOVERY_RECOGNIZED",
        "recognized_amount": amount,
        "currency": "RUB",
        "recovery_accounting_date": "2026-09-04",
    }


def _authorization(amount=100.0):
    return {
        "error": False,
        "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY",
        "history_id": 21,
        "recognition_history_id": 11,
        **IDENTITY,
        "application_authorization_confirmed": True,
        "application_state": "PROFIT_APPLICATION_AUTHORIZED",
        "application_already_applied": False,
        "authorized_amount": amount,
        "currency": "RUB",
        "recovery_accounting_date": "2026-09-04",
        "monetary_authority_treatment": "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
        "monetary_authority_non_overlap_confirmed": True,
        "compensation_non_overlap_confirmed": True,
    }


def _commit(amount=100.0):
    return {
        "error": False,
        "application_commit_confirmed": True,
        "recognition_history_id": 11,
        "authorization_history_id": 21,
        **IDENTITY,
        "committed_amount": amount,
        "currency": "RUB",
        "recovery_accounting_date": "2026-09-04",
    }


def _base_result(committed=False):
    return {
        "error": False,
        "candidate_records": [{**IDENTITY, "quantity": 1}],
        "return_cogs_profit_application_eligibility_status": (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
        ),
        "return_cogs_profit_application_eligibility_confirmed": True,
        "return_cogs_accounting_recognition_evidence_records": [_recognition()],
        "return_cogs_profit_application_authorization_records": [_authorization()],
        "return_cogs_profit_application_commit_status": (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED"
            if committed
            else "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
        ),
        "return_cogs_profit_application_commit_ready": not committed,
        "return_cogs_profit_application_commit_confirmed": committed,
        "return_cogs_profit_application_commit_records": [_commit()] if committed else [],
        "return_cogs_profit_application_commit_blockers": [],
        "return_cogs_profit_applied": False,
        "return_cogs_profit_application_amount": None,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


class StubCommitBase:
    def __init__(self, result):
        self.result = result

    def analyze(self, return_evidence, products):
        return deepcopy(self.result)


class StubFinalBase:
    def apply(self, summary, evidence):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_COGS_APPLICATION_APPLIED",
            "summary": dict(summary),
            "evidence": dict(evidence),
            "return_cogs_profit_applied": True,
            "return_cogs_profit_application_amount": 100.0,
            "read_only": True,
            "executed": False,
        }


def _final_evidence():
    result = _base_result(committed=True)
    result.update(
        {
            "accounting_attribution_evidence_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY",
            "accounting_attribution_evidence_confirmed": True,
            "return_cogs_accounting_recognition_status": "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
            "return_cogs_accounting_recognition_evidence_confirmed": True,
            "return_cogs_profit_application_eligible_amount": 100.0,
        }
    )
    return result


def test_commit_integrity_keeps_exact_ready_chain_ready():
    result = PeriodProfitReturnCogsCommitIntegrityService(
        StubCommitBase(_base_result())
    ).analyze({}, [])

    assert result["return_cogs_profit_application_commit_status"] == (
        "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
    )
    assert result["return_cogs_profit_application_integrity_confirmed"] is True
    assert result["read_only"] is True
    assert result["executed"] is False


def test_commit_integrity_rejects_boolean_without_canonical_eligibility_status():
    base = _base_result()
    base["return_cogs_profit_application_eligibility_status"] = (
        "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_BLOCKED"
    )
    result = PeriodProfitReturnCogsCommitIntegrityService(StubCommitBase(base)).analyze({}, [])

    assert result["return_cogs_profit_application_commit_status"] == (
        "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_BLOCKED"
    )
    assert "RETURN_COGS_COMMIT_CANONICAL_ELIGIBILITY_STATUS_REQUIRED" in result[
        "return_cogs_profit_application_commit_blockers"
    ]
    assert result["return_cogs_profit_application_integrity_confirmed"] is False


def test_commit_integrity_rejects_non_finite_money_and_non_overlap_gap():
    base = _base_result()
    base["return_cogs_profit_application_authorization_records"][0]["authorized_amount"] = float("inf")
    base["return_cogs_profit_application_authorization_records"][0][
        "monetary_authority_non_overlap_confirmed"
    ] = None
    result = PeriodProfitReturnCogsCommitIntegrityService(StubCommitBase(base)).analyze({}, [])

    blockers = result["return_cogs_profit_application_commit_blockers"]
    assert "RETURN_COGS_COMMIT_AUTHORIZATION_AMOUNT_REQUIRED" in blockers
    assert "RETURN_COGS_COMMIT_MONETARY_AUTHORITY_NON_OVERLAP_REQUIRED" in blockers
    assert result["return_cogs_profit_application_commit_ready"] is False


def test_commit_integrity_rejects_candidate_subset_coverage():
    base = _base_result()
    base["candidate_records"].append(
        {"return_id": "ret-2", "posting_number": "post-2", "sku": "43", "quantity": 1}
    )
    result = PeriodProfitReturnCogsCommitIntegrityService(StubCommitBase(base)).analyze({}, [])

    blockers = result["return_cogs_profit_application_commit_blockers"]
    assert "RETURN_COGS_COMMIT_RECOGNITION_CANDIDATE_COVERAGE_REQUIRED" in blockers
    assert "RETURN_COGS_COMMIT_AUTHORIZATION_CANDIDATE_COVERAGE_REQUIRED" in blockers


def test_commit_integrity_rechecks_durable_commit_record_error_and_amount():
    base = _base_result(committed=True)
    base["return_cogs_profit_application_commit_records"][0]["error"] = None
    base["return_cogs_profit_application_commit_records"][0]["committed_amount"] = float("nan")
    result = PeriodProfitReturnCogsCommitIntegrityService(StubCommitBase(base)).analyze({}, [])

    blockers = result["return_cogs_profit_application_commit_blockers"]
    assert "RETURN_COGS_COMMIT_DURABLE_RECORD_INVALID" in blockers
    assert result["return_cogs_profit_application_commit_confirmed"] is False


def test_final_integrity_accepts_complete_candidate_to_commit_chain():
    service = PeriodProfitReturnCogsFinalIntegrityService(StubFinalBase())
    result = service.apply({"error": False, "profit": 400.0}, _final_evidence())

    assert result["error"] is False
    assert result["return_cogs_final_candidate_coverage_confirmed"] is True
    assert result["return_cogs_final_monetary_authority_reconfirmed"] is True
    assert result["evidence"]["return_cogs_final_candidate_coverage_confirmed"] is True
    assert result["read_only"] is True
    assert result["executed"] is False


def test_final_integrity_rejects_candidate_subset_even_when_aggregate_chain_matches():
    evidence = _final_evidence()
    evidence["candidate_records"].append(
        {"return_id": "ret-2", "posting_number": "post-2", "sku": "43", "quantity": 1}
    )
    result = PeriodProfitReturnCogsFinalIntegrityService(StubFinalBase()).apply(
        {"error": False}, evidence
    )

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_CANDIDATE_RECOGNITION_COVERAGE_MISMATCH"
    assert result["return_cogs_profit_applied"] is False


def test_final_integrity_rechecks_monetary_authority_non_overlap():
    evidence = _final_evidence()
    evidence["return_cogs_profit_application_authorization_records"][0][
        "compensation_non_overlap_confirmed"
    ] = False
    result = PeriodProfitReturnCogsFinalIntegrityService(StubFinalBase()).apply(
        {"error": False}, evidence
    )

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_COMPENSATION_NON_OVERLAP_REQUIRED"


def test_final_integrity_rejects_non_finite_commit_amount():
    evidence = _final_evidence()
    evidence["return_cogs_profit_application_commit_records"][0]["committed_amount"] = float("inf")
    result = PeriodProfitReturnCogsFinalIntegrityService(StubFinalBase()).apply(
        {"error": False}, evidence
    )

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_CHAIN_AMOUNT_INVALID"


def test_final_integrity_rejects_commit_row_without_explicit_error_false():
    evidence = _final_evidence()
    evidence["return_cogs_profit_application_commit_records"][0]["error"] = None
    result = PeriodProfitReturnCogsFinalIntegrityService(StubFinalBase()).apply(
        {"error": False}, evidence
    )

    assert result["error"] is True
    assert result["code"] == "RETURN_COGS_FINAL_COMMIT_RECORD_INVALID"
