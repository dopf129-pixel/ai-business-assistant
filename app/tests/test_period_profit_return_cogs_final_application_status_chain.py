import unittest

from services.period_profit_return_cogs_final_application_service import (
    PeriodProfitReturnCogsFinalApplicationService,
)


class StubTaxService:
    def calculate(
        self,
        mode,
        revenue,
        profit,
        tax_rate=None,
        minimum_tax_rate=1.0,
    ):
        return {
            "error": False,
            "mode": mode,
            "tax_amount": 0.0,
            "tax_base": revenue,
            "tax_rate": tax_rate,
            "minimum_tax_rate": minimum_tax_rate,
            "regular_tax": 0.0,
            "minimum_tax": 0.0,
        }


class PeriodProfitReturnCogsFinalApplicationStatusChainTests(unittest.TestCase):
    def setUp(self):
        self.service = PeriodProfitReturnCogsFinalApplicationService(
            StubTaxService(),
            {
                "error": False,
                "configured": True,
                "policy": {
                    "mode": "NONE",
                    "tax_rate": 0.0,
                    "minimum_tax_rate": 1.0,
                },
            },
        )
        self.summary = {
            "error": False,
            "revenue": 1000.0,
            "net_accrual": 400.0,
            "product_cost": 210.0,
            "profit": 130.0,
        }

    def _evidence(self):
        return {
            "error": False,
            "accounting_attribution_evidence_status": (
                "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_READY"
            ),
            "accounting_attribution_evidence_confirmed": True,
            "return_cogs_accounting_recognition_status": (
                "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_READY"
            ),
            "return_cogs_accounting_recognition_evidence_confirmed": True,
            "return_cogs_profit_application_eligibility_status": (
                "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY"
            ),
            "return_cogs_profit_application_eligibility_confirmed": True,
            "return_cogs_profit_application_commit_status": (
                "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_CONFIRMED"
            ),
            "return_cogs_profit_application_commit_confirmed": True,
            "return_cogs_profit_application_eligible_amount": 21.0,
            "return_cogs_profit_application_commit_records": [
                {
                    "error": False,
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "recognition_history_id": 10,
                    "authorization_history_id": 20,
                    "application_commit_confirmed": True,
                    "committed_amount": 21.0,
                    "currency": "RUB",
                    "recovery_accounting_date": "2026-08-20",
                }
            ],
        }

    def test_full_canonical_chain_applies_only_durable_committed_amount(self):
        result = self.service.apply(self.summary, self._evidence())
        self.assertFalse(result["error"])
        self.assertEqual(
            result["status"],
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_APPLIED",
        )
        self.assertTrue(result["return_cogs_profit_applied"])
        self.assertEqual(result["return_cogs_profit_application_amount"], 21.0)
        self.assertEqual(result["summary"]["profit"], 211.0)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_true_commit_boolean_with_ready_not_confirmed_status_fails_closed(self):
        evidence = self._evidence()
        evidence["return_cogs_profit_application_commit_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
        )
        result = self.service.apply(self.summary, evidence)
        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "RETURN_COGS_FINAL_APPLICATION_COMMIT_STATUS_REQUIRED",
        )
        self.assertFalse(result["return_cogs_profit_applied"])
        self.assertFalse(result["executed"])

    def test_blocked_authorization_status_cannot_be_overridden_by_true_boolean(self):
        evidence = self._evidence()
        evidence["return_cogs_profit_application_eligibility_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_BLOCKED"
        )
        result = self.service.apply(self.summary, evidence)
        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "RETURN_COGS_FINAL_APPLICATION_ELIGIBILITY_STATUS_REQUIRED",
        )
        self.assertFalse(result["executed"])

    def test_blocked_recognition_status_cannot_be_overridden_by_true_boolean(self):
        evidence = self._evidence()
        evidence["return_cogs_accounting_recognition_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_BLOCKED"
        )
        result = self.service.apply(self.summary, evidence)
        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "RETURN_COGS_FINAL_APPLICATION_RECOGNITION_STATUS_REQUIRED",
        )
        self.assertFalse(result["executed"])

    def test_partial_accounting_status_cannot_be_overridden_by_true_boolean(self):
        evidence = self._evidence()
        evidence["accounting_attribution_evidence_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_PARTIAL"
        )
        result = self.service.apply(self.summary, evidence)
        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "RETURN_COGS_FINAL_APPLICATION_ACCOUNTING_STATUS_REQUIRED",
        )
        self.assertFalse(result["executed"])

    def test_missing_canonical_status_does_not_mean_ready(self):
        evidence = self._evidence()
        evidence.pop("accounting_attribution_evidence_status")
        result = self.service.apply(self.summary, evidence)
        self.assertTrue(result["error"])
        self.assertEqual(
            result["code"],
            "RETURN_COGS_FINAL_APPLICATION_ACCOUNTING_STATUS_REQUIRED",
        )
        self.assertIsNone(result["return_cogs_profit_application_amount"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
