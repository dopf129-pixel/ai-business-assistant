import copy
import time
from decimal import Decimal, InvalidOperation

from api.ozon_client import OzonClient


class PeriodProfitOzonClient(OzonClient):
    """Read-only Ozon client with Period Profit retry and critical finance validation."""

    TRANSIENT_STATUS_CODES = {408, 500, 502, 503, 504}
    FINANCE_ACCRUAL_BY_DAY = "/v1/finance/accrual/by-day"
    REVENUE_DIAGNOSTIC_FIELDS = (
        "sale_amount",
        "seller_price",
        "sale_price",
        "bonus",
        "coinvestment",
    )
    SALE_AMOUNT_COMPONENT_FIELDS = (
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
            return self._finance_money_error("accruals")

        normalized = copy.deepcopy(result)
        diagnostics = self._empty_revenue_diagnostics()
        completeness = self._empty_finance_completeness()

        for accrual_index, accrual in enumerate(normalized.get("accruals", [])):
            if not isinstance(accrual, dict):
                return self._finance_money_error(f"accruals[{accrual_index}]")

            if not self._valid_money(accrual.get("total_amount")):
                return self._finance_money_error(
                    f"accruals[{accrual_index}].total_amount"
                )

            self._normalize_item_fees(
                accrual,
                completeness,
                f"accruals[{accrual_index}].item_fees",
            )

            if accrual.get("accrued_category") != "POSTING":
                continue

            posting = accrual.get("posting")
            if posting is None:
                continue
            if not isinstance(posting, dict):
                return self._finance_money_error(
                    f"accruals[{accrual_index}].posting"
                )

            products = posting.get("products")
            if products is None:
                continue
            if not isinstance(products, list):
                return self._finance_money_error(
                    f"accruals[{accrual_index}].posting.products"
                )

            for product_index, product in enumerate(products):
                path = f"accruals[{accrual_index}].posting.products[{product_index}]"
                if not isinstance(product, dict):
                    return self._finance_money_error(path)

                commission = product.get("commission")
                if not isinstance(commission, dict):
                    return self._finance_money_error(path + ".commission")

                self._observe_revenue_diagnostics(diagnostics, commission)

                sale_amount = commission.get("sale_amount")
                if not self._valid_money(sale_amount):
                    recovered_sale_amount = self._recover_sale_amount_from_components(
                        commission
                    )
                    if recovered_sale_amount is None:
                        return self._finance_money_error(path + ".commission.sale_amount")
                    commission["sale_amount"] = recovered_sale_amount

                # sale_amount and total_amount are formula-critical. The following
                # values are decomposition/diagnostic fields only: their absence must
                # not make the authoritative account accrual or seller revenue unknown.
                # Unknown ancillary values are explicitly marked incomplete before a
                # parser-safe zero is inserted; they are never promoted as evidence.
                if not self._valid_money(commission.get("sale_commission")):
                    self._mark_ancillary_incomplete(
                        completeness,
                        path + ".commission.sale_commission",
                    )
                    commission["sale_commission"] = self._zero_money(commission)

                self._normalize_delivery(
                    product,
                    completeness,
                    path + ".delivery",
                )

        if diagnostics["record_count"] > 0:
            normalized["_period_profit_revenue_diagnostics"] = (
                self._serialize_revenue_diagnostics(diagnostics)
            )

        normalized["_period_profit_finance_completeness"] = completeness
        return normalized

    def _normalize_period_profit_revenue(self, endpoint, result):
        """Compatibility entry point kept for earlier seller-revenue tests/callers."""
        normalized = self._normalize_period_profit_finance(endpoint, result)
        if (
            endpoint == self.FINANCE_ACCRUAL_BY_DAY
            and isinstance(normalized, dict)
            and normalized.get("code") == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"
        ):
            return self._seller_revenue_error()
        return normalized

    @classmethod
    def _recover_sale_amount_from_components(cls, commission):
        if not isinstance(commission, dict):
            return None

        amounts = []
        for field in cls.SALE_AMOUNT_COMPONENT_FIELDS:
            amount = cls._money_decimal(commission.get(field))
            if amount is None:
                return None
            amounts.append(amount)

        total = sum(amounts, Decimal("0"))
        if not total.is_finite():
            return None

        return {
            "amount": format(total, "f"),
            "currency": cls._component_currency(commission),
        }

    @classmethod
    def _component_currency(cls, commission):
        currencies = []
        for field in cls.SALE_AMOUNT_COMPONENT_FIELDS:
            money = commission.get(field)
            if not isinstance(money, dict):
                continue
            currency = str(money.get("currency") or "").strip()
            if currency:
                currencies.append(currency)

        if currencies and all(currency == currencies[0] for currency in currencies):
            return currencies[0]
        return "RUB"

    @classmethod
    def _normalize_delivery(cls, product, completeness, path):
        delivery = product.get("delivery")
        if delivery is None:
            return
        if not isinstance(delivery, dict):
            cls._mark_ancillary_incomplete(completeness, path)
            product["delivery"] = {"services": []}
            return

        services = delivery.get("services")
        if services is None:
            return
        if not isinstance(services, list):
            cls._mark_ancillary_incomplete(completeness, path + ".services")
            delivery["services"] = []
            return

        normalized_services = []
        for index, service in enumerate(services):
            service_path = f"{path}.services[{index}]"
            if not isinstance(service, dict):
                cls._mark_ancillary_incomplete(completeness, service_path)
                continue
            if not cls._valid_money(service.get("accrued")):
                cls._mark_ancillary_incomplete(
                    completeness,
                    service_path + ".accrued",
                )
                service["accrued"] = cls._zero_money(service)
            normalized_services.append(service)
        delivery["services"] = normalized_services

    @classmethod
    def _normalize_item_fees(cls, accrual, completeness, path):
        item_fees = accrual.get("item_fees")
        if item_fees is None:
            return
        if not isinstance(item_fees, dict):
            cls._mark_ancillary_incomplete(completeness, path)
            accrual["item_fees"] = {"fees": []}
            return

        groups = item_fees.get("fees")
        if groups is None:
            return
        if not isinstance(groups, list):
            cls._mark_ancillary_incomplete(completeness, path + ".fees")
            item_fees["fees"] = []
            return

        normalized_groups = []
        for group_index, group in enumerate(groups):
            group_path = f"{path}.fees[{group_index}]"
            if not isinstance(group, dict):
                cls._mark_ancillary_incomplete(completeness, group_path)
                continue

            fees = group.get("fees")
            if fees is None:
                normalized_groups.append(group)
                continue
            if not isinstance(fees, list):
                cls._mark_ancillary_incomplete(completeness, group_path + ".fees")
                group["fees"] = []
                normalized_groups.append(group)
                continue

            normalized_fees = []
            for fee_index, fee in enumerate(fees):
                fee_path = f"{group_path}.fees[{fee_index}]"
                if not isinstance(fee, dict):
                    cls._mark_ancillary_incomplete(completeness, fee_path)
                    continue
                if not cls._valid_money(fee.get("accrued")):
                    cls._mark_ancillary_incomplete(
                        completeness,
                        fee_path + ".accrued",
                    )
                    fee["accrued"] = cls._zero_money(fee)
                normalized_fees.append(fee)
            group["fees"] = normalized_fees
            normalized_groups.append(group)
        item_fees["fees"] = normalized_groups

    @staticmethod
    def _empty_finance_completeness():
        return {
            "fee_components_included": True,
            "ancillary_incomplete_count": 0,
            "ancillary_incomplete_paths": [],
        }

    @staticmethod
    def _mark_ancillary_incomplete(completeness, path):
        completeness["fee_components_included"] = False
        completeness["ancillary_incomplete_count"] += 1
        if len(completeness["ancillary_incomplete_paths"]) < 20:
            completeness["ancillary_incomplete_paths"].append(str(path))

    @classmethod
    def _zero_money(cls, source=None):
        currency = "RUB"
        if isinstance(source, dict):
            candidate = source.get("currency")
            if candidate:
                currency = str(candidate)
        return {"amount": "0", "currency": currency}

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
    def _finance_money_error(field=None):
        result = {
            "error": True,
            "code": "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE",
            "complete": False,
        }
        if field:
            result["internal_field"] = str(field)
        return result

    @staticmethod
    def _seller_revenue_error():
        return {
            "error": True,
            "code": "FINANCE_SELLER_REVENUE_UNAVAILABLE",
            "complete": False,
        }
