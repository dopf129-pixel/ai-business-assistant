import copy
import time
from decimal import Decimal, InvalidOperation

from api.ozon_client import OzonClient


class PeriodProfitOzonClient(OzonClient):
    """Read-only Ozon client with Period Profit retry and strict finance validation."""

    TRANSIENT_STATUS_CODES = {408, 500, 502, 503, 504}
    FINANCE_ACCRUAL_BY_DAY = "/v1/finance/accrual/by-day"
    REVENUE_DIAGNOSTIC_FIELDS = (
        "sale_amount",
        "seller_price",
        "sale_price",
        "bonus",
        "coinvestment",
    )

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        result = None

        for attempt in range(1, int(max_attempts) + 1):
            result = super()._post(
                endpoint,
                data,
                timeout=timeout,
                max_attempts=max_attempts,
            )

            if not isinstance(result, dict) or result.get("error") is not True:
                return self._normalize_period_profit_finance(endpoint, result)

            status_code = result.get("status_code")
            if status_code not in self.TRANSIENT_STATUS_CODES:
                return result

            if attempt >= int(max_attempts):
                return result

            time.sleep(2 ** attempt)

        return result

    def _normalize_period_profit_finance(self, endpoint, result):
        if endpoint != self.FINANCE_ACCRUAL_BY_DAY:
            return result

        if not isinstance(result, dict):
            return result

        accruals = result.get("accruals")
        if not isinstance(accruals, list):
            return self._finance_money_error()

        normalized = copy.deepcopy(result)
        diagnostics = self._empty_revenue_diagnostics()

        for accrual in normalized.get("accruals", []):
            if not isinstance(accrual, dict):
                return self._finance_money_error()

            if not self._valid_money(accrual.get("total_amount")):
                return self._finance_money_error()

            if not self._validate_item_fees(accrual.get("item_fees")):
                return self._finance_money_error()

            if accrual.get("accrued_category") != "POSTING":
                continue

            posting = accrual.get("posting")
            if posting is None:
                continue
            if not isinstance(posting, dict):
                return self._finance_money_error()

            products = posting.get("products")
            if products is None:
                continue
            if not isinstance(products, list):
                return self._finance_money_error()

            for product in products:
                if not isinstance(product, dict):
                    return self._finance_money_error()

                commission = product.get("commission")
                if not isinstance(commission, dict):
                    return self._finance_money_error()

                self._observe_revenue_diagnostics(diagnostics, commission)

                seller_price = commission.get("seller_price")
                sale_commission = commission.get("sale_commission")
                if not self._valid_money(seller_price):
                    return self._finance_money_error()
                if not self._valid_money(sale_commission):
                    return self._finance_money_error()

                # FinanceService historically reads sale_amount for gross_sales.
                # Period Profit binds that read to the seller-facing seller_price.
                # Bonus/coinvestment stay diagnostic and are never added again.
                commission["sale_amount"] = copy.deepcopy(seller_price)

                if not self._validate_delivery(product.get("delivery")):
                    return self._finance_money_error()

        if diagnostics["record_count"] > 0:
            normalized["_period_profit_revenue_diagnostics"] = (
                self._serialize_revenue_diagnostics(diagnostics)
            )
        return normalized

    @classmethod
    def _validate_delivery(cls, delivery):
        if delivery is None:
            return True
        if not isinstance(delivery, dict):
            return False

        services = delivery.get("services")
        if services is None:
            return True
        if not isinstance(services, list):
            return False

        for service in services:
            if not isinstance(service, dict):
                return False
            if not cls._valid_money(service.get("accrued")):
                return False
        return True

    @classmethod
    def _validate_item_fees(cls, item_fees):
        if item_fees is None:
            return True
        if not isinstance(item_fees, dict):
            return False

        groups = item_fees.get("fees")
        if groups is None:
            return True
        if not isinstance(groups, list):
            return False

        for group in groups:
            if not isinstance(group, dict):
                return False
            fees = group.get("fees")
            if fees is None:
                continue
            if not isinstance(fees, list):
                return False
            for fee in fees:
                if not isinstance(fee, dict):
                    return False
                if not cls._valid_money(fee.get("accrued")):
                    return False
        return True

    @classmethod
    def _empty_revenue_diagnostics(cls):
        return {
            "record_count": 0,
            "fields": {
                field: {
                    "observed_amount": Decimal("0"),
                    "observed_records": 0,
                    "missing_records": 0,
                }
                for field in cls.REVENUE_DIAGNOSTIC_FIELDS
            },
        }

    @classmethod
    def _observe_revenue_diagnostics(cls, diagnostics, commission):
        diagnostics["record_count"] += 1
        for field in cls.REVENUE_DIAGNOSTIC_FIELDS:
            money = commission.get(field)
            amount = cls._money_decimal(money)
            state = diagnostics["fields"][field]
            if amount is None:
                state["missing_records"] += 1
                continue
            state["observed_amount"] += amount
            state["observed_records"] += 1

    @classmethod
    def _serialize_revenue_diagnostics(cls, diagnostics):
        fields = {}
        for field in cls.REVENUE_DIAGNOSTIC_FIELDS:
            source = diagnostics["fields"][field]
            missing = int(source["missing_records"])
            observed_amount = source["observed_amount"].quantize(Decimal("0.01"))
            fields[field] = {
                "amount": str(observed_amount) if missing == 0 else None,
                "observed_amount": str(observed_amount),
                "complete": missing == 0,
                "observed_records": int(source["observed_records"]),
                "missing_records": missing,
            }
        return {
            "complete": all(item["complete"] for item in fields.values()),
            "record_count": int(diagnostics["record_count"]),
            "fields": fields,
        }

    @classmethod
    def _money_decimal(cls, value):
        if not isinstance(value, dict):
            return None

        raw_amount = value.get("amount")
        if raw_amount is None:
            return None

        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError, ValueError):
            return None

        return amount if amount.is_finite() else None

    @classmethod
    def _valid_money(cls, value):
        return cls._money_decimal(value) is not None

    @staticmethod
    def _finance_money_error():
        return {
            "error": True,
            "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
            "complete": False,
        }

    # Compatibility alias retained for existing callers/tests.
    _seller_revenue_error = _finance_money_error
