from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


class PeriodProfitRevenueDiagnosticsSummaryService:
    """Attach read-only raw Ozon revenue-field diagnostics to Period Profit."""

    FIELDS = (
        "sale_amount",
        "seller_price",
        "sale_price",
        "bonus",
        "coinvestment",
    )

    def __init__(self, base_service, finance_service):
        self.base_service = base_service
        self.finance_service = finance_service
        self.tax_rate = getattr(base_service, "tax_rate", None)

    def calculate(self, date_from, date_to, products):
        calculator = getattr(self.base_service, "calculate", None)
        if not callable(calculator):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_REVENUE_DIAGNOSTICS_BASE_UNAVAILABLE",
                "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
            }

        try:
            base = calculator(date_from, date_to, products)
        except Exception:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_REVENUE_DIAGNOSTICS_BASE_EXCEPTION",
                "status": "PERIOD_PROFIT_SUMMARY_UNAVAILABLE",
            }

        if not isinstance(base, dict) or base.get("error") is not False:
            return base

        result = dict(base)
        result["revenue_diagnostics"] = self._aggregate(date_from, date_to)
        return result

    def _aggregate(self, date_from, date_to):
        start = self._date(date_from)
        end = self._date(date_to)
        if start is None or end is None or start > end:
            return self._unavailable("PERIOD_PROFIT_REVENUE_DIAGNOSTICS_PERIOD_INVALID")

        cache = getattr(self.finance_service, "_daily_accrual_cache", None)
        if not isinstance(cache, dict):
            return self._unavailable("PERIOD_PROFIT_REVENUE_DIAGNOSTICS_CACHE_UNAVAILABLE")

        fields = {
            field: {
                "observed_amount": Decimal("0"),
                "observed_records": 0,
                "missing_records": 0,
                "complete": True,
            }
            for field in self.FIELDS
        }
        record_count = 0
        missing_days = 0
        current = start

        while current <= end:
            response = cache.get(current.isoformat())
            daily = self._daily_diagnostics(response)
            if daily is None:
                missing_days += 1
                for state in fields.values():
                    state["complete"] = False
                current += timedelta(days=1)
                continue

            daily_record_count = self._non_negative_int(daily.get("record_count"))
            if daily_record_count is None:
                missing_days += 1
                for state in fields.values():
                    state["complete"] = False
                current += timedelta(days=1)
                continue
            record_count += daily_record_count

            daily_fields = daily.get("fields")
            if not isinstance(daily_fields, dict):
                missing_days += 1
                for state in fields.values():
                    state["complete"] = False
                current += timedelta(days=1)
                continue

            for field in self.FIELDS:
                item = daily_fields.get(field)
                state = fields[field]
                if not isinstance(item, dict):
                    state["complete"] = False
                    continue

                observed_amount = self._decimal(item.get("observed_amount"))
                observed_records = self._non_negative_int(item.get("observed_records"))
                missing_records = self._non_negative_int(item.get("missing_records"))
                if (
                    observed_amount is None
                    or observed_records is None
                    or missing_records is None
                ):
                    state["complete"] = False
                    continue

                state["observed_amount"] += observed_amount
                state["observed_records"] += observed_records
                state["missing_records"] += missing_records
                if item.get("complete") is not True or missing_records > 0:
                    state["complete"] = False

            current += timedelta(days=1)

        serialized_fields = {}
        for field, state in fields.items():
            observed = state["observed_amount"].quantize(Decimal("0.01"))
            complete = state["complete"] is True and missing_days == 0
            serialized_fields[field] = {
                "amount": float(observed) if complete else None,
                "observed_amount": float(observed),
                "complete": complete,
                "observed_records": state["observed_records"],
                "missing_records": state["missing_records"],
            }

        complete = missing_days == 0 and all(
            item["complete"] is True for item in serialized_fields.values()
        )
        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_REVENUE_DIAGNOSTICS_READY"
                if complete
                else "PERIOD_PROFIT_REVENUE_DIAGNOSTICS_PARTIAL"
            ),
            "complete": complete,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "record_count": record_count,
            "missing_days": missing_days,
            "fields": serialized_fields,
            "source": "OZON_FINANCE_ACCRUAL_BY_DAY_RAW_COMMISSION_FIELDS",
            "read_only": True,
        }

    def _daily_diagnostics(self, response):
        if not isinstance(response, dict) or response.get("error") is True:
            return None

        diagnostics = response.get("_period_profit_revenue_diagnostics")
        if isinstance(diagnostics, dict):
            return diagnostics

        accruals = response.get("accruals")
        if not isinstance(accruals, list):
            return None

        if self._contains_commission_record(accruals):
            return None

        return {
            "record_count": 0,
            "fields": {
                field: {
                    "observed_amount": "0.00",
                    "observed_records": 0,
                    "missing_records": 0,
                    "complete": True,
                }
                for field in self.FIELDS
            },
        }

    @staticmethod
    def _contains_commission_record(accruals):
        for accrual in accruals:
            if not isinstance(accrual, dict):
                continue
            if accrual.get("accrued_category") != "POSTING":
                continue
            posting = accrual.get("posting")
            if not isinstance(posting, dict):
                continue
            products = posting.get("products")
            if not isinstance(products, list):
                continue
            for product in products:
                if isinstance(product, dict) and isinstance(product.get("commission"), dict):
                    return True
        return False

    def _unavailable(self, code):
        return {
            "error": False,
            "status": code,
            "complete": False,
            "record_count": None,
            "missing_days": None,
            "fields": {
                field: {
                    "amount": None,
                    "observed_amount": None,
                    "complete": False,
                    "observed_records": None,
                    "missing_records": None,
                }
                for field in self.FIELDS
            },
            "source": "OZON_FINANCE_ACCRUAL_BY_DAY_RAW_COMMISSION_FIELDS",
            "read_only": True,
        }

    @staticmethod
    def _date(value):
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decimal(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number.is_finite() else None

    @staticmethod
    def _non_negative_int(value):
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if number >= 0 else None


def build_period_profit_revenue_diagnostics(finance_service, date_from, date_to):
    service = PeriodProfitRevenueDiagnosticsSummaryService(None, finance_service)
    return service._aggregate(date_from, date_to)
