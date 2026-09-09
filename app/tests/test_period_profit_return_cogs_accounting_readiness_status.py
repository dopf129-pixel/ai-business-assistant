import unittest

from services.period_profit_return_cogs_accounting_readiness_service import (
    PeriodProfitReturnCogsAccountingReadinessService,
)


class StubAccountingEvidenceService:
    def __init__(self, result):
        self.result = result

    def analyze(self, return_evidence, products):
        return dict(self.result)


class PeriodProfitReturnCogsAccountingReadinessStatusTests(unittest.TestCase):
    def _base(self, status="PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"):
        return {
            "error": False,
            "candidate_records": [
                {
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
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
            "accounting_attribution_evidence_status": status,
        }

    def _analyze(self, base):
        return PeriodProfitReturnCogsAccountingReadinessService(
            StubAccountingEvidenceService(base)
        ).analyze({}, [])

    def test_canonical_ready_status_allows_readiness_when_all_facts_are_proven(self):
        result = self._analyze(self._base())
        self.assertTrue(result["return_cogs_accounting_evidence_status_confirmed"])
        self.assertTrue(result["return_cogs_accounting_readiness_confirmed"])
        self.assertEqual(
            result["return_cogs_accounting_readiness_status"],
            "RETURN_COGS_ACCOUNTING_READINESS_READY",
        )
        self.assertNotIn(
            "ACCOUNTING_ATTRIBUTION_EVIDENCE_READY_STATUS_REQUIRED",
            result["return_cogs_accounting_readiness_blockers"],
        )
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_partial_status_blocks_even_when_all_confirmation_booleans_are_true(self):
        result = self._analyze(
            self._base("PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_PARTIAL")
        )
        self.assertFalse(result["return_cogs_accounting_evidence_status_confirmed"])
        self.assertFalse(result["return_cogs_accounting_readiness_confirmed"])
        self.assertEqual(
            result["return_cogs_accounting_readiness_status"],
            "RETURN_COGS_ACCOUNTING_READINESS_BLOCKED",
        )
        self.assertIn(
            "ACCOUNTING_ATTRIBUTION_EVIDENCE_READY_STATUS_REQUIRED",
            result["return_cogs_accounting_readiness_blockers"],
        )
        self.assertEqual(result["confirmed_cogs_recovery_amount"], 0.0)
        self.assertFalse(result["profit_adjustment_allowed"])

    def test_missing_status_blocks_even_when_all_confirmation_booleans_are_true(self):
        base = self._base()
        base.pop("accounting_attribution_evidence_status")
        result = self._analyze(base)
        self.assertFalse(result["return_cogs_accounting_evidence_status_confirmed"])
        self.assertFalse(result["return_cogs_accounting_readiness_confirmed"])
        self.assertIn(
            "ACCOUNTING_ATTRIBUTION_EVIDENCE_READY_STATUS_REQUIRED",
            result["return_cogs_accounting_readiness_blockers"],
        )

    def test_unavailable_status_blocks_even_when_all_confirmation_booleans_are_true(self):
        result = self._analyze(
            self._base("PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_UNAVAILABLE")
        )
        self.assertFalse(result["return_cogs_accounting_readiness_confirmed"])
        self.assertFalse(result["period_cogs_recovery_confirmed"])
        self.assertFalse(result["accounting_cogs_recovery_confirmed"])
        self.assertFalse(result["automatic_recovery_allowed"])
        self.assertFalse(result["executed"])

    def test_unknown_status_is_not_normalized_to_ready(self):
        result = self._analyze(self._base("unknown"))
        self.assertFalse(result["return_cogs_accounting_evidence_status_confirmed"])
        self.assertFalse(result["return_cogs_accounting_readiness_confirmed"])
        self.assertEqual(result["confirmed_cogs_recovery_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
