from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from datetime import date, timedelta
from threading import local

from api.period_profit_ozon_client import PeriodProfitOzonClient
from api.period_profit_runtime_ozon_client import PeriodProfitRuntimeOzonClient
from services.finance_service import FinanceService


class PeriodProfitFinanceService(FinanceService):
    """FinanceService adapter that preserves Period Profit completeness metadata."""

    POSTING_QUANTITY_BATCH_SIZE = 100
    DAILY_PREFETCH_WORKERS = 4
    POSTING_QUANTITY_WORKERS = 4

    def __init__(self):
        # This service is shared by the production Telegram runtime. Keep the
        # daily cache in the caller's context so overlapping store requests
        # cannot clear or reuse each other's account-level accruals.
        self._daily_accrual_cache_context = ContextVar(
            "period_profit_daily_accrual_cache_" + str(id(self)),
            default=None,
        )
        super().__init__()
        # FinanceService initializes its cache through the property below.
        # Ensure copied worker contexts start empty and lazily create their own
        # cache before the first read session.
        self._daily_accrual_cache_context.set(None)
        self._period_profit_session = local()

    @property
    def _daily_accrual_cache(self):
        cache = self._daily_accrual_cache_context.get()
        if cache is None:
            cache = {}
            self._daily_accrual_cache_context.set(cache)
        return cache

    @_daily_accrual_cache.setter
    def _daily_accrual_cache(self, value):
        self._daily_accrual_cache_context.set(value)

    @property
    def ozon(self):
        return self._ozon

    @ozon.setter
    def ozon(self, value):
        # The factory and older callers still assign PeriodProfitOzonClient directly.
        # Route only that production assignment through the runtime structural adapter;
        # test doubles and unrelated clients remain untouched.
        if type(value) is PeriodProfitOzonClient:
            value = PeriodProfitRuntimeOzonClient()
        self._ozon = value

    def prepare_read_session(self, date_from, date_to):
        """Schedule bounded READ-ONLY day prefetch for the next summary calculation."""
        self._period_profit_session.prefetch_period = (
            str(date_from),
            str(date_to),
        )

    def begin_read_session(self):
        super().begin_read_session()
        period = getattr(self._period_profit_session, "prefetch_period", None)
        self._period_profit_session.prefetch_period = None
        if period is None:
            return
        result = self.prefetch_daily_accruals(*period)
        if not isinstance(result, dict) or result.get("error") is True:
            raise RuntimeError("PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE")

    def prefetch_daily_accruals(self, date_from, date_to):
        """Fill the normal daily cache concurrently without changing finance semantics."""
        try:
            start = date.fromisoformat(str(date_from))
            end = date.fromisoformat(str(date_to))
        except (TypeError, ValueError):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_FINANCE_PREFETCH_PERIOD_INVALID",
            }
        if start > end:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_FINANCE_PREFETCH_PERIOD_INVALID",
            }

        getter = getattr(self.ozon, "get_accruals_by_day", None)
        if not callable(getter):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE",
            }

        dates = []
        current = start
        while current <= end:
            key = current.isoformat()
            if key not in self._daily_accrual_cache:
                dates.append(key)
            current += timedelta(days=1)

        if not dates:
            return {
                "error": False,
                "status": "PERIOD_PROFIT_FINANCE_PREFETCH_READY",
                "date_count": 0,
                "read_only": True,
                "executed": False,
            }

        workers = min(self.DAILY_PREFETCH_WORKERS, len(dates))
        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                responses = list(self._map_with_current_context(executor, getter, dates))
        except Exception:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE",
            }

        # Commit to the shared cache only after the whole bounded read succeeds.
        # This preserves the existing all-or-fail behavior for a calculation.
        for key, response in zip(dates, responses):
            if not isinstance(response, dict) or response.get("error") is True:
                return self._prefetch_response_error(response)
            accruals = response.get("accruals")
            if not isinstance(accruals, list):
                return {
                    "error": True,
                    "code": "PERIOD_PROFIT_FINANCE_PREFETCH_INVALID",
                }

        for key, response in zip(dates, responses):
            self._daily_accrual_cache[key] = response

        return {
            "error": False,
            "status": "PERIOD_PROFIT_FINANCE_PREFETCH_READY",
            "date_count": len(dates),
            "read_only": True,
            "executed": False,
        }

    def get_daily_finance(self, accrual_date, sku=None):
        result = super().get_daily_finance(accrual_date, sku=sku)
        if not isinstance(result, dict) or result.get("error") is True:
            return result

        cached = self._daily_accrual_cache.get(str(accrual_date))
        completeness = (
            cached.get("_period_profit_finance_completeness")
            if isinstance(cached, dict)
            else None
        )

        enriched = dict(result)
        if isinstance(completeness, dict):
            enriched["fee_components_included"] = (
                completeness.get("fee_components_included") is not False
            )
            enriched["ancillary_incomplete_count"] = int(
                completeness.get("ancillary_incomplete_count") or 0
            )
        else:
            enriched["fee_components_included"] = True
            enriched["ancillary_incomplete_count"] = 0
        return enriched

    def get_sale_posting_quantity_evidence(self, posting_numbers):
        """Load direct READ-ONLY Ozon quantity evidence for exact sale postings.

        ``/v1/finance/accrual/postings`` can contain several accrual rows for the
        same SKU (sale, commission, logistics, etc.). Quantity is therefore not
        summed across rows. It is accepted only when every positive observation
        for one posting/SKU agrees on the same integer value.
        """
        numbers = []
        seen = set()
        for value in posting_numbers or []:
            posting_number = str(value or "").strip()
            if not posting_number or posting_number in seen:
                continue
            seen.add(posting_number)
            numbers.append(posting_number)

        if not numbers:
            return {
                "error": False,
                "status": "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_READY",
                "complete": True,
                "record_count": 0,
                "records": [],
                "read_only": True,
                "executed": False,
            }

        getter = getattr(self.ozon, "get_accruals_by_postings", None)
        if not callable(getter):
            return self._posting_quantity_error(
                "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_UNAVAILABLE"
            )

        batches = [
            numbers[offset:offset + self.POSTING_QUANTITY_BATCH_SIZE]
            for offset in range(0, len(numbers), self.POSTING_QUANTITY_BATCH_SIZE)
        ]
        workers = min(self.POSTING_QUANTITY_WORKERS, len(batches))
        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                responses = list(self._map_with_current_context(executor, getter, batches))
        except Exception:
            return self._posting_quantity_error(
                "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_UNAVAILABLE"
            )

        quantities = {}
        for response in responses:
            if not isinstance(response, dict) or response.get("error") is True:
                return self._posting_quantity_error(
                    "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_UNAVAILABLE"
                )
            posting_accruals = response.get("posting_accruals")
            if not isinstance(posting_accruals, list):
                return self._posting_quantity_error(
                    "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                )

            for posting in posting_accruals:
                if not isinstance(posting, dict):
                    return self._posting_quantity_error(
                        "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                    )
                posting_number = str(posting.get("posting_number") or "").strip()
                accruals = posting.get("accruals")
                if not posting_number or not isinstance(accruals, list):
                    return self._posting_quantity_error(
                        "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                    )
                if posting_number not in seen:
                    return self._posting_quantity_error(
                        "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_SCOPE_INVALID"
                    )

                for accrual in accruals:
                    if not isinstance(accrual, dict):
                        return self._posting_quantity_error(
                            "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                        )
                    sku = str(accrual.get("sku") or "").strip()
                    raw_quantity = accrual.get("quantity")
                    if not sku or isinstance(raw_quantity, bool):
                        continue
                    try:
                        quantity = int(raw_quantity)
                    except (TypeError, ValueError, OverflowError):
                        return self._posting_quantity_error(
                            "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                        )
                    try:
                        if float(raw_quantity) != float(quantity):
                            return self._posting_quantity_error(
                                "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                            )
                    except (TypeError, ValueError, OverflowError):
                        return self._posting_quantity_error(
                            "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_INVALID"
                        )
                    if quantity <= 0:
                        continue
                    quantities.setdefault((posting_number, sku), set()).add(quantity)

        records = []
        for (posting_number, sku), values in sorted(quantities.items()):
            if len(values) != 1:
                return self._posting_quantity_error(
                    "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_CONFLICT"
                )
            records.append({
                "posting_number": posting_number,
                "sku": sku,
                "quantity": next(iter(values)),
                "source": "OZON_FINANCE_ACCRUAL_POSTINGS",
            })

        return {
            "error": False,
            "status": "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_READY",
            "complete": True,
            "record_count": len(records),
            "records": records,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _prefetch_response_error(response):
        code = ""
        if isinstance(response, dict):
            raw_code = str(response.get("code") or "").strip().upper()
            if raw_code and all(
                character.isalnum() or character == "_"
                for character in raw_code
            ):
                code = raw_code
            if not code:
                status_code = response.get("status_code")
                if (
                    isinstance(status_code, int)
                    and not isinstance(status_code, bool)
                    and 100 <= status_code <= 599
                ):
                    code = "PERIOD_PROFIT_FINANCE_PREFETCH_HTTP_" + str(status_code)
        result = {
            "error": True,
            "code": code or "PERIOD_PROFIT_FINANCE_PREFETCH_UNAVAILABLE",
            "read_only": True,
            "executed": False,
        }
        if isinstance(response, dict):
            diagnostic = str(
                response.get("finance_diagnostic_code") or ""
            ).strip().upper()
            if diagnostic and all(
                character.isalnum() or character == "_"
                for character in diagnostic
            ):
                result["finance_diagnostic_code"] = diagnostic
        return result

    @staticmethod
    def _map_with_current_context(executor, function, values):
        """Run every worker call in an independent copy of the request context."""
        futures = [
            executor.submit(copy_context().run, function, value)
            for value in values
        ]
        for future in futures:
            yield future.result()

    @staticmethod
    def _posting_quantity_error(code):
        return {
            "error": True,
            "code": code,
            "status": "FINANCE_SALE_POSTING_QUANTITY_EVIDENCE_UNAVAILABLE",
            "complete": False,
            "records": [],
            "read_only": True,
            "executed": False,
        }
