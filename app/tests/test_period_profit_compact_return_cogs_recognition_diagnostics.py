import unittest

from period_profit_compact_response import compact_period_profit_result


class PeriodProfitCompactReturnCogsRecognitionDiagnosticsTests(unittest.TestCase):
    def _candidate(self, suffix, quantity=1):
        return {
            "return_id": "r-" + suffix,
            "posting_number": "p-" + suffix,
            "sku": "s-" + suffix,
            "quantity": quantity,
            "inventory_recovery_state": "SALEABLE_RESTORED",
            "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
        }

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

    def _recognition_ready_base(self, candidate):
        key = {
            "return_id": candidate["return_id"],
            "posting_number": candidate["posting_number"],
            "sku": candidate["sku"],
        }
        return {
            "error": False,
            "unresolved_units": 0,
            "period_cogs_recovery_confirmed": False,
            "candidate_records": [candidate],
            "accounting_attribution_evidence_confirmed": True,
            "accounting_attribution_evidence_records": [{
                **key,
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
                "recovery_accounting_date": "2026-07-15",
                "recovery_accounting_period_matches_request": True,
                "compensation_state": "NO_COMPENSATION_CONFIRMED",
                "compensation_double_count_clear": True,
            }],
            "return_cogs_recovery_amount_evidence_records": [{
                **key,
                "status": "RETURN_COGS_AMOUNT_CANDIDATE_READY",
                "staged_recovery_amount": 210.0,
            }],
            "return_cogs_accounting_recognition_evidence_confirmed": False,
            "return_cogs_accounting_recognition_evidence_records": [],
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_commit_confirmed": False,
        }

    def test_missing_recognition_exposes_exact_identity_without_inventing_quantity(self):
        candidate = self._candidate("missing", quantity=None)
        result = compact_period_profit_result(
            self._result(self._recognition_ready_base(candidate))
        )

        self.assertIn("Точные блокеры бухгалтерского признания", result["text"])
        self.assertIn("return_id=r-missing", result["text"])
        self.assertIn("posting=p-missing", result["text"])
        self.assertIn("SKU=s-missing", result["text"])
        self.assertIn("кол-во=неизвестно", result["text"])
        self.assertNotIn("кол-во=0", result["text"])
        self.assertIn("нет отдельного бухгалтерского признания", result["text"])
        self.assertIn("не подменяется расчётной суммой", result["text"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_recognition_amount_mismatch_is_exposed_and_does_not_advance(self):
        candidate = self._candidate("amount")
        evidence = self._recognition_ready_base(candidate)
        evidence["return_cogs_accounting_recognition_evidence_records"] = [{
            "error": False,
            "return_id": "r-amount",
            "posting_number": "p-amount",
            "sku": "s-amount",
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
            "accounting_recognition_confirmed": True,
            "recognition_state": "COGS_RECOVERY_RECOGNIZED",
            "recognized_amount": 209.0,
            "currency": "RUB",
            "recovery_accounting_date": "2026-07-15",
        }]

        result = compact_period_profit_result(self._result(evidence))

        self.assertIn("return_id=r-amount", result["text"])
        self.assertIn(
            "признанная сумма не совпадает с подтверждённой суммой восстановления",
            result["text"],
        )
        self.assertNotIn("отдельная авторизация применения", result["text"])

    def test_recognition_date_mismatch_is_exposed(self):
        candidate = self._candidate("date")
        evidence = self._recognition_ready_base(candidate)
        evidence["return_cogs_accounting_recognition_evidence_records"] = [{
            "error": False,
            "return_id": "r-date",
            "posting_number": "p-date",
            "sku": "s-date",
            "status": "RETURN_COGS_ACCOUNTING_RECOGNITION_READY",
            "accounting_recognition_confirmed": True,
            "recognition_state": "COGS_RECOVERY_RECOGNIZED",
            "recognized_amount": 210.0,
            "currency": "RUB",
            "recovery_accounting_date": "2026-07-16",
        }]

        result = compact_period_profit_result(self._result(evidence))

        self.assertIn("return_id=r-date", result["text"])
        self.assertIn(
            "дата бухгалтерского признания не совпадает с атрибуцией периода",
            result["text"],
        )

    def test_recognition_diagnostics_are_deterministic_and_limited(self):
        candidates = [self._candidate(suffix) for suffix in ("d", "b", "a", "c")]
        evidence = {
            "error": False,
            "unresolved_units": 0,
            "period_cogs_recovery_confirmed": False,
            "candidate_records": candidates,
            "accounting_attribution_evidence_confirmed": True,
            "accounting_attribution_evidence_records": [],
            "return_cogs_recovery_amount_evidence_records": [],
            "return_cogs_accounting_recognition_evidence_confirmed": False,
            "return_cogs_accounting_recognition_evidence_records": [],
            "return_cogs_profit_application_eligibility_confirmed": False,
            "return_cogs_profit_application_commit_confirmed": False,
        }

        result = compact_period_profit_result(self._result(evidence))
        text = result["text"]

        self.assertLess(text.index("return_id=r-a"), text.index("return_id=r-b"))
        self.assertLess(text.index("return_id=r-b"), text.index("return_id=r-c"))
        self.assertNotIn("return_id=r-d", text)
        self.assertIn("ещё 1", text)


if __name__ == "__main__":
    unittest.main()
