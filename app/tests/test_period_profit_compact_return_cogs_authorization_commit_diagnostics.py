import unittest

from period_profit_compact_response import compact_period_profit_result


class PeriodProfitCompactReturnCogsAuthorizationCommitDiagnosticsTests(unittest.TestCase):
    def _result(self, evidence):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "summary": {
                "date_from": "2026-05-03",
                "date_to": "2026-08-31",
                "revenue": 1000.0,
                "units_sold": 10,
                "net_accrual": 400.0,
                "product_cost": 210.0,
                "tax": 60.0,
                "profit": 130.0,
                "margin_percent": 13.0,
            },
            "return_cogs_recovery_evidence": evidence,
            "text": "details",
        }

    def _candidate(self, suffix="1", quantity=1):
        return {
            "return_id": "r-" + suffix,
            "posting_number": "p-" + suffix,
            "sku": "s-" + suffix,
            "quantity": quantity,
            "inventory_recovery_state": "SALEABLE_RESTORED",
            "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
        }

    def _recognition(self, suffix="1", history_id=10, amount=21.0):
        return {
            "error": False,
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
            "return_id": "r-" + suffix,
            "posting_number": "p-" + suffix,
            "sku": "s-" + suffix,
            "history_id": history_id,
            "accounting_recognition_confirmed": True,
            "recognition_state": "COGS_RECOVERY_RECOGNIZED",
            "recognized_amount": amount,
            "currency": "RUB",
            "recovery_accounting_date": "2026-08-20",
        }

    def _authorization(self, suffix="1", recognition_history_id=10, history_id=20, amount=21.0):
        return {
            "error": False,
            "status": "RETURN_COGS_PROFIT_APPLICATION_AUTHORIZATION_READY",
            "return_id": "r-" + suffix,
            "posting_number": "p-" + suffix,
            "sku": "s-" + suffix,
            "history_id": history_id,
            "recognition_history_id": recognition_history_id,
            "application_authorization_confirmed": True,
            "application_state": "PROFIT_APPLICATION_AUTHORIZED",
            "application_already_applied": False,
            "authorized_amount": amount,
            "currency": "RUB",
            "recovery_accounting_date": "2026-08-20",
            "monetary_authority_treatment": "EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL",
            "monetary_authority_non_overlap_confirmed": True,
            "compensation_non_overlap_confirmed": True,
        }

    def _base_evidence(self):
        return {
            "error": False,
            "unresolved_units": 0,
            "period_cogs_recovery_confirmed": True,
            "accounting_attribution_evidence_confirmed": True,
            "return_cogs_accounting_recognition_evidence_confirmed": True,
            "candidate_records": [self._candidate()],
            "return_cogs_accounting_recognition_evidence_records": [self._recognition()],
        }

    def test_missing_authorization_exposes_exact_identity(self):
        evidence = self._base_evidence()
        evidence.update({
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_authorization_records": [],
        })
        result = compact_period_profit_result(self._result(evidence))
        self.assertIn("Точные блокеры авторизации", result["text"])
        self.assertIn("return_id=r-1", result["text"])
        self.assertIn("нет отдельной авторизации применения к прибыли", result["text"])
        self.assertNotIn("exact-once commit", result["text"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_authorized_amount_mismatch_stays_at_authorization_gate(self):
        evidence = self._base_evidence()
        evidence.update({
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_authorization_records": [
                self._authorization(amount=20.0)
            ],
        })
        result = compact_period_profit_result(self._result(evidence))
        self.assertIn("авторизованная сумма не совпадает", result["text"])
        self.assertNotIn("Точные блокеры exact-once commit", result["text"])

    def test_unknown_monetary_authority_overlap_is_not_treated_as_clear(self):
        record = self._authorization()
        record["monetary_authority_non_overlap_confirmed"] = None
        evidence = self._base_evidence()
        evidence.update({
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_authorization_records": [record],
        })
        result = compact_period_profit_result(self._result(evidence))
        self.assertIn("не подтверждено отсутствие пересечения с денежным authority", result["text"])
        self.assertNotIn("=0", result["text"])

    def test_commit_ready_is_exact_and_still_not_committed(self):
        evidence = self._base_evidence()
        evidence.update({
            "return_cogs_profit_application_eligibility_confirmed": True,
            "return_cogs_profit_application_authorization_records": [self._authorization()],
            "return_cogs_profit_application_commit_ready": True,
            "return_cogs_profit_application_commit_confirmed": False,
            "return_cogs_profit_application_commit_records": [],
            "return_cogs_profit_applied": False,
        })
        result = compact_period_profit_result(self._result(evidence))
        self.assertIn("Точные блокеры exact-once commit", result["text"])
        self.assertIn("return_id=r-1", result["text"])
        self.assertIn("готов к exact-once commit, но запись commit ещё отсутствует", result["text"])
        self.assertIn("остаётся read-only", result["text"])
        self.assertFalse(result["executed"])

    def test_commit_amount_mismatch_exposes_exact_candidate(self):
        commit = {
            "error": False,
            "return_id": "r-1",
            "posting_number": "p-1",
            "sku": "s-1",
            "recognition_history_id": 10,
            "authorization_history_id": 20,
            "application_commit_confirmed": True,
            "committed_amount": 20.0,
            "currency": "RUB",
            "recovery_accounting_date": "2026-08-20",
        }
        evidence = self._base_evidence()
        evidence.update({
            "return_cogs_profit_application_eligibility_confirmed": True,
            "return_cogs_profit_application_authorization_records": [self._authorization()],
            "return_cogs_profit_application_commit_ready": False,
            "return_cogs_profit_application_commit_confirmed": False,
            "return_cogs_profit_application_commit_records": [commit],
            "return_cogs_profit_applied": False,
        })
        result = compact_period_profit_result(self._result(evidence))
        self.assertIn("return_id=r-1", result["text"])
        self.assertIn("сумма commit не совпадает с бухгалтерски признанной", result["text"])

    def test_authorization_and_commit_diagnostics_are_deterministic_and_limited(self):
        candidates = []
        recognitions = []
        for suffix, history_id in (("d", 14), ("b", 12), ("a", 11), ("c", 13)):
            candidates.append(self._candidate(suffix))
            recognitions.append(self._recognition(suffix, history_id=history_id))
        evidence = {
            "error": False,
            "unresolved_units": 0,
            "period_cogs_recovery_confirmed": True,
            "accounting_attribution_evidence_confirmed": True,
            "return_cogs_accounting_recognition_evidence_confirmed": True,
            "return_cogs_profit_application_eligibility_confirmed": False,
            "candidate_records": candidates,
            "return_cogs_accounting_recognition_evidence_records": recognitions,
            "return_cogs_profit_application_authorization_records": [],
        }
        text = compact_period_profit_result(self._result(evidence))["text"]
        self.assertLess(text.index("return_id=r-a"), text.index("return_id=r-b"))
        self.assertLess(text.index("return_id=r-b"), text.index("return_id=r-c"))
        self.assertNotIn("return_id=r-d", text)
        self.assertIn("ещё 1", text)


if __name__ == "__main__":
    unittest.main()
