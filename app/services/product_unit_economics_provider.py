from datetime import datetime
from math import isfinite


class ProductUnitEconomicsProvider:

    REQUIRED_FIELDS = (
        "product_id",
        "sku",
        "sales_count",
        "gross_sales",
        "total_cost",
        "net_accrual",
        "gross_profit"
    )

    CURRENT_EXPENSE_FIELDS = (
        "commission_amount",
        "logistics",
        "last_mile",
        "acquiring_average"
    )

    def __init__(
        self,
        tax_service=None,
        tax_mode=None,
        tax_rate=None,
        minimum_tax_rate=1.0,
        tax_configuration_service=None
    ):
        self.tax_service = tax_service
        self.tax_mode = tax_mode
        self.tax_rate = tax_rate
        self.minimum_tax_rate = minimum_tax_rate
        self.tax_configuration_service = tax_configuration_service

    def build(
        self,
        profits
    ):
        metrics = []
        tax_policy = self._resolve_tax_policy()

        for item in (profits or []):
            if not item or item.get("error"):
                continue

            if any(
                item.get(field) is None
                for field in self.REQUIRED_FIELDS
            ):
                continue

            units_sold = int(
                item.get("sales_count")
            )
            revenue = float(
                item.get("gross_sales")
            )
            product_cost = float(
                item.get("total_cost")
            )
            net_accrual = float(
                item.get("net_accrual")
            )
            gross_profit = float(
                item.get("gross_profit")
            )
            discount_points = float(
                item.get("discount_points", 0.0) or 0.0
            )

            marketplace_fees = (
                revenue - net_accrual
            )

            tax_result = self._calculate_tax(
                revenue=revenue,
                gross_profit=gross_profit,
                tax_policy=tax_policy,
                discount_points=discount_points,
            )

            if tax_result is None:
                tax = None
                tax_base = None
                net_profit = None
                profit_per_unit = None
                margin_percent = None
            else:
                tax = float(tax_result.get("tax_amount", 0) or 0)
                tax_base = self._number(tax_result.get("tax_base"))
                net_profit = gross_profit - tax
                profit_per_unit = (
                    net_profit / units_sold
                    if units_sold > 0
                    else 0.0
                )
                margin_percent = (
                    net_profit / revenue * 100
                    if revenue > 0
                    else 0.0
                )

            metrics.append(
                {
                    "product_id": str(
                        item.get("product_id")
                    ),
                    "sku": str(
                        item.get("sku")
                    ),
                    "units_sold": units_sold,
                    "revenue": round(
                        revenue,
                        2
                    ),
                    "discount_points": round(discount_points, 2),
                    "revenue_tax_base": round(
                        max(0.0, revenue - discount_points),
                        2,
                    ),
                    "tax_base": self._round(tax_base),
                    "product_cost": round(
                        product_cost,
                        2
                    ),
                    "marketplace_fees": round(
                        marketplace_fees,
                        2
                    ),
                    "tax": (
                        round(tax, 2)
                        if tax is not None
                        else None
                    ),
                    "tax_effective_percent": (
                        round(tax / revenue * 100, 2)
                        if tax is not None and revenue > 0
                        else 0.0 if tax is not None else None
                    ),
                    "net_profit": (
                        round(net_profit, 2)
                        if net_profit is not None
                        else None
                    ),
                    "profit_per_unit": (
                        round(profit_per_unit, 2)
                        if profit_per_unit is not None
                        else None
                    ),
                    "margin_percent": (
                        round(margin_percent, 2)
                        if margin_percent is not None
                        else None
                    )
                }
            )

        return metrics

    def build_current(self, facts, product_cost):
        facts = dict(facts or {})
        tax_policy = self._resolve_tax_policy()
        seller_price = self._number(
            facts.get("seller_price")
        )
        buyer_price = self._number(
            facts.get("buyer_price")
        )
        compensation = self._number(
            facts.get("ozon_discount_compensation")
        )
        discount_points = self._number(
            facts.get("discount_points_per_unit", 0.0)
        )
        requested_tax_policy = str(
            facts.get("tax_base_policy")
            or "SELLER_PRICE"
        )
        tax_base_policy = "SELLER_PRICE"
        tax_base = seller_price

        if (
            requested_tax_policy == "OZON_BUYER_PRICE"
            and tax_policy["mode"] == "USN_INCOME"
        ):
            tax_base_policy = "OZON_BUYER_PRICE"
            tax_base = buyer_price

        cost = self._number(product_cost)
        cross_docking = self._nonnegative_number(
            facts.get("cross_docking_per_unit")
        )

        values = {
            field: self._number(facts.get(field))
            for field in self.CURRENT_EXPENSE_FIELDS
        }

        missing_fields = []
        if seller_price is None:
            missing_fields.append("unit_price")
        if (
            tax_base_policy == "OZON_BUYER_PRICE"
            and buyer_price is None
        ):
            missing_fields.append("buyer_price")
        if discount_points is None:
            missing_fields.append("discount_points")
        if cost is None:
            missing_fields.append("cost")
        for field, value in values.items():
            if value is None:
                missing_fields.append(field)

        commission = values["commission_amount"]
        logistics = values["logistics"]
        last_mile = values["last_mile"]
        acquiring = values["acquiring_average"]

        marketplace_fees = None
        gross_profit = None
        tax = None
        net_profit = None
        margin_percent = None
        tax_effective_percent = None
        calculated_tax_base = None
        revenue_tax_base = (
            max(0.0, tax_base - discount_points)
            if tax_base is not None and discount_points is not None
            else None
        )

        if not missing_fields:
            marketplace_fees = sum(
                (
                    commission,
                    logistics,
                    last_mile,
                    acquiring
                )
            )
            gross_profit = (
                seller_price
                - marketplace_fees
                - cost
                - (cross_docking if cross_docking is not None else 0.0)
            )
            tax_result = self._calculate_tax(
                revenue=tax_base,
                gross_profit=gross_profit,
                tax_policy=tax_policy,
                discount_points=discount_points,
            )
            if tax_result is None:
                tax = None
                missing_fields.append("tax")
            else:
                tax = float(tax_result.get("tax_amount", 0) or 0)
                calculated_tax_base = self._number(
                    tax_result.get("tax_base")
                )
                net_profit = gross_profit - tax
                margin_percent = (
                    net_profit / seller_price * 100
                    if seller_price > 0
                    else None
                )
                tax_effective_percent = (
                    tax / seller_price * 100
                    if seller_price > 0
                    else None
                )
        elif not self.tax_service or not tax_policy["mode"]:
            missing_fields.append("tax")

        result = {
            "product_id": (
                str(facts.get("product_id"))
                if facts.get("product_id") is not None
                else None
            ),
            "sku": (
                str(facts.get("sku"))
                if facts.get("sku") is not None
                else None
            ),
            "unit_price": self._round(seller_price),
            "buyer_price": self._round(buyer_price),
            "ozon_discount_compensation": self._round(
                compensation
            ),
            "discount_points": self._round(discount_points),
            "tax_base_policy": tax_base_policy,
            "tax_base": self._round(calculated_tax_base),
            "revenue_tax_base": self._round(revenue_tax_base),
            "tax_rate": self._number(tax_policy["tax_rate"]),
            "tax_effective_percent": self._round(
                tax_effective_percent
            ),
            "cost": self._round(cost),
            "commission": self._round(commission),
            "commission_rate": self._number(
                facts.get("commission_rate")
            ),
            "logistics": self._round(logistics),
            "last_mile": self._round(last_mile),
            "acquiring": self._round(acquiring),
            "marketplace_fees": self._round(
                marketplace_fees
            ),
            "tax": self._round(tax),
            "net_profit_per_unit": self._round(
                net_profit
            ),
            "margin_percent": self._round(
                margin_percent
            ),
            "missing_fields": list(dict.fromkeys(
                missing_fields
            )),
            "as_of": facts.get("as_of"),
            "finance_sample_sales": facts.get(
                "finance_sample_sales"
            ),
            "finance_sample_days": facts.get(
                "finance_sample_days"
            )
        }
        if "cross_docking" in facts:
            cross_docking_source = facts.get("cross_docking")
            cross_docking_source = (
                cross_docking_source
                if isinstance(cross_docking_source, dict)
                else {}
            )
            result.update({
                "cross_docking_per_unit": self._round(cross_docking),
                "cross_docking_included": cross_docking is not None,
                "cross_docking_status": cross_docking_source.get("status"),
                "cross_docking_reason": cross_docking_source.get("reason"),
                # Propagate only whitelisted public evidence fields. The raw
                # source also contains SKU and supply IDs and must stay private.
                "cross_docking": {
                    key: cross_docking_source.get(key)
                    for key in (
                        "status",
                        "reason",
                        "evidence_complete",
                        "applicable_to_sku",
                        "method",
                        "date_from",
                        "date_to",
                        "expense_total",
                        "expense_by_sku",
                        "supplied_units_sku",
                        "supplied_units_store",
                        "days_complete",
                        "days_expected",
                        "denominator_kind",
                    )
                    if key in cross_docking_source
                },
            })

        result["pre_ad_margin"] = self._build_current_pre_ad_margin(
            result,
            facts,
            tax_mode=tax_policy.get("mode"),
        )

        for field in (
            "unit_economics_source_recorded_at",
            "unit_economics_observed_at",
        ):
            if field in facts and facts.get(field) is not None:
                result[field] = facts.get(field)

        return result

    def _build_current_pre_ad_margin(self, result, facts, tax_mode=None):
        known_expenses = {
            key: result.get(field)
            for key, field in (
                ("COGS", "cost"),
                ("OZON_COMMISSION", "commission"),
                ("LOGISTICS", "logistics"),
                ("LAST_MILE", "last_mile"),
                ("ACQUIRING", "acquiring"),
            )
            if result.get(field) is not None
        }
        unknown_expenses = {
            "STORAGE",
            "PLACEMENT",
            "RETURNS_AND_CANCELLATIONS",
            "UNMAPPED_NON_AD_EXPENSES",
        }
        cross_docking = result.get("cross_docking_per_unit")
        if result.get("cross_docking_included") is True and cross_docking is not None:
            known_expenses["CROSS_DOCKING"] = cross_docking
        else:
            unknown_expenses.add("CROSS_DOCKING")

        for field, key in (
            ("cost", "COGS"),
            ("commission", "OZON_COMMISSION"),
            ("logistics", "LOGISTICS"),
            ("last_mile", "LAST_MILE"),
            ("acquiring", "ACQUIRING"),
        ):
            if result.get(field) is None:
                unknown_expenses.add(key)

        included = sorted(known_expenses)
        confirmed_zero = sorted(
            key for key, amount in known_expenses.items()
            if amount == 0
        )
        missing_inputs = list(result.get("missing_fields") or [])
        price = result.get("unit_price")
        profit = result.get("net_profit_per_unit")
        tax = result.get("tax")
        margin = result.get("margin_percent")
        available = all(value is not None for value in (price, profit, tax, margin))
        source_periods = facts.get("pre_ad_source_periods")
        if not isinstance(source_periods, dict):
            source_periods = {}
        safe_periods = {}

        def is_iso_date(value):
            return (
                isinstance(value, str)
                and len(value) == 10
                and value[4] == "-"
                and value[7] == "-"
                and value[:4].isdigit()
                and value[5:7].isdigit()
                and value[8:10].isdigit()
            )

        seller_price_period = source_periods.get("seller_price")
        if isinstance(seller_price_period, dict):
            as_of = seller_price_period.get("as_of")
            if isinstance(as_of, str) and len(as_of) <= 64:
                try:
                    datetime.fromisoformat(as_of.replace("Z", "+00:00"))
                except ValueError:
                    pass
                else:
                    safe_periods["seller_price"] = {"as_of": as_of}
        finance_period = source_periods.get("current_finance_averages")
        if isinstance(finance_period, dict):
            safe_finance_period = {}
            for key in ("date_from", "date_to"):
                value = finance_period.get(key)
                if is_iso_date(value):
                    safe_finance_period[key] = value
            for key in ("requested_days", "observed_sales_days"):
                value = finance_period.get(key)
                if type(value) is int and 0 <= value <= 366:
                    safe_finance_period[key] = value
            if safe_finance_period:
                safe_periods["current_finance_averages"] = safe_finance_period
        cross_docking_period = result.get("cross_docking")
        if isinstance(cross_docking_period, dict):
            safe_cross_docking_period = {}
            for key in ("date_from", "date_to"):
                value = cross_docking_period.get(key)
                if is_iso_date(value):
                    safe_cross_docking_period[key] = value
            for key in ("days_complete", "days_expected"):
                value = cross_docking_period.get(key)
                if type(value) is int and 0 <= value <= 366:
                    safe_cross_docking_period[key] = value
            if cross_docking_period.get("denominator_kind") == "DELIVERED_CROSSDOCK_UNITS":
                safe_cross_docking_period["denominator_kind"] = "DELIVERED_CROSSDOCK_UNITS"
            if safe_cross_docking_period:
                safe_periods["cross_docking"] = safe_cross_docking_period

        return {
            "schema_version": 1,
            "basis": "CURRENT_MODEL",
            "tax_basis": "CURRENT_TAX_POLICY",
            "tax_mode": (
                tax_mode
                if isinstance(tax_mode, str) and tax_mode in {
                    "USN_INCOME",
                    "USN_INCOME_MINUS_EXPENSES",
                    "NONE",
                }
                else None
            ),
            "revenue_basis": "SELLER_REVENUE_BEFORE_DISCOUNT_POINTS",
            "currency": "RUB",
            "unit_basis": "ONE_SUCCESSFUL_UNIT",
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "price_per_unit_rub": price,
            "profit_per_unit_rub": profit,
            "margin_percent": margin,
            "tax_per_unit_rub": tax,
            "advertising_status": "UNKNOWN",
            "advertising_per_unit_rub": None,
            "expense_scope": {
                "status": "PARTIAL" if unknown_expenses else "COMPLETE",
                "known_non_ad_expenses_rub": {
                    key: known_expenses[key]
                    for key in sorted(known_expenses)
                },
                "included_expense_keys": included,
                "confirmed_zero_expense_keys": confirmed_zero,
                "unknown_non_ad_expense_keys": sorted(unknown_expenses),
                "excluded_expense_keys": [
                    "ADVERTISING",
                    "FIXED_STORE_OVERHEAD",
                ],
                "excluded_expense_reasons": {
                    "ADVERTISING": "EXCLUDED_BY_DEFINITION",
                    "FIXED_STORE_OVERHEAD": "OUTSIDE_SKU_CONTRIBUTION_SCOPE",
                },
            },
            "missing_inputs": missing_inputs,
            "reason": (
                "CURRENT_PRE_AD_INPUTS_MISSING"
                if missing_inputs
                else None if available else "SELLER_REVENUE_DENOMINATOR_UNAVAILABLE"
            ),
            "source_periods": safe_periods,
            "as_of": safe_periods.get("seller_price", {}).get("as_of"),
            "read_only": True,
            "executed": False,
        }

    def _calculate_tax(
        self,
        revenue,
        gross_profit,
        tax_policy=None,
        discount_points=0.0,
    ):
        policy = tax_policy or self._resolve_tax_policy()
        if not self.tax_service or not policy["mode"]:
            return None

        result = self.tax_service.calculate(
            mode=policy["mode"],
            revenue=revenue,
            gross_profit=gross_profit,
            tax_rate=policy["tax_rate"],
            minimum_tax_rate=(
                policy["minimum_tax_rate"]
            ),
            discount_points=discount_points,
        )

        if result.get("error"):
            return None

        return result

    def _resolve_tax_policy(self):
        if self.tax_configuration_service is None:
            return {
                "mode": self.tax_mode,
                "tax_rate": self.tax_rate,
                "minimum_tax_rate": self.minimum_tax_rate,
            }

        configuration = self.tax_configuration_service.get_policy()
        policy = (
            configuration.get("policy")
            if isinstance(configuration, dict)
            and configuration.get("configured") is True
            and isinstance(configuration.get("policy"), dict)
            else None
        )
        if policy is None:
            return {
                "mode": None,
                "tax_rate": None,
                "minimum_tax_rate": 1.0,
            }
        return {
            "mode": policy.get("mode"),
            "tax_rate": policy.get("tax_rate"),
            "minimum_tax_rate": policy.get("minimum_tax_rate", 1.0),
        }

    def _number(self, value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _nonnegative_number(self, value):
        number = self._number(value)
        if number is None or not isfinite(number) or number < 0:
            return None
        return number

    def _round(self, value):
        return (
            round(value, 2)
            if value is not None
            else None
        )
