from services.period_profit_return_cogs_recovery_amount_evidence_service import (
    PeriodProfitReturnCogsRecoveryAmountEvidenceService,
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


def _candidate(return_id="1", quantity=2, cost=21.0, value=42.0):
    return {
        "return_id": return_id,
        "posting_number": f"p-{return_id}",
        "sku": "42",
        "quantity": quantity,
        "historical_cost_per_unit": cost,
        "candidate_value_at_historical_cost": value,
    }


def _ready_base():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
        "candidate_records": [_candidate()],
        "return_cogs_accounting_readiness_confirmed": True,
        "period_cogs_recovery_confirmed": False,
        "accounting_cogs_recovery_confirmed": False,
        "confirmed_cogs_recovery_amount": 0.0,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _analyze(overrides=None, value=None):
    return PeriodProfitReturnCogsRecoveryAmountEvidenceService(
        Base(overrides=overrides, value=value)
    ).analyze({}, [])


def test_v1331_accounting_ready_candidate_stages_historical_cost_amount_only():
    result = _analyze()

    assert result["return_cogs_recovery_amount_evidence_confirmed"] is True
    assert result["return_cogs_recovery_amount_evidence_amount"] == 42.0
    assert result["return_cogs_recovery_amount_evidence_currency"] == "RUB"
    assert result["return_cogs_recovery_amount_basis"] == (
        "HISTORICAL_COST_PER_UNIT_X_RETURN_QUANTITY"
    )
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert result["profit_adjustment_allowed"] is False


def test_v1332_multiple_candidates_sum_only_explicit_historical_values():
    result = _analyze(
        {
            "candidate_records": [
                _candidate("1", quantity=2, cost=21.0, value=42.0),
                _candidate("2", quantity=3, cost=10.0, value=30.0),
            ]
        }
    )

    assert result["return_cogs_recovery_amount_evidence_confirmed"] is True
    assert result["return_cogs_recovery_amount_evidence_amount"] == 72.0
    assert result["return_cogs_recovery_amount_evidence_valid_record_count"] == 2


def test_v1333_accounting_readiness_false_blocks_amount_without_zero_inference():
    result = _analyze({"return_cogs_accounting_readiness_confirmed": False})

    assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
    assert result["return_cogs_recovery_amount_evidence_amount"] is None
    assert "RETURN_COGS_ACCOUNTING_READINESS_REQUIRED" in result[
        "return_cogs_recovery_amount_evidence_blockers"
    ]


def test_v1334_missing_or_malformed_historical_cost_blocks_whole_amount():
    for cost in (None, True, "bad", -1.0, float("inf")):
        result = _analyze({"candidate_records": [_candidate(cost=cost)]})
        assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
        assert result["return_cogs_recovery_amount_evidence_amount"] is None
        assert "RETURN_COGS_AMOUNT_HISTORICAL_COST_REQUIRED" in result[
            "return_cogs_recovery_amount_evidence_blockers"
        ]


def test_v1335_missing_or_invalid_quantity_blocks_whole_amount():
    for quantity in (None, True, 0, -1, 1.5):
        result = _analyze({"candidate_records": [_candidate(quantity=quantity)]})
        assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
        assert result["return_cogs_recovery_amount_evidence_amount"] is None
        assert "RETURN_COGS_AMOUNT_QUANTITY_REQUIRED" in result[
            "return_cogs_recovery_amount_evidence_blockers"
        ]


def test_v1336_historical_candidate_value_must_match_cost_times_quantity():
    result = _analyze(
        {"candidate_records": [_candidate(quantity=2, cost=21.0, value=41.0)]}
    )

    assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
    assert result["return_cogs_recovery_amount_evidence_amount"] is None
    assert "RETURN_COGS_AMOUNT_HISTORICAL_VALUE_MISMATCH" in result[
        "return_cogs_recovery_amount_evidence_blockers"
    ]


def test_v1337_explicit_zero_historical_cost_is_valid_zero_amount_evidence():
    result = _analyze(
        {"candidate_records": [_candidate(quantity=2, cost=0.0, value=0.0)]}
    )

    assert result["return_cogs_recovery_amount_evidence_confirmed"] is True
    assert result["return_cogs_recovery_amount_evidence_amount"] == 0.0
    assert result["confirmed_cogs_recovery_amount"] == 0.0


def test_v1338_empty_or_invalid_candidate_identity_fails_closed():
    empty = _analyze({"candidate_records": []})
    invalid = _analyze(
        {
            "candidate_records": [
                {
                    "return_id": "",
                    "posting_number": "p-1",
                    "sku": "42",
                    "quantity": 1,
                    "historical_cost_per_unit": 21.0,
                    "candidate_value_at_historical_cost": 21.0,
                }
            ]
        }
    )

    assert empty["return_cogs_recovery_amount_evidence_amount"] is None
    assert "RETURN_COGS_AMOUNT_CANDIDATES_REQUIRED" in empty[
        "return_cogs_recovery_amount_evidence_blockers"
    ]
    assert invalid["return_cogs_recovery_amount_evidence_amount"] is None
    assert "RETURN_COGS_AMOUNT_CANDIDATE_IDENTITY_REQUIRED" in invalid[
        "return_cogs_recovery_amount_evidence_blockers"
    ]


def test_v1339_one_invalid_candidate_blocks_aggregate_without_partial_amount_claim():
    result = _analyze(
        {
            "candidate_records": [
                _candidate("1", quantity=2, cost=21.0, value=42.0),
                _candidate("2", quantity=1, cost=10.0, value=None),
            ]
        }
    )

    assert result["return_cogs_recovery_amount_evidence_valid_record_count"] == 1
    assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
    assert result["return_cogs_recovery_amount_evidence_amount"] is None
    assert "RETURN_COGS_AMOUNT_HISTORICAL_VALUE_REQUIRED" in result[
        "return_cogs_recovery_amount_evidence_blockers"
    ]


def test_v1340_malformed_or_exceptional_base_never_promotes_money_or_execution():
    for result in (
        _analyze(value=[]),
        _analyze(value=RuntimeError("boom")),
    ):
        assert result["error"] is True
        assert result["return_cogs_recovery_amount_evidence_confirmed"] is False
        assert result["return_cogs_recovery_amount_evidence_amount"] is None
        assert result["period_cogs_recovery_confirmed"] is False
        assert result["accounting_cogs_recovery_confirmed"] is False
        assert result["confirmed_cogs_recovery_amount"] == 0.0
        assert result["profit_adjustment_allowed"] is False
        assert result["automatic_recovery_allowed"] is False
        assert result["read_only"] is True
        assert result["executed"] is False
