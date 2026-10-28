"""Keep financial advertising primary and Performance CPC reconciliation-only."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class UnitEconomicsAdvertisingEvidenceService:
    """Resolve explicitly mapped SKU advertising without summing CPC twice."""

    _KIND_CATEGORIES = {
        "CPC": "ADVERTISING_CPC",
        "CPO": "ADVERTISING_CPO",
        "OTHER": "ADVERTISING_OTHER",
    }
    _COMPONENT_KEY_KINDS = {
        "FINANCE_ADVERTISING_CPC": "CPC",
        "FINANCE_ADVERTISING_CPO": "CPO",
        "FINANCE_ADVERTISING_OTHER": "OTHER",
        "FINANCE_ADVERTISING_OTHER_ACCOUNT": "OTHER",
        "FINANCE_ADVERTISING_OTHER_SKU": "OTHER",
    }
    _EXACT_ATTRIBUTIONS = frozenset({"EXACT_SKU", "EXACT_COHORT"})
    _MONEY_QUANTUM = Decimal("0.01")
    _MAX_AMOUNT = Decimal("999999999999.99")
    _WINDOW_DENOMINATORS = frozenset({"ORDERED_UNITS_WINDOW", "SOLD_UNITS_WINDOW"})

    @classmethod
    def resolve(cls, financial_snapshot, performance_snapshot=None, quantity_evidence=None):
        """Return the finance-led view, separate account totals, and CPC check."""
        finance = cls._snapshot(financial_snapshot, "SELLER_FINANCE")
        if finance is None:
            return cls._error("UNIT_ECONOMICS_AD_FINANCE_SNAPSHOT_INVALID")

        finance_result = cls._summarize_financial(finance)
        performance_result = cls._summarize_performance(performance_snapshot)
        reconciliation = cls._reconcile_cpc(finance, finance_result, performance_result)
        absolute_unit_cost = cls._absolute_unit_cost(
            finance, finance_result, quantity_evidence,
        )
        complete = finance_result["status"] == "COMPLETE"
        return {
            "error": False,
            "status": "COMPLETE" if complete else "INCOMPLETE",
            "identity": finance["identity"],
            "financial": finance_result,
            "performance_reconciliation": reconciliation,
            "absolute_unit_cost": absolute_unit_cost,
            "warnings": cls._warnings(
                finance_result, performance_result, reconciliation, absolute_unit_cost,
            ),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _summarize_financial(cls, snapshot):
        groups = {kind: [] for kind in cls._KIND_CATEGORIES}
        for component in snapshot["components"]:
            kind = cls._kind_for_component(component)
            if kind is not None:
                groups[kind].append(component)

        source_complete = snapshot["coverage"]["complete"] is True and snapshot["completeness"] in {
            "COMPLETE", "CONFIRMED_ZERO",
        }
        component_summaries = {}
        known_sku_amount = Decimal("0.00")
        additional_sku_amount = Decimal("0.00")
        account_amount = Decimal("0.00")
        window_allocated_amount = Decimal("0.00")
        account_component_count = 0
        window_component_count = 0
        unmapped_account_component_count = 0
        unmapped_advertising_count = 0
        eligible_for_model = []
        for kind, components in groups.items():
            summary = cls._summarize_kind(components, kind)
            component_summaries[kind] = summary
            if summary["known_sku_expense_rub"] is not None:
                known_sku_amount += Decimal(summary["known_sku_expense_rub"])
            if summary["additional_sku_expense_rub"] is not None:
                additional_sku_amount += Decimal(summary["additional_sku_expense_rub"])
            if summary["account_level_expense_rub"] is not None:
                account_amount += Decimal(summary["account_level_expense_rub"])
            if summary["window_allocated_expense_rub"] is not None:
                window_allocated_amount += Decimal(summary["window_allocated_expense_rub"])
            account_component_count += summary["account_component_count"]
            window_component_count += summary["window_component_count"]
            eligible_for_model.extend(summary["model_components"])

        for component in snapshot["components"]:
            if component.get("category") not in set(cls._KIND_CATEGORIES.values()):
                continue
            if cls._kind_for_component(component) is not None:
                continue
            unmapped_advertising_count += 1
            if component.get("ownership") == "UNATTRIBUTED":
                unmapped_account_component_count += 1
                amount = cls._component_amount(component)
                if amount is not None:
                    account_amount += amount
            elif component.get("attribution") == "WINDOW_ALLOCATION":
                amount = cls._component_amount(component)
                if amount is not None:
                    window_allocated_amount += amount

        kinds_complete = all(
            component_summaries[kind]["status"] == "COMPLETE"
            for kind in cls._KIND_CATEGORIES
        )
        no_unattributed = account_component_count == 0
        no_window_allocation = window_component_count == 0
        complete_for_sku = (
            source_complete and kinds_complete and no_unattributed
            and no_window_allocation and unmapped_advertising_count == 0
        )
        status = "COMPLETE" if complete_for_sku else (
            "CONFLICT" if snapshot["completeness"] == "CONFLICT"
            or any(item["status"] == "CONFLICT" for item in component_summaries.values())
            else "PARTIAL" if snapshot["completeness"] == "PARTIAL"
            or any(item["status"] == "PARTIAL" for item in component_summaries.values())
            else "INCOMPLETE"
        )
        return {
            "status": status,
            "source_complete": source_complete,
            "complete_for_sku": complete_for_sku,
            "component_status": component_summaries,
            "sku_primary_expense_rub": cls._money(additional_sku_amount) if complete_for_sku else None,
            "known_sku_scoped_expense_rub": cls._money(known_sku_amount),
            "account_level_expense_rub": cls._money(account_amount),
            "window_allocated_expense_rub": cls._money(window_allocated_amount),
            "account_component_count": account_component_count,
            "unmapped_account_component_count": unmapped_account_component_count,
            "window_component_count": window_component_count,
            "unmapped_advertising_count": unmapped_advertising_count,
            "source_window": snapshot["source_window"],
            "model_components": eligible_for_model,
        }

    @classmethod
    def _summarize_kind(cls, components, kind):
        if not components:
            return cls._empty_kind("MISSING")
        amount = Decimal("0.00")
        known_sku_amount = Decimal("0.00")
        base_included_amount = Decimal("0.00")
        reconciliation_only_amount = Decimal("0.00")
        account_amount = Decimal("0.00")
        window_amount = Decimal("0.00")
        account_component_count = 0
        window_component_count = 0
        model_components = []
        status = "COMPLETE"
        reasons = []
        for component in components:
            component_status = component.get("status")
            if component_status not in {"PRESENT", "CONFIRMED_ZERO"}:
                reasons.append(component_status or "UNKNOWN_STATUS")
                status = cls._merge_status(
                    status, "CONFLICT" if component_status == "CONFLICT" else "PARTIAL",
                )
                continue
            if not cls._component_category_matches(component, kind):
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("COMPONENT_CATEGORY_KEY_MISMATCH")
                continue
            value = cls._component_amount(component)
            if value is None:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("AMOUNT_INVALID")
                continue
            if component_status == "CONFIRMED_ZERO":
                continue
            ownership = component.get("ownership")
            attribution = component.get("attribution")
            if ownership == "ADDITIONAL" and attribution in cls._EXACT_ATTRIBUTIONS:
                amount += value
                known_sku_amount += value
                if component.get("origin") in {"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION"}:
                    model_components.append({
                        "component_key": component["component_key"],
                        "expense_rub": cls._money(value),
                        "recurrence": component.get("recurrence", "UNKNOWN"),
                        "origin": component.get("origin"),
                    })
                else:
                    status = cls._merge_status(status, "PARTIAL")
                    reasons.append("ADVERTISING_MAPPING_NOT_CONFIRMED")
            elif attribution in cls._EXACT_ATTRIBUTIONS and ownership == "BASE_ALREADY_INCLUDED":
                known_sku_amount += value
                base_included_amount += value
            elif attribution in cls._EXACT_ATTRIBUTIONS and ownership == "RECONCILIATION_ONLY":
                known_sku_amount += value
                reconciliation_only_amount += value
            elif ownership == "ADDITIONAL" and attribution == "WINDOW_ALLOCATION":
                window_amount += value
                window_component_count += 1
                reasons.append("WINDOW_ALLOCATION_REQUIRES_EXPLICIT_MODEL_SCOPE")
            elif ownership == "UNATTRIBUTED" or attribution == "UNATTRIBUTED":
                account_amount += value
                account_component_count += 1
                reasons.append("ACCOUNT_LEVEL_EXPENSE_NOT_ALLOCATED_TO_SKU")
            elif ownership in {"BASE_ALREADY_INCLUDED", "RECONCILIATION_ONLY"}:
                continue
            else:
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("OWNERSHIP_OR_ATTRIBUTION_UNKNOWN")
        if status == "COMPLETE" and (account_component_count or window_component_count):
            status = "INCOMPLETE"
        return {
            "status": status,
            "known_sku_expense_rub": cls._money(known_sku_amount),
            "additional_sku_expense_rub": cls._money(amount),
            "base_included_expense_rub": cls._money(base_included_amount),
            "reconciliation_only_expense_rub": cls._money(reconciliation_only_amount),
            "account_level_expense_rub": cls._money(account_amount),
            "window_allocated_expense_rub": cls._money(window_amount),
            "account_component_count": account_component_count,
            "window_component_count": window_component_count,
            "component_count": len(components),
            "reasons": sorted(set(reasons)),
            "model_components": model_components,
        }

    @classmethod
    def _summarize_performance(cls, snapshot):
        if snapshot is None:
            return {"status": "UNAVAILABLE", "cpc_expense_rub": None}
        normalized = cls._snapshot(snapshot, "PERFORMANCE")
        if normalized is None:
            return {"status": "INVALID", "cpc_expense_rub": None}
        if normalized["coverage"]["complete"] is not True or normalized["completeness"] not in {
            "COMPLETE", "CONFIRMED_ZERO",
        }:
            return {"status": "PARTIAL", "cpc_expense_rub": None}
        components = []
        unsupported = 0
        unmapped = 0
        for component in normalized["components"]:
            if component.get("component_key") != "PERFORMANCE_ADVERTISING_CPC":
                if component.get("category") in {"ADVERTISING_CPC", "ADVERTISING_CPO", "ADVERTISING_OTHER"}:
                    unmapped += 1
                    if component.get("category") != "ADVERTISING_CPC":
                        unsupported += 1
                continue
            if component.get("category") not in {None, "ADVERTISING_CPC"}:
                unmapped += 1
                continue
            if component.get("status") == "PRESENT" and (
                component.get("ownership") != "RECONCILIATION_ONLY"
                or component.get("attribution") not in cls._EXACT_ATTRIBUTIONS
                or component.get("origin") not in {"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION"}
            ):
                unmapped += 1
                continue
            if component.get("status") in {"PRESENT", "CONFIRMED_ZERO"}:
                components.append(component)
        if not components:
            return {
                "status": "MISSING_CPC", "cpc_expense_rub": None,
                "unsupported_non_cpc_types": unsupported,
                "unmapped_advertising_count": unmapped,
                "identity": normalized["identity"],
                "source_window": normalized["source_window"],
            }
        total = Decimal("0.00")
        for component in components:
            if component.get("status") not in {"PRESENT", "CONFIRMED_ZERO"}:
                return {
                    "status": "CONFLICT", "cpc_expense_rub": None,
                    "unsupported_non_cpc_types": unsupported,
                    "unmapped_advertising_count": unmapped,
                    "identity": normalized["identity"],
                    "source_window": normalized["source_window"],
                }
            amount = cls._component_amount(component)
            if amount is None:
                return {
                    "status": "INVALID", "cpc_expense_rub": None,
                    "unsupported_non_cpc_types": unsupported,
                    "unmapped_advertising_count": unmapped,
                    "identity": normalized["identity"],
                    "source_window": normalized["source_window"],
                }
            total += amount
        return {
            "status": "COMPLETE",
            "cpc_expense_rub": cls._money(total),
            "unsupported_non_cpc_types": unsupported,
            "unmapped_advertising_count": unmapped,
            "identity": normalized["identity"],
            "source_window": normalized["source_window"],
            "source_scope": "RECONCILIATION_ONLY",
        }

    @classmethod
    def _reconcile_cpc(cls, financial_snapshot, financial, performance):
        finance_cpc = financial["component_status"]["CPC"]
        finance_amount = (
            finance_cpc["known_sku_expense_rub"]
            if finance_cpc["status"] == "COMPLETE" else None
        )
        performance_amount = performance.get("cpc_expense_rub")
        result = {
            "status": "UNAVAILABLE",
            "financial_primary_rub": finance_amount,
            "performance_reconciliation_rub": performance_amount,
            "difference_rub": None,
            "performance_is_additional_expense": False,
        }
        if performance.get("status") != "COMPLETE":
            result["status"] = performance.get("status", "UNAVAILABLE")
            return result
        if finance_amount is None:
            result["status"] = "FINANCIAL_CPC_NOT_CONFIRMED"
            return result
        finance_window = financial_snapshot["source_window"]
        performance_window = performance["source_window"]
        if finance_window["timezone"] == "UNKNOWN" or performance_window["timezone"] == "UNKNOWN":
            result["status"] = "TIMEZONE_UNKNOWN"
            return result
        if performance.get("identity") != financial_snapshot["identity"]:
            result["status"] = "IDENTITY_MISMATCH"
            result["performance_reconciliation_rub"] = None
            return result
        if not cls._same_calendar_window(
            financial_snapshot["source_window"], performance["source_window"],
        ):
            result["status"] = "CALENDAR_WINDOW_MISMATCH"
            return result
        if finance_window["date_basis"] != performance_window["date_basis"]:
            result["status"] = "DATE_BASIS_MISMATCH"
            return result
        result["status"] = "COMPARABLE_WINDOW"
        result["difference_rub"] = cls._money(
            Decimal(performance_amount) - Decimal(finance_amount),
        )
        return result

    @classmethod
    def _absolute_unit_cost(cls, finance_snapshot, financial, quantity):
        base = {
            "status": "UNAVAILABLE",
            "expense_rub": None,
            "denominator_units": None,
            "denominator_kind": None,
            "unit_expense_rub": None,
            "model_scope": "WINDOW_COST_ALLOCATION",
        }
        if financial["complete_for_sku"] is not True:
            base["reason"] = "FINANCIAL_ADVERTISING_SCOPE_INCOMPLETE"
            return base
        if not isinstance(quantity, dict):
            base["reason"] = "COMPATIBLE_QUANTITY_UNAVAILABLE"
            return base
        if (
            quantity.get("identity") != finance_snapshot["identity"]
            or quantity.get("complete") is not True
            or quantity.get("status") != "COMPLETE"
        ):
            base["reason"] = "QUANTITY_EVIDENCE_INCOMPLETE_OR_MISMATCHED"
            return base
        quantity_window = quantity.get("source_window")
        finance_window = finance_snapshot["source_window"]
        if not cls._same_calendar_window(finance_window, quantity_window):
            base["reason"] = "QUANTITY_WINDOW_MISMATCH"
            return base
        units = quantity.get("denominator_units")
        denominator_kind = quantity.get("denominator_kind")
        if type(units) is not int or units <= 0 or denominator_kind not in cls._WINDOW_DENOMINATORS:
            base["reason"] = "COMPATIBLE_DENOMINATOR_UNAVAILABLE"
            return base
        components = financial["model_components"]
        if any(Decimal(item["expense_rub"]) < 0 for item in components):
            base["status"] = "REVIEW_REQUIRED"
            base["expense_rub"] = financial["sku_primary_expense_rub"]
            base["reason"] = "NET_CREDIT_REQUIRES_REVIEW"
            return base
        if any(item["recurrence"] != "RECURRING" for item in components):
            base["reason"] = "ONE_OFF_OR_UNKNOWN_RECURRENCE"
            return base
        if any(item["origin"] not in {"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION"} for item in components):
            base["reason"] = "ADVERTISING_MAPPING_NOT_CONFIRMED"
            return base
        numerator = Decimal(financial["sku_primary_expense_rub"])
        rate = (numerator / Decimal(units)).quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        return {
            "status": "AVAILABLE",
            "expense_rub": cls._money(numerator),
            "denominator_units": units,
            "denominator_kind": denominator_kind,
            "unit_expense_rub": cls._money(rate),
            "model_scope": "WINDOW_COST_ALLOCATION",
            "source_window": finance_window,
            "quantity_window": quantity_window,
            "date_basis_warning": (
                None if finance_window["date_basis"] == quantity_window.get("date_basis")
                else "SOURCE_DATE_BASES_DIFFER; THIS_IS_ONLY_A_WINDOW_ALLOCATION"
            ),
        }

    @classmethod
    def _kind_for_component(cls, component):
        return cls._COMPONENT_KEY_KINDS.get(component.get("component_key"))

    @classmethod
    def _component_category_matches(cls, component, kind):
        expected = cls._KIND_CATEGORIES[kind]
        if component.get("status") == "CONFIRMED_ZERO":
            return component.get("category") in {None, expected}
        return component.get("category") == expected

    @staticmethod
    def _merge_status(current, incoming):
        order = {"COMPLETE": 0, "INCOMPLETE": 1, "PARTIAL": 2, "CONFLICT": 3}
        return incoming if order.get(incoming, 0) > order.get(current, 0) else current

    @classmethod
    def _snapshot(cls, value, expected_source):
        if not isinstance(value, dict):
            return None
        identity = value.get("identity")
        source_window = value.get("source_window")
        coverage = value.get("coverage")
        components = value.get("components")
        if (
            value.get("error") is not False
            or value.get("source") != expected_source
            or not cls._valid_identity(identity)
            or not cls._valid_window(source_window)
            or not isinstance(coverage, dict) or type(coverage.get("complete")) is not bool
            or value.get("completeness") not in {
                "COMPLETE", "CONFIRMED_ZERO", "PARTIAL", "UNAVAILABLE", "UNKNOWN", "CONFLICT",
            }
            or not isinstance(components, list) or len(components) > 64
            or any(not isinstance(item, dict) for item in components)
        ):
            return None
        return {
            "identity": dict(identity), "source_window": dict(source_window),
            "coverage": dict(coverage), "completeness": value["completeness"],
            "components": [dict(item) for item in components],
        }

    @staticmethod
    def _valid_identity(value):
        keys = {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
        return (
            isinstance(value, dict) and set(value) == keys
            and all(isinstance(value.get(key), str) and value[key].strip() for key in keys)
            and value.get("sale_schema") in {"FBO", "FBS"}
        )

    @staticmethod
    def _valid_window(value):
        keys = {"from_date", "to_date", "date_basis", "timezone"}
        if not isinstance(value, dict) or set(value) != keys:
            return False
        if not all(isinstance(value.get(key), str) and value[key] for key in keys):
            return False
        try:
            return date.fromisoformat(value["from_date"]) <= date.fromisoformat(value["to_date"])
        except ValueError:
            return False

    @classmethod
    def _component_amount(cls, component):
        raw = component.get("normalized_expense_rub")
        if not isinstance(raw, str) or len(raw) > 32:
            return None
        try:
            amount = Decimal(raw)
        except (InvalidOperation, ValueError):
            return None
        if not amount.is_finite() or abs(amount) > cls._MAX_AMOUNT:
            return None
        return amount.quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    @classmethod
    def _same_calendar_window(cls, first, second):
        return (
            cls._valid_window(first) and cls._valid_window(second)
            and first.get("from_date") == second.get("from_date")
            and first.get("to_date") == second.get("to_date")
            and first.get("timezone") == second.get("timezone")
            and first.get("timezone") != "UNKNOWN"
        )

    @classmethod
    def _warnings(cls, financial, performance, reconciliation, unit_cost):
        warnings = []
        if financial["complete_for_sku"] is not True:
            warnings.append("FINANCIAL_ADVERTISING_SCOPE_INCOMPLETE; UNKNOWN_TYPES_ARE_NOT_ZERO")
        if financial["account_component_count"] or financial["unmapped_account_component_count"]:
            warnings.append("ACCOUNT_LEVEL_ADVERTISING_NOT_ALLOCATED_TO_SKU")
        if financial["unmapped_advertising_count"]:
            warnings.append("ADVERTISING_MAPPING_NOT_CONFIRMED")
        if financial["window_component_count"]:
            warnings.append("WINDOW_ALLOCATION_REQUIRES_EXPLICIT_MODEL_SCOPE")
        if performance.get("unsupported_non_cpc_types", 0):
            warnings.append("PERFORMANCE_NON_CPC_TYPES_NOT_INCLUDED")
        if performance.get("unmapped_advertising_count", 0):
            warnings.append("PERFORMANCE_ADVERTISING_MAPPING_NOT_CONFIRMED")
        if reconciliation["status"] in {
            "DATE_BASIS_MISMATCH", "CALENDAR_WINDOW_MISMATCH", "TIMEZONE_UNKNOWN",
            "IDENTITY_MISMATCH",
        }:
            warnings.append("PERFORMANCE_CPC_IS_RECONCILIATION_ONLY_AND_WINDOWS_ARE_NOT_COMPARABLE")
        if unit_cost.get("status") != "AVAILABLE":
            warnings.append(unit_cost.get("reason", "ADVERTISING_UNIT_COST_UNAVAILABLE"))
        return sorted(set(warnings))

    @classmethod
    def _empty_kind(cls, status):
        return {
            "status": status, "known_sku_expense_rub": None,
            "additional_sku_expense_rub": None,
            "base_included_expense_rub": "0.00",
            "reconciliation_only_expense_rub": "0.00",
            "account_level_expense_rub": "0.00",
            "window_allocated_expense_rub": "0.00",
            "account_component_count": 0, "window_component_count": 0,
            "unmapped_account_component_count": 0,
            "component_count": 0, "reasons": [status], "model_components": [],
        }

    @staticmethod
    def _money(value):
        amount = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(abs(amount) if amount.is_zero() else amount, ".2f")

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
