import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_return_cogs_effective_cost_recovery_evidence_service import (  # noqa: E402
    PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService,
)


class EffectiveSwitchCost:
    def get_cost(self, product_id):
        return (product_id, "3921245627", "hook-2", 99.0, "RUB", None)

    def get_effective_cost_evidence(
        self, at_date, product_id=None, sku=None, offer_id=None
    ):
        return {
            "error": False,
            "status": "PRODUCT_COST_SWITCH_READY",
            "switch_id": 2,
            "product_id": product_id,
            "sku": sku,
            "offer_id": offer_id,
            "cost_price": 21.0,
            "currency": "RUB",
            "effective_from": "2026-01-01",
            "effective_through": None,
            "source": "SELLER_CONFIRMED_INITIAL",
            "at_date": at_date,
            "switch_cost_confirmed": True,
            "seller_confirmed": True,
            "effective_cost_confirmed": True,
            "historical_cost_confirmed": True,
            "cost_basis": "SELLER_CONFIRMED_OPERATIONAL_SWITCH",
        }


class CurrentOnlyCost:
    def get_cost(self, product_id):
        return (product_id, "3921245627", "hook-2", 21.0, "RUB", None)


class MatchedLineage:
    def analyze(self, return_evidence):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_READY",
            "finance_period_complete": True,
            "matching_basis": "posting_number+sku",
            "lineage_records": [
                {
                    "return_id": "r1",
                    "posting_number": "p1",
                    "sku": "3921245627",
                    "lineage_status": "MATCHED_IN_SELECTED_PERIOD",
                    "matched_sale_accrual_date": "2026-08-01",
                }
            ],
        }


class SaleableRecovery:
    def get_latest_recovery(self, return_id, posting_number, sku):
        return {
            "error": False,
            "status": "RETURN_INVENTORY_RECOVERY_READY",
            "return_id": return_id,
            "posting_number": posting_number,
            "sku": sku,
            "quantity": 1,
            "recovery_state": "SALEABLE_RESTORED",
            "confirmed_on": "2026-08-10",
            "source": "SELLER_CONFIRMED",
            "inventory_recovery_confirmed": True,
        }


def return_evidence(status="ReturnedToOzon"):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
        "complete": True,
        "return_record_count_exact": True,
        "records": [
            {
                "id": "r1",
                "return_id": "r1",
                "posting_number": "p1",
                "sku": "3921245627",
                "offer_id": "hook-2",
                "quantity": 1,
                "type": "ClientReturn",
                "visual_status_sys_name": status,
                "compensation_status_sys_name": "",
            }
        ],
    }


class ReturnCogsEffectiveCostTests(unittest.TestCase):
    def test_current_returned_to_ozon_status_reaches_conservative_recovery_gates(self):
        service = PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService(
            EffectiveSwitchCost(),
            MatchedLineage(),
            SaleableRecovery(),
        )
        result = service.analyze(
            return_evidence(),
            [("4108512640", "hook-2", "3921245627")],
        )

        self.assertEqual(result["candidate_recovery_units"], 1)
        self.assertEqual(len(result["candidate_records"]), 1)
        self.assertTrue(result["saleable_inventory_recovery_confirmed"])

    def test_legacy_arrived_status_is_not_silently_treated_as_current_authority(self):
        service = PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService(
            EffectiveSwitchCost(),
            MatchedLineage(),
            SaleableRecovery(),
        )
        result = service.analyze(
            return_evidence("ArrivedAtReturnPlace"),
            [("4108512640", "hook-2", "3921245627")],
        )

        self.assertEqual(result["candidate_recovery_units"], 0)
        self.assertEqual(len(result["candidate_records"]), 0)
        self.assertEqual(result["unresolved_units"], 1)
        self.assertFalse(result["period_cogs_recovery_confirmed"])
        self.assertFalse(result["profit_adjustment_allowed"])

    def test_operational_switch_is_originating_sale_cost_authority(self):
        service = PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService(
            EffectiveSwitchCost(),
            MatchedLineage(),
            SaleableRecovery(),
        )
        result = service.analyze(
            return_evidence(),
            [("4108512640", "hook-2", "3921245627")],
        )

        self.assertFalse(result["error"])
        self.assertTrue(result["originating_sale_period_confirmed"])
        self.assertTrue(result["historical_cost_basis_confirmed"])
        self.assertEqual(result["candidate_value_at_historical_cost"], 21.0)
        row = result["candidate_records"][0]
        self.assertEqual(row["historical_cost_per_unit"], 21.0)
        self.assertEqual(
            row["historical_cost_source"], "SELLER_CONFIRMED_INITIAL"
        )
        # Mutable current cost is deliberately 99; it cannot become the
        # originating-sale historical authority.
        self.assertEqual(result["candidate_value_at_current_cost"], 99.0)

    def test_current_cost_without_effective_evidence_fails_closed(self):
        service = PeriodProfitReturnCogsEffectiveCostRecoveryEvidenceService(
            CurrentOnlyCost(),
            MatchedLineage(),
            SaleableRecovery(),
        )
        result = service.analyze(
            return_evidence(),
            [("4108512640", "hook-2", "3921245627")],
        )

        self.assertFalse(result["error"])
        self.assertFalse(result["historical_cost_basis_confirmed"])
        self.assertIsNone(result["candidate_value_at_historical_cost"])
        self.assertEqual(
            result["historical_cost_unavailable_candidate_record_count"], 1
        )
        self.assertFalse(result["period_cogs_recovery_confirmed"])
        self.assertFalse(result["profit_adjustment_allowed"])
        self.assertEqual(result["confirmed_cogs_recovery_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
