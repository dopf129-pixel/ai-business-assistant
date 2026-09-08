import unittest

from period_profit_compact_response import compact_period_profit_result


class PeriodProfitCompactReturnInventoryWarningTests(unittest.TestCase):
    def _result(self, return_cogs):
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
            "return_cogs_recovery_evidence": return_cogs,
            "text": "details",
        }

    def test_returned_to_ozon_candidate_without_inventory_proof_stays_visible(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "candidate_recovery_units": 1,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "1001702837",
                    "quantity": 1,
                    "visual_status_sys_name": "ReturnedToOzon",
                    "inventory_recovery_state": None,
                }],
            })
        )

        self.assertIn(
            "Есть 1 возврата Returns API",
            result["text"],
        )
        self.assertIn(
            "восстановление себестоимости не подтверждено",
            result["text"],
        )

    def test_non_saleable_candidate_does_not_claim_unconfirmed_recovery(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 0,
                "candidate_recovery_units": 1,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "1001702837",
                    "quantity": 1,
                    "inventory_recovery_state": "NON_SALEABLE",
                }],
            })
        )

        self.assertNotIn(
            "возврата Returns API",
            result["text"],
        )

    def test_existing_unresolved_units_and_unproven_candidates_are_both_counted(self):
        result = compact_period_profit_result(
            self._result({
                "error": False,
                "unresolved_units": 2,
                "candidate_recovery_units": 1,
                "period_cogs_recovery_confirmed": False,
                "candidate_records": [{
                    "return_id": "1001702837",
                    "quantity": 1,
                    "inventory_recovery_state": "",
                }],
            })
        )

        self.assertIn(
            "Есть 3 возврата Returns API",
            result["text"],
        )


if __name__ == "__main__":
    unittest.main()
