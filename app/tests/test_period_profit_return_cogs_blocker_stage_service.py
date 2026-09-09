import unittest

from services.period_profit_return_cogs_blocker_stage_service import (
    PeriodProfitReturnCogsBlockerStageService,
)


class PeriodProfitReturnCogsBlockerStageServiceTests(unittest.TestCase):
    def _candidate(self, ready=True, state="SALEABLE_RESTORED"):
        return {
            "return_id": "r-1",
            "posting_number": "p-1",
            "sku": "s-1",
            "quantity": 1,
            "inventory_recovery_state": state,
            "inventory_recovery_evidence_status": (
                "RETURN_INVENTORY_RECOVERY_READY"
                if ready
                else "RETURN_INVENTORY_RECOVERY_UNAVAILABLE"
            ),
        }

    def _base(self):
        return {
            "candidate_records": [self._candidate()],
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
            "return_cogs_profit_applied": True,
        }

    def test_inventory_is_first_gate_even_when_later_gates_are_false(self):
        evidence = self._base()
        evidence["candidate_records"] = [self._candidate(ready=False)]
        evidence["accounting_attribution_evidence_confirmed"] = False
        evidence["return_cogs_accounting_recognition_evidence_confirmed"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(result["stage"], PeriodProfitReturnCogsBlockerStageService.INVENTORY)
        self.assertTrue(result["blocker_present"])
        self.assertEqual(result["records"][0]["return_id"], "r-1")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_accounting_precedes_recognition_authorization_and_commit(self):
        evidence = self._base()
        evidence["accounting_attribution_evidence_confirmed"] = False
        evidence["return_cogs_accounting_recognition_evidence_confirmed"] = False
        evidence["return_cogs_profit_application_eligibility_confirmed"] = False
        evidence["return_cogs_profit_application_commit_confirmed"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION,
        )

    def test_partial_accounting_status_blocks_even_when_boolean_is_true(self):
        evidence = self._base()
        evidence["accounting_attribution_evidence_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_EVIDENCE_PARTIAL"
        )
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION,
        )

    def test_missing_accounting_status_blocks_even_when_boolean_is_true(self):
        evidence = self._base()
        evidence.pop("accounting_attribution_evidence_status")
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION,
        )

    def test_recognition_precedes_authorization_and_commit(self):
        evidence = self._base()
        evidence["return_cogs_accounting_recognition_evidence_confirmed"] = False
        evidence["return_cogs_profit_application_eligibility_confirmed"] = False
        evidence["return_cogs_profit_application_commit_confirmed"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_RECOGNITION,
        )

    def test_blocked_recognition_status_cannot_advance_on_true_boolean(self):
        evidence = self._base()
        evidence["return_cogs_accounting_recognition_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_ACCOUNTING_RECOGNITION_BLOCKED"
        )
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_RECOGNITION,
        )

    def test_authorization_precedes_commit(self):
        evidence = self._base()
        evidence["return_cogs_profit_application_eligibility_confirmed"] = False
        evidence["return_cogs_profit_application_commit_confirmed"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_AUTHORIZATION,
        )

    def test_blocked_application_status_cannot_advance_on_true_boolean(self):
        evidence = self._base()
        evidence["return_cogs_profit_application_eligibility_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_BLOCKED"
        )
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_AUTHORIZATION,
        )

    def test_commit_precedes_final_application(self):
        evidence = self._base()
        evidence["return_cogs_profit_application_commit_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
        )
        evidence["return_cogs_profit_application_commit_confirmed"] = False
        evidence["return_cogs_profit_applied"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_COMMIT,
        )

    def test_true_commit_boolean_without_committed_status_stays_at_commit(self):
        evidence = self._base()
        evidence["return_cogs_profit_application_commit_status"] = (
            "PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_READY"
        )
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_COMMIT,
        )

    def test_committed_but_not_applied_is_explicit_final_application_stage(self):
        evidence = self._base()
        evidence["return_cogs_profit_applied"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.FINAL_APPLICATION,
        )
        self.assertTrue(result["blocker_present"])

    def test_applied_chain_has_no_blocker(self):
        result = PeriodProfitReturnCogsBlockerStageService.resolve(self._base())
        self.assertEqual(result["stage"], PeriodProfitReturnCogsBlockerStageService.NONE)
        self.assertFalse(result["blocker_present"])
        self.assertEqual(result["records"], [])

    def test_ready_non_saleable_candidate_can_advance_past_inventory(self):
        evidence = self._base()
        evidence["candidate_records"] = [self._candidate(state="NON_SALEABLE")]
        evidence["accounting_attribution_evidence_confirmed"] = False
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(
            result["stage"],
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION,
        )

    def test_non_ready_non_saleable_candidate_stays_inventory_blocked(self):
        evidence = self._base()
        evidence["candidate_records"] = [
            self._candidate(ready=False, state="NON_SALEABLE")
        ]
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(result["stage"], PeriodProfitReturnCogsBlockerStageService.INVENTORY)

    def test_malformed_candidate_row_is_inventory_blocked(self):
        evidence = self._base()
        evidence["candidate_records"] = [None]
        result = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        self.assertEqual(result["stage"], PeriodProfitReturnCogsBlockerStageService.INVENTORY)
        self.assertTrue(result["blocker_present"])

    def test_invalid_evidence_fails_closed_without_inventing_a_financial_stage(self):
        result = PeriodProfitReturnCogsBlockerStageService.resolve(None)
        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "RETURN_COGS_EVIDENCE_INVALID")
        self.assertEqual(result["stage"], PeriodProfitReturnCogsBlockerStageService.NONE)
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
