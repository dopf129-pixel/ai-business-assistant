import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_finance_service import PeriodProfitFinanceService  # noqa: E402
from services.period_profit_finance_posting_identity_scope_service import (  # noqa: E402
    PeriodProfitFinancePostingIdentityScopeService,
)
from services.tenant_context import (  # noqa: E402
    get_current_tenant_user_id,
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


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


class _TenantScopedOzon:
    def get_accruals_by_day(self, accrual_date):
        return {
            "error": False,
            "accruals": [{"tenant": get_current_tenant_user_id()}],
            "last_id": "",
        }


class _PeriodScopeOzon:
    def __init__(self):
        self.day_calls = []

    def get_accruals_by_day(self, accrual_date):
        self.day_calls.append(str(accrual_date))
        return {
            "error": False,
            "accruals": [{
                "accrued_category": "POSTING",
                "posting": {
                    "products": [{"sku": "fixture-sku"}],
                },
            }],
            "last_id": "",
        }

    def get_realization_posting(self, _year, _month):
        return {"error": False, "rows": []}


class _SummaryBeginningPreparedSession:
    def __init__(self, finance_service):
        self.finance_service = finance_service
        self.cost_service = None
        self.tax_rate = 0.0

    def calculate(self, date_from, date_to, _products):
        self.finance_service.prepare_read_session(date_from, date_to)
        self.finance_service.begin_read_session()
        return {"error": False, "profit": 0.0}


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

    def test_general_and_selected_profit_reuse_scope_prefetch_in_summary(self):
        for selected_scope in (False, True):
            with self.subTest(selected_scope=selected_scope):
                finance = PeriodProfitFinanceService()
                ozon = _PeriodScopeOzon()
                finance.ozon = ozon
                summary = _SummaryBeginningPreparedSession(finance)
                scope = PeriodProfitFinancePostingIdentityScopeService(
                    summary,
                    finance,
                )
                product = {
                    "product_id": "fixture-product",
                    "offer_id": "fixture-offer",
                    "sku": "fixture-sku",
                }
                if selected_scope:
                    product["_period_profit_selected_scope"] = True

                result = scope.calculate(
                    "2026-09-08",
                    "2026-09-14",
                    [product],
                )

                self.assertFalse(result["error"])
                self.assertEqual(len(ozon.day_calls), 7)
                self.assertEqual(len(set(ozon.day_calls)), 7)

    def test_prepared_session_refreshes_cache_for_a_different_period(self):
        service = PeriodProfitFinanceService()
        ozon = _ConcurrentOzon()
        service.ozon = ozon

        service.prefetch_daily_accruals("2026-09-08", "2026-09-08")
        service.prepare_read_session("2026-09-09", "2026-09-09")
        service.begin_read_session()

        self.assertEqual(
            sorted(ozon.day_calls),
            ["2026-09-08", "2026-09-09"],
        )
        self.assertEqual(
            set(service._daily_accrual_cache),
            {"2026-09-09"},
        )

    def test_prepared_session_refetches_when_same_period_cache_is_incomplete(self):
        service = PeriodProfitFinanceService()
        ozon = _ConcurrentOzon()
        service.ozon = ozon

        service.prefetch_daily_accruals("2026-09-08", "2026-09-09")
        del service._daily_accrual_cache["2026-09-08"]
        service.prepare_read_session("2026-09-08", "2026-09-09")
        service.begin_read_session()

        self.assertEqual(len(ozon.day_calls), 4)
        self.assertEqual(
            set(service._daily_accrual_cache),
            {"2026-09-08", "2026-09-09"},
        )

    def test_prefetched_period_marker_does_not_cross_request_contexts(self):
        service = PeriodProfitFinanceService()
        ozon = _ConcurrentOzon()
        service.ozon = ozon
        context_a = copy_context()
        context_b = copy_context()

        prefetched = context_a.run(
            service.prefetch_daily_accruals,
            "2026-09-08",
            "2026-09-08",
        )

        def begin_other_tenant_session():
            service.prepare_read_session("2026-09-08", "2026-09-08")
            service.begin_read_session()

        context_b.run(begin_other_tenant_session)

        self.assertFalse(prefetched["error"])
        self.assertEqual(len(ozon.day_calls), 2)

    def test_overlapping_store_reads_keep_daily_accrual_cache_request_local(self):
        service = PeriodProfitFinanceService()
        service.ozon = _TenantScopedOzon()
        accrual_date = "2026-09-14"
        tenant_a_prefetched = threading.Event()
        tenant_b_prefetched = threading.Event()

        def read_tenant_a():
            token = set_current_tenant_user_id("tenant-a")
            try:
                service.begin_read_session()
                result = service.prefetch_daily_accruals(accrual_date, accrual_date)
                self.assertFalse(result["error"])
                tenant_a_prefetched.set()
                self.assertTrue(tenant_b_prefetched.wait(timeout=3))
                return service._get_accruals_by_day(accrual_date)["accruals"][0]["tenant"]
            finally:
                reset_current_tenant_user_id(token)

        def read_tenant_b():
            token = set_current_tenant_user_id("tenant-b")
            try:
                self.assertTrue(tenant_a_prefetched.wait(timeout=3))
                service.begin_read_session()
                result = service.prefetch_daily_accruals(accrual_date, accrual_date)
                self.assertFalse(result["error"])
                tenant_b_prefetched.set()
                return service._get_accruals_by_day(accrual_date)["accruals"][0]["tenant"]
            finally:
                reset_current_tenant_user_id(token)

        with ThreadPoolExecutor(max_workers=2) as executor:
            tenant_a = executor.submit(read_tenant_a)
            tenant_b = executor.submit(read_tenant_b)
            self.assertEqual(tenant_a.result(timeout=5), "tenant-a")
            self.assertEqual(tenant_b.result(timeout=5), "tenant-b")

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
