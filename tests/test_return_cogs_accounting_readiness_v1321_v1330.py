from services.period_profit_return_cogs_accounting_readiness_service import (
    PeriodProfitReturnCogsAccountingReadinessService,
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


def _ready_base():
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
        "candidate_records": [
            {
                "return_id": "1",
                "posting_number": "p-1",
                "sku": "42",
                "quantity": 1,
            }
        ],
        "return_sample_complete": True,
        "originating_sale_period_confirmed": True,
        "historical_cost_basis_confirmed": True,
        "saleable_inventory_recovery_confirmed": True,
        "originating_sale_quantity_evidence_confirmed": True,
        "recovery_period_attribution_evidence_confirmed": True,
        "compensation_accounting_treatment_evidence_confirmed": True,
        "compensation_double_count_clear": True,
        "accounting_attribution_evidence_confirmed": True,
        "originating_sale_quantity_confirmed": False,
        "originating_sale_quantity_gate_promoted": False,
        "recovery_period_attribution_confirmed": False,
        "compensation_accounting_treatment_confirmed": False,
        "period_cogs_recovery_confirmed": False,
        "accounting_cogs_recovery_confirmed": False,
        "confirmed_cogs_recovery_amount": 0.0,
        "profit_adjustment_allowed": False,
        "automatic_recovery_allowed": False,
        "read_only": True,
        "executed": False,
    }


def _analyze(overrides=None, value=None):
    return PeriodProfitReturnCogsAccountingReadinessService(
        Base(overrides=overrides, value=value)
    ).analyze({}, [])


def test_v1321_complete_independent_evidence_promotes_readiness_gates_only():
    result = _analyze()

    assert result["originating_sale_quantity_confirmed"] is True
    assert result["originating_sale_quantity_gate_promoted"] is True
    assert result["recovery_period_attribution_confirmed"] is True
    assert result["compensation_accounting_treatment_confirmed"] is True
    assert result["return_cogs_accounting_readiness_confirmed"] is True
    assert result["return_cogs_accounting_readiness_blockers"] == []
    assert result["period_cogs_recovery_confirmed"] is False
    assert result["accounting_cogs_recovery_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert result["profit_adjustment_allowed"] is False
    assert result["automatic_recovery_allowed"] is False


def test_v1322_missing_quantity_source_blocks_quantity_gate_and_readiness():
    result = _analyze({"originating_sale_quantity_evidence_confirmed": False})

    assert result["originating_sale_quantity_confirmed"] is False
    assert result["originating_sale_quantity_gate_promoted"] is False
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "ORIGINATING_SALE_QUANTITY_EVIDENCE_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1323_missing_originating_sale_period_blocks_overall_readiness():
    result = _analyze({"originating_sale_period_confirmed": False})

    assert result["originating_sale_quantity_confirmed"] is True
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "ORIGINATING_SALE_PERIOD_CONFIRMED_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1324_missing_historical_cost_blocks_overall_readiness():
    result = _analyze({"historical_cost_basis_confirmed": False})

    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "HISTORICAL_COST_BASIS_CONFIRMED_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1325_missing_saleable_inventory_recovery_blocks_readiness():
    result = _analyze({"saleable_inventory_recovery_confirmed": False})

    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "SALEABLE_INVENTORY_RECOVERY_CONFIRMED_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1326_missing_period_attribution_blocks_period_gate_and_readiness():
    result = _analyze({"recovery_period_attribution_evidence_confirmed": False})

    assert result["recovery_period_attribution_confirmed"] is False
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "RECOVERY_PERIOD_ATTRIBUTION_EVIDENCE_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1327_missing_compensation_treatment_blocks_compensation_gate():
    result = _analyze(
        {"compensation_accounting_treatment_evidence_confirmed": False}
    )

    assert result["compensation_accounting_treatment_confirmed"] is False
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "COMPENSATION_ACCOUNTING_TREATMENT_EVIDENCE_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1328_double_count_not_clear_blocks_compensation_gate():
    result = _analyze({"compensation_double_count_clear": False})

    assert result["compensation_accounting_treatment_confirmed"] is False
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "COMPENSATION_DOUBLE_COUNT_CLEARANCE_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1329_empty_candidate_set_never_becomes_accounting_ready():
    result = _analyze({"candidate_records": []})

    assert result["originating_sale_quantity_confirmed"] is False
    assert result["recovery_period_attribution_confirmed"] is False
    assert result["compensation_accounting_treatment_confirmed"] is False
    assert result["return_cogs_accounting_readiness_confirmed"] is False
    assert "RETURN_COGS_CANDIDATES_REQUIRED" in result[
        "return_cogs_accounting_readiness_blockers"
    ]


def test_v1330_malformed_or_exceptional_base_fails_closed_without_profit_change():
    malformed = _analyze(value=[])
    exceptional = _analyze(value=RuntimeError("boom"))

    for result in (malformed, exceptional):
        assert result["error"] is True
        assert result["originating_sale_quantity_confirmed"] is False
        assert result["recovery_period_attribution_confirmed"] is False
        assert result["compensation_accounting_treatment_confirmed"] is False
        assert result["return_cogs_accounting_readiness_confirmed"] is False
        assert result["period_cogs_recovery_confirmed"] is False
        assert result["accounting_cogs_recovery_confirmed"] is False
        assert result["confirmed_cogs_recovery_amount"] == 0.0
        assert result["profit_adjustment_allowed"] is False
        assert result["automatic_recovery_allowed"] is False
        assert result["read_only"] is True
        assert result["executed"] is False
