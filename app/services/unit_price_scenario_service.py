from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from datetime import date
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnitPriceScenarioService:
    """Pure calculator for one-unit seller-price planning scenarios."""

    VERSION = 2
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
        "cross_docking_per_unit": "RUB/supplied_unit",
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
    EXTENDED_COMPONENT_LIMIT = 64
    EXTENDED_MAX_UNITS = 1_000_000_000
    EXTENDED_MAX_AMOUNT = Decimal("999999999999.99")
    EXTENDED_MODES = frozenset({"WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT"})
    EXTENDED_SOURCE_COMPLETENESS = frozenset({"COMPLETE", "PARTIAL", "UNKNOWN", "CONFLICT"})
    EXTENDED_ASSUMPTIONS = frozenset({
        "OWNER_PRICE", "OWNER_COST", "OWNER_TARIFF_OVERRIDE", "OWNER_ADVERTISING",
        "OWNER_DISCOUNT_POINTS",
    })
    _COMPONENT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _SAFE_REVISION_RE = re.compile(r"^[a-f0-9]{64}$")
    _SAFE_POLICY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

    def __init__(self, tax_service):
        self.tax_service = tax_service

    def calculate(
        self, inputs, identity=None, provenance=None, sources=None, extended_scenario=None,
    ):
        inputs = dict(inputs or {})
        identity = dict(identity or {})
        provenance = dict(provenance or {})
        sources = dict(sources or {})
        extended = None
        if extended_scenario is not None:
            extended, extended_error = self._normalize_extended_scenario(extended_scenario)
            if extended_error:
                return self._extended_unavailable_result(
                    extended_error, extended_scenario, identity, sources,
                )
            if extended["calculation_mode"] == "STRICT_RETAINED_COHORT":
                return self._extended_unavailable_result(
                    "STRICT_RETAINED_COHORT_NOT_IMPLEMENTED", extended_scenario, identity, sources,
                )
            if extended["source_completeness"] != "COMPLETE":
                return self._extended_unavailable_result(
                    "SOURCE_EVIDENCE_" + extended["source_completeness"],
                    extended_scenario, identity, sources,
                )
            if self._has_unscoped_cross_docking(inputs):
                return self._extended_unavailable_result(
                    "CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE",
                    extended_scenario, identity, sources,
                )
        normalized, missing, invalid = self._normalize(inputs)
        try:
            calculated = self._calculate_components(
                normalized,
                additional_expenses=(extended["additional_expense_per_unit"] if extended else None),
            )
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
            if field == "cross_docking_per_unit" and field not in normalized:
                continue
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

        result = {
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
        if extended is not None:
            result["extended_calculation"] = self._public_extended_calculation(
                extended, status="APPLIED" if available else "UNAVAILABLE",
            )
            if extended["additional_expense_per_unit"] > 0:
                result["included_scope"].append(
                    "confirmed additional expenses allocated per compatible window unit"
                )
            if extended["excluded_component_statuses"]:
                result["excluded_scope"].append(
                    "components excluded or unknown by the selected expense evidence"
                )
        if "cross_docking" in calculated:
            cross_docking_included = calculated["cross_docking"] is not None
            result["cross_docking_included"] = cross_docking_included
            completeness = sources.get("completeness") or {}
            cross_docking_completeness = (
                completeness.get("cross_docking")
                if isinstance(completeness, dict)
                else {}
            )
            result["cross_docking_status"] = (
                cross_docking_completeness.get("status")
                if isinstance(cross_docking_completeness, dict)
                else None
            )
            result["cross_docking_reason"] = (
                cross_docking_completeness.get("reason")
                if isinstance(cross_docking_completeness, dict)
                else None
            )
            if cross_docking_included:
                result["included_scope"].append(
                    "56-day cross-docking expense per actually supplied unit"
                )
                result["excluded_scope"].remove("storage and cross-docking")
                result["excluded_scope"].append("storage")
            else:
                result["excluded_scope"].append(
                    "cross-docking not included because complete applicable evidence is unavailable"
                )
        return result

    def calculate_components_only(self, inputs, extended_scenario=None):
        """Return rounded one-sale money components without invoking TaxService.

        Aggregate planning flows use this projection to multiply canonical
        per-sale amounts by quantity, then calculate tax once on the aggregate.
        """
        extended = None
        if extended_scenario is not None:
            extended, extended_error = self._normalize_extended_scenario(extended_scenario)
            if extended_error:
                return self._extended_components_unavailable(extended_error)
            if extended["calculation_mode"] == "STRICT_RETAINED_COHORT":
                return self._extended_components_unavailable(
                    "STRICT_RETAINED_COHORT_NOT_IMPLEMENTED"
                )
            if extended["source_completeness"] != "COMPLETE":
                return self._extended_components_unavailable(
                    "SOURCE_EVIDENCE_" + extended["source_completeness"]
                )
            if self._has_unscoped_cross_docking(inputs):
                return self._extended_components_unavailable(
                    "CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE"
                )
        normalized, missing, invalid = self._normalize(dict(inputs or {}))
        try:
            calculated = self._calculate_components(
                normalized,
                additional_expenses=(extended["additional_expense_per_unit"] if extended else None),
            )
        except (InvalidOperation, ArithmeticError, OverflowError, TypeError, ValueError):
            calculated = self._empty_calculation()
            invalid.append("calculation")
        calculated = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in calculated.items()
        }
        # The aggregate planning view needs the canonical rounded unit cost
        # alongside the already-calculated contribution.
        normalized_cost = normalized.get("cost")
        calculated["cost"] = (
            float(self._money_decimal(normalized_cost))
            if normalized_cost is not None else None
        )
        result = {
            "error": False,
            "available": not missing and not invalid,
            "calculated": calculated,
            "missing_inputs": list(dict.fromkeys(missing)),
            "invalid_inputs": list(dict.fromkeys(invalid)),
            "read_only": True,
            "executed": False,
        }
        if extended is not None:
            result["extended_calculation"] = self._public_extended_calculation(
                extended, status="APPLIED" if result["available"] else "UNAVAILABLE",
            )
        return result

    def compare(
        self, inputs, current_price, identity=None, provenance=None, sources=None,
        extended_scenario=None,
    ):
        scenario = self.calculate(
            inputs,
            identity=identity,
            provenance=provenance,
            sources=sources,
            extended_scenario=extended_scenario,
        )
        current_inputs = dict(inputs or {})
        current_inputs["price"] = current_price
        current = self.calculate(
            current_inputs,
            identity=identity,
            provenance=provenance,
            sources=sources,
            extended_scenario=extended_scenario,
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

        # Cross-docking is an optional, source-derived component. Legacy
        # scenarios that have no such field keep their original projection.
        if "cross_docking_per_unit" in inputs:
            raw_cross_docking = inputs.get("cross_docking_per_unit")
            if raw_cross_docking in (None, ""):
                normalized["cross_docking_per_unit"] = None
            else:
                cross_docking = self._decimal(raw_cross_docking)
                if cross_docking is None or cross_docking < 0:
                    normalized["cross_docking_per_unit"] = None
                    invalid.append("cross_docking_per_unit")
                else:
                    normalized["cross_docking_per_unit"] = cross_docking

        for field in self.REQUIRED_FIELDS:
            if field not in inputs or inputs.get(field) is None or inputs.get(field) == "":
                if field not in missing:
                    missing.append(field)
        return normalized, missing, invalid

    def _calculate_components(self, values, additional_expenses=None):
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
            total_expenses = (
                price - commission - fees - cost - advertising
                - (
                    values.get("cross_docking_per_unit")
                    if values.get("cross_docking_per_unit") is not None
                    else Decimal("0")
                )
            )
            if additional_expenses is not None:
                total_expenses -= additional_expenses
            profit_before_tax = self._money_decimal(total_expenses)
        result = {
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
        if "cross_docking_per_unit" in values:
            cross_docking = values.get("cross_docking_per_unit")
            result["cross_docking"] = (
                self._money_decimal(cross_docking)
                if cross_docking is not None else None
            )
        if additional_expenses is not None:
            result["additional_unit_expenses"] = self._money_decimal(additional_expenses)
        return result

    def _normalize_extended_scenario(self, value):
        expected = {
            "schema_version", "calculation_mode", "expense_snapshot_ref",
            "quantity_evidence_ref", "expense_policy_revision", "included_component_keys",
            "excluded_component_statuses", "numerator_and_denominator_basis",
            "source_completeness", "assumed_inputs", "scope", "denominator_units",
            "components",
        }
        if not isinstance(value, dict) or set(value) != expected:
            return None, "EXTENDED_CONTRACT_INVALID"
        mode = value.get("calculation_mode")
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            return None, "EXTENDED_SCHEMA_UNSUPPORTED"
        if not isinstance(mode, str) or mode not in self.EXTENDED_MODES:
            return None, "EXTENDED_MODE_UNSUPPORTED"
        for field in ("expense_snapshot_ref", "quantity_evidence_ref"):
            reference = value.get(field)
            if reference is not None and (
                not isinstance(reference, str) or self._SAFE_REVISION_RE.fullmatch(reference) is None
            ):
                return None, "EXTENDED_REFERENCE_INVALID"
        policy_revision = value.get("expense_policy_revision")
        if (
            not isinstance(policy_revision, str)
            or self._SAFE_POLICY_RE.fullmatch(policy_revision) is None
        ):
            return None, "EXTENDED_POLICY_REVISION_INVALID"
        completeness = value.get("source_completeness")
        if not isinstance(completeness, str) or completeness not in self.EXTENDED_SOURCE_COMPLETENESS:
            return None, "EXTENDED_SOURCE_COMPLETENESS_INVALID"
        basis = value.get("numerator_and_denominator_basis")
        if not isinstance(basis, dict) or set(basis) != {"numerator", "denominator"}:
            return None, "EXTENDED_BASIS_INVALID"
        allowed_basis = (
            {"numerator": "WINDOW_EXPENSE_RUB", "denominator": "ORDERED_UNITS_WINDOW"},
            {"numerator": "WINDOW_EXPENSE_RUB", "denominator": "SOLD_UNITS_WINDOW"},
            {"numerator": "STRICT_COHORT_LOSS_RUB", "denominator": "RETAINED_UNITS_EXACT_COHORT"},
        )
        if basis not in allowed_basis:
            return None, "EXTENDED_BASIS_INVALID"
        if mode == "WINDOW_COST_ALLOCATION" and basis["numerator"] != "WINDOW_EXPENSE_RUB":
            return None, "EXTENDED_BASIS_MODE_MISMATCH"
        if mode == "STRICT_RETAINED_COHORT" and basis["numerator"] != "STRICT_COHORT_LOSS_RUB":
            return None, "EXTENDED_BASIS_MODE_MISMATCH"
        scope = self._normalize_extended_scope(value.get("scope"))
        if scope is None:
            return None, "EXTENDED_SCOPE_INVALID"
        denominator_units = value.get("denominator_units")
        if (
            type(denominator_units) is not int
            or not 1 <= denominator_units <= self.EXTENDED_MAX_UNITS
        ):
            return None, "ZERO_OR_INVALID_DENOMINATOR"
        assumptions = value.get("assumed_inputs")
        if (
            not isinstance(assumptions, list) or len(assumptions) > 16
            or any(
                not isinstance(item, str) or item not in self.EXTENDED_ASSUMPTIONS
                for item in assumptions
            )
            or len(set(assumptions)) != len(assumptions)
        ):
            return None, "EXTENDED_ASSUMPTIONS_INVALID"

        included_keys = value.get("included_component_keys")
        raw_components = value.get("components")
        excluded = value.get("excluded_component_statuses")
        if (
            not isinstance(included_keys, list) or len(included_keys) > self.EXTENDED_COMPONENT_LIMIT
            or any(not isinstance(key, str) or self._COMPONENT_KEY_RE.fullmatch(key) is None for key in included_keys)
            or included_keys != sorted(set(included_keys))
            or not isinstance(raw_components, list) or len(raw_components) > self.EXTENDED_COMPONENT_LIMIT
            or not isinstance(excluded, dict) or len(excluded) > self.EXTENDED_COMPONENT_LIMIT
        ):
            return None, "EXTENDED_COMPONENTS_INVALID"
        component_keys = []
        total_numerator = Decimal("0")
        normalized_components = []
        for component in raw_components:
            if (
                not isinstance(component, dict)
                or set(component) != {"component_key", "numerator_rub", "ownership"}
                or component.get("ownership") != "ADDITIONAL"
            ):
                return None, "EXTENDED_COMPONENT_INVALID"
            key = component.get("component_key")
            raw_amount = component.get("numerator_rub")
            if (
                not isinstance(key, str) or self._COMPONENT_KEY_RE.fullmatch(key) is None
                or not isinstance(raw_amount, str) or len(raw_amount) > 32
            ):
                return None, "EXTENDED_COMPONENT_INVALID"
            amount = self._decimal(raw_amount)
            if amount is None or amount < 0 or amount > self.EXTENDED_MAX_AMOUNT:
                return None, "EXTENDED_COMPONENT_AMOUNT_INVALID"
            if key in component_keys:
                return None, "EXTENDED_COMPONENT_DUPLICATE"
            component_keys.append(key)
            total_numerator += amount
            if total_numerator > self.EXTENDED_MAX_AMOUNT:
                return None, "EXTENDED_COMPONENT_TOTAL_TOO_LARGE"
            normalized_components.append({"component_key": key, "numerator_rub": amount})
        if component_keys != included_keys:
            return None, "EXTENDED_COMPONENT_KEYS_MISMATCH"
        for key, status in excluded.items():
            if (
                not isinstance(key, str) or self._COMPONENT_KEY_RE.fullmatch(key) is None
                or not isinstance(status, str) or status not in {"EXCLUDED", "UNKNOWN"}
                or key in component_keys
            ):
                return None, "EXTENDED_EXCLUDED_COMPONENTS_INVALID"
        if completeness == "COMPLETE" and not component_keys and not excluded:
            # A zero is explicit only when a complete source is bound to an empty
            # selected component set; missing source data never reaches this path.
            total_numerator = Decimal("0")
        additional_per_unit = self._money_decimal(total_numerator / denominator_units)
        return {
            "schema_version": 1,
            "calculation_mode": mode,
            "expense_snapshot_ref": value["expense_snapshot_ref"],
            "quantity_evidence_ref": value["quantity_evidence_ref"],
            "expense_policy_revision": policy_revision,
            "included_component_keys": component_keys,
            "excluded_component_statuses": dict(sorted(excluded.items())),
            "numerator_and_denominator_basis": dict(basis),
            "source_completeness": completeness,
            "assumed_inputs": sorted(assumptions),
            "scope": scope,
            "denominator_units": denominator_units,
            "total_numerator_rub": self._money_decimal(total_numerator),
            "additional_expense_per_unit": additional_per_unit,
        }, None

    def _normalize_extended_scope(self, value):
        fields = {"scope_kind", "from_date", "to_date", "date_basis", "timezone"}
        if not isinstance(value, dict) or set(value) != fields:
            return None
        scope_kind = value.get("scope_kind")
        if (
            not isinstance(scope_kind, str)
            or scope_kind not in {"REFERENCE_56_COMPLETED_LOCAL_DAYS", "EXPERIMENT_PHASE_WINDOW"}
        ):
            return None
        if value.get("date_basis") != "LOCAL_CALENDAR_DAY":
            return None
        timezone_name = value.get("timezone")
        if not isinstance(timezone_name, str) or not timezone_name or len(timezone_name) > 128:
            return None
        try:
            ZoneInfo(timezone_name)
            start = date.fromisoformat(value.get("from_date"))
            end = date.fromisoformat(value.get("to_date"))
        except (TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return None
        if start > end:
            return None
        days = (end - start).days + 1
        if scope_kind == "REFERENCE_56_COMPLETED_LOCAL_DAYS" and days != 56:
            return None
        if scope_kind == "EXPERIMENT_PHASE_WINDOW" and not 1 <= days <= 28:
            return None
        return {
            "scope_kind": scope_kind,
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "date_basis": "LOCAL_CALENDAR_DAY",
            "timezone": timezone_name,
        }

    @staticmethod
    def _has_unscoped_cross_docking(inputs):
        if not isinstance(inputs, dict) or "cross_docking_per_unit" not in inputs:
            return False
        return inputs.get("cross_docking_per_unit") not in (None, "")

    def _public_extended_calculation(self, extended, *, status):
        return {
            "schema_version": extended["schema_version"],
            "calculation_mode": extended["calculation_mode"],
            "status": status,
            "expense_snapshot_ref": extended["expense_snapshot_ref"],
            "quantity_evidence_ref": extended["quantity_evidence_ref"],
            "expense_policy_revision": extended["expense_policy_revision"],
            "included_component_keys": list(extended["included_component_keys"]),
            "excluded_component_statuses": dict(extended["excluded_component_statuses"]),
            "numerator_and_denominator_basis": dict(extended["numerator_and_denominator_basis"]),
            "source_completeness": extended["source_completeness"],
            "assumed_inputs": list(extended["assumed_inputs"]),
            "scope": dict(extended["scope"]),
            "total_numerator_rub": format(extended["total_numerator_rub"], ".2f"),
            "denominator_units": extended["denominator_units"],
            "denominator_kind": extended["numerator_and_denominator_basis"]["denominator"],
            "additional_expense_per_unit_rub": format(
                extended["additional_expense_per_unit"], ".2f",
            ),
        }

    def _extended_unavailable_result(self, reason, raw_contract, identity, sources):
        mode = None
        if isinstance(raw_contract, dict):
            raw_mode = raw_contract.get("calculation_mode")
            if isinstance(raw_mode, str) and raw_mode in self.EXTENDED_MODES:
                mode = raw_mode
        return {
            "error": False,
            "available": False,
            "kind": "PRICE_PLANNING_SCENARIO",
            "identity": identity,
            "scenario_id": str(identity.get("scenario_id") or uuid4().hex[:16]),
            "scenario_version": self.VERSION,
            "inputs": {},
            "source_periods": sources.get("periods", {}),
            "as_of": sources.get("as_of"),
            "source_completeness": sources.get("completeness", {}),
            "calculated": self._empty_calculation(),
            "missing_inputs": [],
            "invalid_inputs": [],
            "extended_calculation": {
                "schema_version": 1,
                "calculation_mode": mode,
                "status": "UNAVAILABLE",
                "reason": reason,
            },
            "included_scope": [],
            "excluded_scope": ["extended unit economics not applied"],
            "read_only": True,
            "executed": False,
        }

    def _extended_components_unavailable(self, reason):
        return {
            "error": False,
            "available": False,
            "calculated": self._empty_calculation(),
            "missing_inputs": [],
            "invalid_inputs": [],
            "extended_calculation": {
                "schema_version": 1,
                "status": "UNAVAILABLE",
                "reason": reason,
            },
            "read_only": True,
            "executed": False,
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
