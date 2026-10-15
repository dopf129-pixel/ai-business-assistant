from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4


class UnitPriceScenarioService:
    """Pure calculator for one-unit seller-price planning scenarios."""

    VERSION = 1
    MONEY_FIELDS = (
        "price",
        "cost",
        "logistics_per_unit",
        "last_mile_per_unit",
        "acquiring_per_unit",
    )
    RATE_FIELDS = (
        "commission_rate",
        "advertising_rate",
        "discount_points_rate",
    )
    TAX_RATE_FIELDS = ("tax_rate", "minimum_tax_rate")
    REQUIRED_FIELDS = (
        "price",
        "cost",
        "commission_rate",
        "logistics_per_unit",
        "last_mile_per_unit",
        "acquiring_per_unit",
        "advertising_rate",
        "discount_points_rate",
        "tax_mode",
    )
    UNITS = {
        "price": "RUB/unit",
        "cost": "RUB/unit",
        "commission_rate": "percent",
        "logistics_per_unit": "RUB/unit",
        "last_mile_per_unit": "RUB/unit",
        "acquiring_per_unit": "RUB/unit",
        "advertising_rate": "percent",
        "discount_points_rate": "percent",
        "tax_rate": "percent",
        "minimum_tax_rate": "percent",
    }
    _CENT = Decimal("0.01")
    _HUNDRED = Decimal("100")
    # Decimal is eventually passed through the existing float-based tax
    # service. Keep values inside a cents-safe technical representation range.
    MAX_INPUT_DIGITS = 15
    # Source-derived weighted rates can be recurring decimals (for example,
    # 50 / 300 * 100). Rates are bounded to [0, 100], so allowing the Decimal
    # context precision here does not weaken the amount/magnitude guard.
    MAX_RATE_INPUT_DIGITS = 28
    MAX_INPUT_ADJUSTED_EXPONENT = 12
    MIN_INPUT_ADJUSTED_EXPONENT = -12

    def __init__(self, tax_service):
        self.tax_service = tax_service

    def calculate(self, inputs, identity=None, provenance=None, sources=None):
        inputs = dict(inputs or {})
        identity = dict(identity or {})
        provenance = dict(provenance or {})
        sources = dict(sources or {})
        normalized, missing, invalid = self._normalize(inputs)
        try:
            calculated = self._calculate_components(normalized)
        except (InvalidOperation, ArithmeticError, OverflowError, TypeError, ValueError):
            calculated = self._empty_calculation()
            invalid.append("calculation")

        tax_mode = inputs.get("tax_mode")
        if tax_mode in (None, ""):
            missing.append("tax_mode")
        elif str(tax_mode).upper() not in self.tax_service.SUPPORTED_MODES:
            invalid.append("tax_mode")
        elif str(tax_mode).upper() != "NONE":
            if normalized.get("tax_rate") is None:
                if "tax_rate" not in invalid:
                    missing.append("tax_rate")
            if (
                str(tax_mode).upper() == "USN_INCOME_MINUS_EXPENSES"
                and normalized.get("minimum_tax_rate") is None
            ):
                if "minimum_tax_rate" not in invalid:
                    missing.append("minimum_tax_rate")

        available = not missing and not invalid
        if available:
            try:
                calculated.update(
                    self._calculate_tax_and_profit(
                        normalized,
                        str(tax_mode).upper(),
                        calculated,
                    )
                )
            except (InvalidOperation, ArithmeticError, OverflowError, TypeError, ValueError):
                calculated.update(self._empty_tax_calculation())
            if any(
                calculated.get(field) is None
                for field in ("tax", "effective_tax_rate", "profit", "margin_percent")
            ):
                invalid.append("tax_calculation")
                available = False
        else:
            calculated.update({
                "tax": None,
                "effective_tax_rate": None,
                "profit": None,
                "margin_percent": None,
            })
        all_missing = list(dict.fromkeys(missing))
        all_invalid = list(dict.fromkeys(invalid))
        calculated = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in calculated.items()
        }

        scenario_inputs = {}
        for field in self.UNITS:
            value = normalized.get(field)
            scenario_inputs[field] = {
                "value": float(value) if value is not None else None,
                "unit": self.UNITS[field],
                "provenance": provenance.get(
                    field,
                    "manual" if field in inputs else "unknown",
                ),
            }
        scenario_inputs["tax_mode"] = {
            "value": str(tax_mode).upper() if tax_mode else None,
            "unit": "tax_mode",
            "provenance": provenance.get("tax_mode", "store_policy"),
        }

        return {
            "error": False,
            "available": available,
            "kind": "PRICE_PLANNING_SCENARIO",
            "identity": identity,
            "scenario_id": str(identity.get("scenario_id") or uuid4().hex[:16]),
            "scenario_version": self.VERSION,
            "inputs": scenario_inputs,
            "source_periods": sources.get("periods", {}),
            "as_of": sources.get("as_of"),
            "source_completeness": sources.get("completeness", {}),
            "calculated": calculated,
            "missing_inputs": all_missing,
            "invalid_inputs": all_invalid,
            "included_scope": [
                "one successful sale",
                "seller price, commission, delivery, last mile, acquiring",
                "planned advertising, cost of goods and discount points",
                "configured store tax policy",
            ],
            "excluded_scope": [
                "fixed store overhead",
                "storage and cross-docking",
                "returns and cancellations probability/effects",
                "sales volume and advertising attribution",
                "future Ozon tariff changes",
            ],
            "read_only": True,
            "executed": False,
        }

    def compare(self, inputs, current_price, identity=None, provenance=None, sources=None):
        scenario = self.calculate(
            inputs,
            identity=identity,
            provenance=provenance,
            sources=sources,
        )
        current_inputs = dict(inputs or {})
        current_inputs["price"] = current_price
        current = self.calculate(
            current_inputs,
            identity=identity,
            provenance=provenance,
            sources=sources,
        )
        scenario["comparison"] = {
            "kind": "same_assumptions_at_current_seller_price",
            "available": current["available"],
            "price": current_price,
            "profit": current["calculated"]["profit"],
            "margin_percent": current["calculated"]["margin_percent"],
        }
        return scenario

    def _normalize(self, inputs):
        normalized = {}
        missing = []
        invalid = []
        for field in self.MONEY_FIELDS + self.RATE_FIELDS + self.TAX_RATE_FIELDS:
            if field not in inputs or inputs.get(field) is None or inputs.get(field) == "":
                normalized[field] = None
                if field in self.REQUIRED_FIELDS:
                    missing.append(field)
                continue
            value = self._decimal(
                inputs.get(field),
                max_input_digits=(
                    self.MAX_RATE_INPUT_DIGITS
                    if field in self.RATE_FIELDS + self.TAX_RATE_FIELDS
                    else self.MAX_INPUT_DIGITS
                ),
            )
            if value is None:
                normalized[field] = None
                invalid.append(field)
                continue
            if field == "price":
                valid = value > 0
            elif field in self.RATE_FIELDS + self.TAX_RATE_FIELDS:
                valid = Decimal("0") <= value <= self._HUNDRED
            else:
                valid = value >= 0
            if not valid:
                normalized[field] = None
                invalid.append(field)
                continue
            normalized[field] = value

        for field in self.REQUIRED_FIELDS:
            if field not in inputs or inputs.get(field) is None or inputs.get(field) == "":
                if field not in missing:
                    missing.append(field)
        return normalized, missing, invalid

    def _calculate_components(self, values):
        price = values.get("price")
        cost = values.get("cost")
        commission_rate = values.get("commission_rate")
        ad_rate = values.get("advertising_rate")
        points_rate = values.get("discount_points_rate")
        logistics = values.get("logistics_per_unit")
        last_mile = values.get("last_mile_per_unit")
        acquiring = values.get("acquiring_per_unit")

        points = (
            self._money_decimal(price * points_rate / self._HUNDRED)
            if price is not None and points_rate is not None
            else None
        )
        commission = (
            self._money_decimal(price * commission_rate / self._HUNDRED)
            if price is not None and commission_rate is not None
            else None
        )
        advertising = (
            self._money_decimal(price * ad_rate / self._HUNDRED)
            if price is not None and ad_rate is not None
            else None
        )
        fees = (
            self._money_decimal(logistics + last_mile + acquiring)
            if None not in (logistics, last_mile, acquiring)
            else None
        )
        taxable_revenue = (
            self._money_decimal(max(Decimal("0"), price - points))
            if price is not None and points is not None
            else None
        )

        profit_before_tax = None
        if None not in (price, cost, commission, advertising, fees):
            profit_before_tax = self._money_decimal(
                price - commission - fees - cost - advertising
            )
        return {
            "revenue": self._money_decimal(price) if price is not None else None,
            "discount_points": points,
            "taxable_revenue": taxable_revenue,
            "commission": commission,
            "advertising": advertising,
            "fees": fees,
            "profit_before_tax": profit_before_tax,
            "tax": None,
            "effective_tax_rate": None,
            "profit": None,
            "margin_percent": None,
        }

    def _calculate_tax_and_profit(self, values, mode, components):
        profit_before_tax = components["profit_before_tax"]
        if profit_before_tax is None:
            return {
                "tax": None,
                "effective_tax_rate": None,
                "profit": None,
                "margin_percent": None,
            }
        try:
            tax_result = self.tax_service.calculate(
                mode=mode,
                revenue=float(values["price"]),
                gross_profit=float(profit_before_tax),
                tax_rate=(
                    float(values["tax_rate"])
                    if values.get("tax_rate") is not None
                    else None
                ),
                minimum_tax_rate=(
                    float(values["minimum_tax_rate"])
                    if values.get("minimum_tax_rate") is not None
                    else None
                ),
                discount_points=float(components["discount_points"]),
            )
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            return self._empty_tax_calculation()
        if tax_result.get("error") or not tax_result.get("configured"):
            return {
                "tax": None,
                "effective_tax_rate": None,
                "profit": None,
                "margin_percent": None,
            }
        price = values["price"]
        tax = self._decimal(tax_result.get("tax_amount"))
        if tax is None:
            return {
                "tax": None,
                "effective_tax_rate": None,
                "profit": None,
                "margin_percent": None,
            }
        profit = self._money_decimal(profit_before_tax - tax)
        effective_tax_rate = self._percent(tax / price * self._HUNDRED)
        margin_percent = self._percent(profit / price * self._HUNDRED)
        return {
            "tax": self._money(tax),
            "effective_tax_rate": effective_tax_rate,
            "profit": profit,
            "margin_percent": margin_percent,
        }

    def _decimal(self, value, max_input_digits=None):
        if isinstance(value, bool):
            return None
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, (str, int, float)):
            text = str(value).strip().replace("\u00a0", "").replace(" ", "")
            if len(text) > 64 or ("," in text and "." in text):
                return None
            if "," in text:
                text = text.replace(",", ".")
            try:
                number = Decimal(text)
            except InvalidOperation:
                return None
        else:
            return None
        if not number.is_finite():
            return None
        if number.is_zero():
            return number
        digits = len(number.as_tuple().digits)
        adjusted = number.adjusted()
        if (
            digits > (max_input_digits or self.MAX_INPUT_DIGITS)
            or adjusted > self.MAX_INPUT_ADJUSTED_EXPONENT
            or adjusted < self.MIN_INPUT_ADJUSTED_EXPONENT
        ):
            return None
        return number

    @staticmethod
    def _empty_calculation():
        return {
            "revenue": None,
            "discount_points": None,
            "taxable_revenue": None,
            "commission": None,
            "advertising": None,
            "fees": None,
            "profit_before_tax": None,
            **UnitPriceScenarioService._empty_tax_calculation(),
        }

    @staticmethod
    def _empty_tax_calculation():
        return {
            "tax": None,
            "effective_tax_rate": None,
            "profit": None,
            "margin_percent": None,
        }

    def _money(self, value):
        return float(self._money_decimal(value))

    def _money_decimal(self, value):
        return value.quantize(self._CENT, rounding=ROUND_HALF_UP)

    def _percent(self, value):
        rounded = value.quantize(self._CENT, rounding=ROUND_HALF_UP)
        return 0.0 if rounded == 0 else float(rounded)
