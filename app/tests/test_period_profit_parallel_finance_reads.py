import os
import sys
import threading
import time
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_service import PeriodProfitFinanceService  # noqa: E402


class _ConcurrentOzon:
    def __init__(self):
        self.lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight_day = 0
        self.max_in_flight_posting = 0
        self.day_calls = []
        self.posting_calls = []

    def _enter(self, attr):
        with self.lock:
            self.in_flight += 1
            setattr(self, attr, max(getattr(self, attr), self.in_flight))

    def _leave(self):
        with self.lock:
            self.in_flight -= 1

    def get_accruals_by_day(self, accrual_date):
        self._enter("max_in_flight_day")
        try:
            time.sleep(0.03)
            with self.lock:
                self.day_calls.append(str(accrual_date))
            return {"error": False, "accruals": [], "last_id": ""}
        finally:
            self._leave()

    def get_accruals_by_postings(self, posting_numbers):
        self._enter("max_in_flight_posting")
        try:
            time.sleep(0.03)
            batch = [str(value) for value in posting_numbers]
            with self.lock:
                self.posting_calls.append(tuple(batch))
            return {
                "error": False,
                "posting_accruals": [
                    {
                        "posting_number": posting_number,
                        "accruals": [{"sku": "sku-1", "quantity": 1}],
                    }
                    for posting_number in batch
                ],
            }
        finally:
            self._leave()


class _FailingDayOzon(_ConcurrentOzon):
    def get_accruals_by_day(self, accrual_date):
        if str(accrual_date) == "2026-09-12":
            time.sleep(0.01)
            return {"error": True, "message": "fixture failure"}
        return super().get_accruals_by_day(accrual_date)


class PeriodProfitParallelFinanceReadTests(unittest.TestCase):
    def test_prepared_read_session_prefetches_days_in_parallel_and_populates_normal_cache(self):
        service = PeriodProfitFinanceService()
        ozon = _ConcurrentOzon()
        service.ozon = ozon

        service.prepare_read_session("2026-09-08", "2026-09-14")
        service.begin_read_session()

        self.assertEqual(len(ozon.day_calls), 7)
        self.assertGreaterEqual(ozon.max_in_flight_day, 2)
        self.assertEqual(len(service._daily_accrual_cache), 7)

        before = len(ozon.day_calls)
        evidence = service.get_daily_sale_posting_evidence("2026-09-10")
        self.assertFalse(evidence["error"])
        self.assertEqual(len(ozon.day_calls), before)

    def test_prefetch_failure_keeps_fail_closed_cache_empty(self):
        service = PeriodProfitFinanceService()
        service.ozon = _FailingDayOzon()

        result = service.prefetch_daily_accruals("2026-09-10", "2026-09-13")

        self.assertTrue(result["error"])
        self.assertEqual(service._daily_accrual_cache, {})

    def test_posting_quantity_batches_run_in_parallel_without_changing_result(self):
        service = PeriodProfitFinanceService()
        ozon = _ConcurrentOzon()
        service.ozon = ozon
        posting_numbers = ["posting-%03d" % index for index in range(250)]

        result = service.get_sale_posting_quantity_evidence(posting_numbers)

        self.assertFalse(result["error"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["record_count"], 250)
        self.assertEqual(len(ozon.posting_calls), 3)
        self.assertGreaterEqual(ozon.max_in_flight_posting, 2)
        self.assertEqual(
            {record["posting_number"] for record in result["records"]},
            set(posting_numbers),
        )
        self.assertTrue(all(record["quantity"] == 1 for record in result["records"]))


if __name__ == "__main__":
    unittest.main()
