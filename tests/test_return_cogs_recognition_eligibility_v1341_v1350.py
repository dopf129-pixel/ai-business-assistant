from services.period_profit_return_cogs_recognition_eligibility_service import (
    PeriodProfitReturnCogsRecognitionEligibilityService,
)


class Base:
    def __init__(self, overrides=None, value=None):
        self.overrides = dict(overrides or {})
        self.value = value

    def analyze(self, return_evidence, products):
        if isinstance(self.value, Exception):
            raise self.value
        if self.value is not None:
            return self.value
        result = _ready_base()
        result.update(self.overrides)
        return result


def _identity(return_id="1"):
    return {
        "return_id": return_id,
        "posting_number": f"p-{return_id}",
        "sku": "42",
    }


def _candidate(return_id="1"):
    row = _identity(return_id)
    row.update({
        "quantity": 2,
        "historical_cost_per_unit": 21.0,
        "candidate_value_at_historical_cost": 42.0,
    })
    return row


def _amount_record(return_id="1", amount=42.0):
    row = _identity(return_id)
    row.update({
        "status": "RETURN_COGS_AMOUNT_CANDIDATE_READY",
        "staged_recovery_amount": amount,
    })
    return row


def _attribution(return_id="1"):
    row = _identity(return_id)
    row.update({
        "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
        "recovery_accounting_date": "2026-08-20",
        "recovery_accounting_period_matches_request": True,
        "compensation_state": "NO_COMPENSATION_CONFIRMED",
        "compensation_double_count_clear": True,
    })
    return row


def _ready_base():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
        "candidate_records": [_candidate()],
        "accounting_attribution_evidence_records": [_attribution()],
        "return_cogs_accounting_readiness_confirmed": True,
        "return_cogs_recovery_amount_evidence_confirmed": True,
        "return_cogs_recovery_amount_evidence_amount": 42.0,
        "return_cogs_recovery_amount_evidence_currency": "RUB",
        "return_cogs_recovery_amount_evidence_records": [_amount_record()],
        "period_cogs_recovery_confirmed": False,
        "accounting_cogs_recovery_confirmed": False,
        "confirmed_cogs_recovery_amount": 0.0,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _analyze(overrides=None, value=None):
    return PeriodProfitReturnCogsRecognitionEligibilityService(
        Base(overrides=overrides, value=value)
    ).analyze({}, [])


def test_v1341_exact_candidate_amount_and_attribution_identity_is_eligible_only():
    result = _analyze()

    assert result["return_cogs_recognition_eligibility_confirmed"] is True
    assert result["return_cogs_recognition_eligible_amount"] == 42.0
    assert result["return_cogs_recognition_eligible_currency"] == "RUB"
    assert result["return_cogs_recognition_eligibility_blockers"] == []
    assert result["period_cogs_recovery_confirmed"] is False
    assert result["accounting_cogs_recovery_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert result["profit_adjustment_allowed"] is False


def test_v1342_missing_accounting_readiness_blocks_recognition_eligibility():
    result = _analyze({"return_cogs_accounting_readiness_confirmed": False})

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert result["return_cogs_recognition_eligible_amount"] is None
    assert "RETURN_COGS_ACCOUNTING_READINESS_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1343_missing_amount_evidence_blocks_without_zero_inference():
    result = _analyze(
        {
            "return_cogs_recovery_amount_evidence_confirmed": False,
            "return_cogs_recovery_amount_evidence_amount": None,
        }
    )

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert result["return_cogs_recognition_eligible_amount"] is None
    assert "RETURN_COGS_RECOVERY_AMOUNT_EVIDENCE_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1344_non_rub_or_invalid_staged_amount_blocks_eligibility():
    currency = _analyze({"return_cogs_recovery_amount_evidence_currency": "USD"})
    invalid = _analyze({"return_cogs_recovery_amount_evidence_amount": True})

    assert currency["return_cogs_recognition_eligibility_confirmed"] is False
    assert "RETURN_COGS_STAGED_AMOUNT_CURRENCY_RUB_REQUIRED" in currency[
        "return_cogs_recognition_eligibility_blockers"
    ]
    assert invalid["return_cogs_recognition_eligible_amount"] is None
    assert "RETURN_COGS_STAGED_AMOUNT_REQUIRED" in invalid[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1345_amount_records_must_cover_exact_candidate_identity():
    result = _analyze(
        {"return_cogs_recovery_amount_evidence_records": [_amount_record("2")]}
    )

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert "RETURN_COGS_AMOUNT_IDENTITY_COVERAGE_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1346_attribution_records_must_cover_exact_candidate_identity():
    result = _analyze({"accounting_attribution_evidence_records": [_attribution("2")]})

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert "RETURN_COGS_ATTRIBUTION_IDENTITY_COVERAGE_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1347_each_attribution_must_match_requested_period():
    attribution = _attribution()
    attribution["recovery_accounting_period_matches_request"] = False
    result = _analyze({"accounting_attribution_evidence_records": [attribution]})

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert "RETURN_COGS_RECOGNITION_PERIOD_MATCH_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1348_compensation_double_count_must_be_explicitly_clear():
    attribution = _attribution()
    attribution["compensation_state"] = "COMPENSATION_PRESENT"
    attribution["compensation_double_count_clear"] = False
    result = _analyze({"accounting_attribution_evidence_records": [attribution]})

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert "RETURN_COGS_COMPENSATION_DOUBLE_COUNT_CLEAR_REQUIRED" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1349_staged_total_must_reconcile_to_candidate_amount_records():
    result = _analyze({"return_cogs_recovery_amount_evidence_amount": 41.0})

    assert result["return_cogs_recognition_eligibility_confirmed"] is False
    assert result["return_cogs_recognition_eligible_amount"] is None
    assert "RETURN_COGS_STAGED_AMOUNT_TOTAL_MISMATCH" in result[
        "return_cogs_recognition_eligibility_blockers"
    ]


def test_v1350_malformed_or_exceptional_base_never_recognizes_or_adjusts_profit():
    for result in (
        _analyze(value=[]),
        _analyze(value=RuntimeError("boom")),
    ):
        assert result["error"] is True
        assert result["return_cogs_recognition_eligibility_confirmed"] is False
        assert result["return_cogs_recognition_eligible_amount"] is None
        assert result["period_cogs_recovery_confirmed"] is False
        assert result["accounting_cogs_recovery_confirmed"] is False
        assert result["confirmed_cogs_recovery_amount"] == 0.0
        assert result["profit_adjustment_allowed"] is False
        assert result["automatic_recovery_allowed"] is False
        assert result["read_only"] is True
        assert result["executed"] is False
