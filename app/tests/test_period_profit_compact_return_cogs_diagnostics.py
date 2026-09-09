import unittest

from period_profit_compact_response import compact_period_profit_result


class PeriodProfitCompactReturnCogsDiagnosticsTests(unittest.TestCase):
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

    def test_inventory_blocker_exposes_exact_identity_without_inferring_ozon_state(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "1001702837",
                    "posting_number": "123-456-1",
                    "sku": "987654321",
                    "quantity": 1,
                    "visual_status_sys_name": "ReturnedToOzon",
                    "inventory_recovery_state": None,
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_MISSING"
                    ),
                }],
            })
        )

        self.assertIn("return_id=1001702837", result["text"])
        self.assertIn("posting=123-456-1", result["text"])
        self.assertIn("SKU=987654321", result["text"])
        self.assertIn("кол-во=1", result["text"])
        self.assertIn("Статус Ozon сам по себе не доказывает SALEABLE_RESTORED", result["text"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_unknown_quantity_is_not_rendered_as_zero(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "quantity": None,
                    "inventory_recovery_state": None,
                }],
            })
        )

        self.assertIn("кол-во=неизвестно", result["text"])
        self.assertNotIn("кол-во=0", result["text"])

    def test_non_saleable_candidate_is_not_requested_for_saleable_confirmation(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "quantity": 1,
                    "inventory_recovery_state": "NON_SALEABLE",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_READY"
                    ),
                }],
            })
        )

        self.assertNotIn("Нужен локальный факт о состоянии возврата", result["text"])
        self.assertNotIn("return_id=r-1", result["text"])

    def test_non_saleable_state_without_ready_evidence_stays_unconfirmed(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-unsafe",
                    "posting_number": "p-unsafe",
                    "sku": "s-unsafe",
                    "quantity": 2,
                    "inventory_recovery_state": "NON_SALEABLE",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_IDENTITY_CONFLICT"
                    ),
                }],
            })
        )

        self.assertIn("Есть 2 возврата Returns API", result["text"])
        self.assertIn("Нужен локальный факт о состоянии возврата", result["text"])
        self.assertIn("return_id=r-unsafe", result["text"])

    def test_saleable_state_without_ready_evidence_does_not_advance_to_accounting(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-unavailable",
                    "posting_number": "p-unavailable",
                    "sku": "s-unavailable",
                    "quantity": 1,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_UNAVAILABLE"
                    ),
                }],
                "accounting_attribution_evidence_confirmed": False,
            })
        )

        self.assertIn("Нужен локальный факт о состоянии возврата", result["text"])
        self.assertIn("return_id=r-unavailable", result["text"])
        self.assertNotIn("бухгалтерская атрибуция периода", result["text"])

    def test_saleable_inventory_moves_diagnostic_to_accounting_gate(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "quantity": 1,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_READY"
                    ),
                }],
                "accounting_attribution_evidence_confirmed": False,
            })
        )

        self.assertNotIn("Нужен локальный факт о состоянии возврата", result["text"])
        self.assertIn("бухгалтерская атрибуция периода", result["text"])
        self.assertIn("отсутствие двойного учёта компенсации", result["text"])

    def test_accounting_missing_exposes_exact_identity_and_does_not_invent_quantity(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-accounting",
                    "posting_number": "p-accounting",
                    "sku": "s-accounting",
                    "quantity": None,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
                }],
                "accounting_attribution_evidence_confirmed": False,
                "accounting_attribution_evidence_records": [{
                    "return_id": "r-accounting",
                    "posting_number": "p-accounting",
                    "sku": "s-accounting",
                    "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING",
                    "recovery_accounting_period_matches_request": False,
                    "compensation_state": None,
                    "compensation_double_count_clear": None,
                }],
            })
        )

        self.assertIn("Точные бухгалтерские блокеры", result["text"])
        self.assertIn("return_id=r-accounting", result["text"])
        self.assertIn("posting=p-accounting", result["text"])
        self.assertIn("SKU=s-accounting", result["text"])
        self.assertIn("кол-во=неизвестно", result["text"])
        self.assertIn("нет бухгалтерской атрибуции периода", result["text"])
        self.assertNotIn("кол-во=0", result["text"])
        self.assertIn("не считаются нулём", result["text"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_accounting_ready_but_outside_period_exposes_period_reason(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-period",
                    "posting_number": "p-period",
                    "sku": "s-period",
                    "quantity": 2,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
                }],
                "accounting_attribution_evidence_confirmed": False,
                "accounting_attribution_evidence_records": [{
                    "return_id": "r-period",
                    "posting_number": "p-period",
                    "sku": "s-period",
                    "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
                    "recovery_accounting_period_matches_request": False,
                    "compensation_state": "NO_COMPENSATION_CONFIRMED",
                    "compensation_double_count_clear": True,
                }],
            })
        )

        self.assertIn("return_id=r-period", result["text"])
        self.assertIn("кол-во=2", result["text"])
        self.assertIn(
            "дата бухгалтерского восстановления не подтверждена в выбранном периоде",
            result["text"],
        )

    def test_accounting_double_count_unknown_stays_unconfirmed(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-comp",
                    "posting_number": "p-comp",
                    "sku": "s-comp",
                    "quantity": 1,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
                }],
                "accounting_attribution_evidence_confirmed": False,
                "accounting_attribution_evidence_records": [{
                    "return_id": "r-comp",
                    "posting_number": "p-comp",
                    "sku": "s-comp",
                    "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
                    "recovery_accounting_period_matches_request": True,
                    "compensation_state": "COMPENSATION_PRESENT",
                    "compensation_double_count_clear": None,
                }],
            })
        )

        self.assertIn("return_id=r-comp", result["text"])
        self.assertIn(
            "отсутствие двойного учёта компенсации не подтверждено",
            result["text"],
        )
        self.assertNotIn("отдельная авторизация применения", result["text"])

    def test_accounting_diagnostics_are_deterministic_and_limited(self):
        candidates = []
        accounting_records = []
        for suffix in ("d", "b", "a", "c"):
            candidates.append({
                "return_id": "r-" + suffix,
                "posting_number": "p-" + suffix,
                "sku": "s-" + suffix,
                "quantity": 1,
                "inventory_recovery_state": "SALEABLE_RESTORED",
                "inventory_recovery_evidence_status": "RETURN_INVENTORY_RECOVERY_READY",
            })
            accounting_records.append({
                "return_id": "r-" + suffix,
                "posting_number": "p-" + suffix,
                "sku": "s-" + suffix,
                "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING",
            })

        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": candidates,
                "accounting_attribution_evidence_confirmed": False,
                "accounting_attribution_evidence_records": accounting_records,
            })
        )

        text = result["text"]
        self.assertLess(text.index("return_id=r-a"), text.index("return_id=r-b"))
        self.assertLess(text.index("return_id=r-b"), text.index("return_id=r-c"))
        self.assertNotIn("return_id=r-d", text)
        self.assertIn("ещё 1", text)

    def test_diagnostic_stops_at_first_unproven_gate(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "quantity": 1,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_READY"
                    ),
                }],
                "accounting_attribution_evidence_confirmed": True,
                "return_cogs_accounting_recognition_evidence_confirmed": False,
                "return_cogs_profit_application_eligibility_confirmed": False,
                "return_cogs_profit_application_commit_confirmed": False,
            })
        )

        self.assertIn("требуется отдельное бухгалтерское признание", result["text"])
        self.assertNotIn("отдельная авторизация применения", result["text"])
        self.assertNotIn("exact-once commit", result["text"])

    def test_commit_ready_is_still_read_only_and_not_presented_as_applied(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "period_cogs_recovery_confirmed": True,
                "candidate_records": [{
                    "return_id": "r-1",
                    "posting_number": "p-1",
                    "sku": "s-1",
                    "quantity": 1,
                    "inventory_recovery_state": "SALEABLE_RESTORED",
                    "inventory_recovery_evidence_status": (
                        "RETURN_INVENTORY_RECOVERY_READY"
                    ),
                }],
                "accounting_attribution_evidence_confirmed": True,
                "return_cogs_accounting_recognition_evidence_confirmed": True,
                "return_cogs_profit_application_eligibility_confirmed": True,
                "return_cogs_profit_application_commit_ready": True,
                "return_cogs_profit_application_commit_confirmed": False,
                "return_cogs_profit_applied": False,
            })
        )

        self.assertIn("доказан до стадии commit", result["text"])
        self.assertIn("Текущий ответ остаётся read-only", result["text"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
