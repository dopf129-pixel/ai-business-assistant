"""Resolve exact-cohort return costs without treating unknown COGS as zero."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


class UnitEconomicsReturnEvidenceService:
    """Pure return/non-buyout and inventory-loss evidence resolver."""

    _FEE_KEYS = {
        "CUSTOMER_RETURN": "FINANCE_CUSTOMER_RETURN_FEES",
        "CUSTOMER_NONBUYOUT": "FINANCE_CUSTOMER_NONBUYOUT_FEES",
    }
    _FEE_CATEGORY = "RETURN_NONBUYOUT"
    _EXACT_ORIGINS = frozenset({"OFFICIAL_SOURCE", "DETERMINISTIC_DERIVATION"})
    _DISPOSITIONS = frozenset({
        "SALEABLE_RESTORED", "IRRECOVERABLE_CONFIRMED", "PENDING", "UNKNOWN",
    })
    _COMPENSATION_TREATMENTS = frozenset({
        "NON_OVERLAPPING", "ALREADY_INCLUDED", "NONE_CONFIRMED", "UNKNOWN",
    })
    _MONEY_QUANTUM = Decimal("0.01")
    _MAX_AMOUNT = Decimal("999999999999.99")
    _MAX_UNITS = 1_000_000_000
    _MAX_DISPOSITIONS = 10_000
    _COHORT_REF_RE = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def resolve(cls, financial_snapshot, quantity_evidence, inventory_evidence=None):
        """Return observed fees, exact retained quantity and a gated loss rate."""
        finance = cls._financial_snapshot(financial_snapshot)
        if finance is None:
            return cls._error("UNIT_ECONOMICS_RETURN_FINANCE_SNAPSHOT_INVALID")
        quantity = cls._quantity_evidence(quantity_evidence)
        if quantity is None:
            return cls._error("UNIT_ECONOMICS_RETURN_QUANTITY_EVIDENCE_INVALID")
        if finance["identity"] != quantity["identity"]:
            return cls._error("UNIT_ECONOMICS_RETURN_IDENTITY_MISMATCH")

        cohort_matches = (
            cls._valid_cohort_ref(finance["cohort_ref"])
            and cls._valid_cohort_ref(quantity["cohort_ref"])
            and finance["cohort_ref"] == quantity["cohort_ref"]
        )
        fees = cls._summarize_fees(finance, cohort_matches)
        quantity_result = cls._summarize_quantity(quantity, cohort_matches)
        inventory = cls._summarize_inventory(
            inventory_evidence,
            identity=finance["identity"],
            cohort_ref=finance["cohort_ref"],
            confirmed_returned_units=quantity_result[
                "confirmed_returned_units_from_deliveries"
            ],
            zero_return_sample_confirmed=(
                cohort_matches and quantity_result["status"] == "COMPLETE"
                and quantity_result["confirmed_returned_units_from_deliveries"] == 0
            ),
        )
        strict_loss = cls._strict_loss(fees, quantity_result, inventory)
        window_warning = (
            None if cls._same_window(finance["source_window"], quantity["source_window"])
            else "SOURCE_WINDOWS_DIFFER; COHORT_MATCH_IS_THE_STRICT_LINK"
        )
        warnings = cls._warnings(fees, quantity_result, inventory, strict_loss)
        if not cohort_matches:
            warning = (
                "EXACT_COHORT_BINDING_UNAVAILABLE"
                if finance["cohort_ref"] is None or quantity["cohort_ref"] is None
                else "COHORT_BINDING_MISMATCH"
            )
            warnings.append(warning)
        if window_warning:
            warnings.append(window_warning)
        return {
            "error": False,
            "status": "COMPLETE" if strict_loss["status"] == "AVAILABLE" else "INCOMPLETE",
            "identity": finance["identity"],
            "fees": fees,
            "quantity": quantity_result,
            "inventory": inventory,
            "strict_retained_cohort_loss": strict_loss,
            "source_windows": {
                "financial": finance["source_window"],
                "quantity": quantity["source_window"],
            },
            "warnings": sorted(set(warnings)),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _financial_snapshot(cls, value):
        if not isinstance(value, dict) or value.get("error") is not False:
            return None
        identity = value.get("identity")
        window = value.get("source_window")
        coverage = value.get("coverage")
        components = value.get("components")
        completeness = value.get("completeness")
        cohort_ref = value.get("cohort_ref")
        if (
            value.get("source") != "SELLER_FINANCE"
            or not cls._valid_identity(identity)
            or not cls._valid_window(window)
            or not isinstance(coverage, dict)
            or type(coverage.get("complete")) is not bool
            or completeness not in {"COMPLETE", "CONFIRMED_ZERO", "PARTIAL", "UNAVAILABLE", "UNKNOWN", "CONFLICT"}
            or not isinstance(components, list)
            or len(components) > 64
            or any(not isinstance(item, dict) for item in components)
            or (cohort_ref is not None and not cls._valid_cohort_ref(cohort_ref))
        ):
            return None
        return {
            "identity": dict(identity),
            "source_window": dict(window),
            "coverage": dict(coverage),
            "completeness": completeness,
            "cohort_ref": cohort_ref,
            "components": [dict(item) for item in components],
        }

    @classmethod
    def _quantity_evidence(cls, value):
        if (
            not isinstance(value, dict)
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
        ):
            return None
        identity = value.get("identity")
        window = value.get("source_window")
        coverage = value.get("source_coverage")
        if (
            not cls._valid_identity(identity)
            or not cls._valid_window(window)
            or not isinstance(coverage, dict)
            or set(coverage) != {"postings_complete", "returns_complete", "unit_links_complete"}
            or any(type(item) is not bool for item in coverage.values())
            or (
                value.get("cohort_ref") is not None
                and not cls._valid_cohort_ref(value.get("cohort_ref"))
            )
            or value.get("status") not in {"COMPLETE", "PARTIAL", "UNKNOWN", "CONFLICT", "UNSUPPORTED"}
            or value.get("attribution") not in {"EXACT_COHORT", "EXACT_SKU", "WINDOW_ALLOCATION", "UNATTRIBUTED"}
        ):
            return None
        delivered = cls._count(value.get("delivered_units"))
        returned = cls._count(value.get("confirmed_returned_units_from_deliveries"))
        retained_raw = value.get("retained_units")
        retained = None if retained_raw is None else cls._count(retained_raw)
        if delivered is None or returned is None or (retained_raw is not None and retained is None):
            return None
        return {
            "identity": dict(identity),
            "source_window": dict(window),
            "source_coverage": dict(coverage),
            "cohort_ref": value["cohort_ref"],
            "status": value["status"],
            "attribution": value["attribution"],
            "delivered_units": delivered,
            "confirmed_returned_units_from_deliveries": returned,
            "retained_units": retained,
        }

    @classmethod
    def _summarize_fees(cls, snapshot, cohort_matches):
        groups = {kind: [] for kind in cls._FEE_KEYS}
        unmapped_count = 0
        for component in snapshot["components"]:
            key = component.get("component_key")
            kind = next((name for name, expected in cls._FEE_KEYS.items() if key == expected), None)
            if kind is not None:
                groups[kind].append(component)
            elif component.get("category") == cls._FEE_CATEGORY:
                unmapped_count += 1

        source_complete = (
            snapshot["coverage"]["complete"] is True
            and snapshot["completeness"] in {"COMPLETE", "CONFIRMED_ZERO"}
        )
        summaries = {}
        total_additional = Decimal("0.00")
        total_base_included = Decimal("0.00")
        total_account = Decimal("0.00")
        total_window = Decimal("0.00")
        account_component_count = 0
        window_component_count = 0
        complete = source_complete and unmapped_count == 0 and cohort_matches
        for kind, components in groups.items():
            summary = cls._summarize_fee_kind(components, cohort_matches)
            summaries[kind] = summary
            if summary["observed_additional_exact_cohort_rub"] is not None:
                total_additional += Decimal(summary["observed_additional_exact_cohort_rub"])
            if summary["base_included_exact_cohort_rub"] is not None:
                total_base_included += Decimal(summary["base_included_exact_cohort_rub"])
            if summary["account_level_rub"] is not None:
                total_account += Decimal(summary["account_level_rub"])
            if summary["window_allocated_rub"] is not None:
                total_window += Decimal(summary["window_allocated_rub"])
            account_component_count += summary["account_component_count"]
            window_component_count += summary["window_component_count"]
            complete = complete and summary["status"] == "COMPLETE"
        return {
            "status": "COMPLETE" if complete else (
                "CONFLICT" if any(item["status"] == "CONFLICT" for item in summaries.values())
                else "PARTIAL"
            ),
            "source_complete": source_complete,
            "cohort_matches": cohort_matches,
            "by_kind": summaries,
            "additional_exact_cohort_rub": cls._money(total_additional) if complete else None,
            "observed_additional_exact_cohort_rub": cls._money(total_additional),
            "base_included_exact_cohort_rub": cls._money(total_base_included),
            "account_level_rub": cls._money(total_account),
            "window_allocated_rub": cls._money(total_window),
            "account_component_count": account_component_count,
            "window_component_count": window_component_count,
            "unmapped_return_component_count": unmapped_count,
        }

    @classmethod
    def _summarize_fee_kind(cls, components, cohort_matches):
        if not components:
            return {
                "status": "MISSING", "additional_exact_cohort_rub": None,
                "observed_additional_exact_cohort_rub": None,
                "base_included_exact_cohort_rub": "0.00", "account_level_rub": "0.00",
                "window_allocated_rub": "0.00", "account_component_count": 0,
                "window_component_count": 0, "component_count": 0,
                "reasons": ["MISSING"],
            }
        additional = Decimal("0.00")
        base_included = Decimal("0.00")
        account = Decimal("0.00")
        window = Decimal("0.00")
        account_component_count = 0
        window_component_count = 0
        status = "COMPLETE"
        reasons = []
        for component in components:
            component_status = component.get("status")
            if component_status not in {"PRESENT", "CONFIRMED_ZERO"}:
                status = cls._merge_status(
                    status, "CONFLICT" if component_status == "CONFLICT" else "PARTIAL",
                )
                reasons.append(component_status or "UNKNOWN_STATUS")
                continue
            if component_status == "CONFIRMED_ZERO":
                if component.get("category") not in {None, cls._FEE_CATEGORY}:
                    status = cls._merge_status(status, "CONFLICT")
                    reasons.append("COMPONENT_CATEGORY_KEY_MISMATCH")
                continue
            if component.get("category") != cls._FEE_CATEGORY:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("COMPONENT_CATEGORY_KEY_MISMATCH")
                continue
            amount = cls._component_amount(component)
            if amount is None:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("AMOUNT_INVALID")
                continue
            ownership = component.get("ownership")
            attribution = component.get("attribution")
            origin = component.get("origin")
            if (
                ownership == "ADDITIONAL" and attribution == "EXACT_COHORT"
                and cohort_matches and origin in cls._EXACT_ORIGINS
            ):
                additional += amount
            elif ownership == "BASE_ALREADY_INCLUDED" and attribution == "EXACT_COHORT" and cohort_matches:
                base_included += amount
            elif ownership == "UNATTRIBUTED" or attribution == "UNATTRIBUTED":
                account += amount
                account_component_count += 1
                status = cls._merge_status(status, "INCOMPLETE")
                reasons.append("ACCOUNT_LEVEL_FEE_NOT_ALLOCATED")
            elif attribution == "WINDOW_ALLOCATION":
                window += amount
                window_component_count += 1
                status = cls._merge_status(status, "INCOMPLETE")
                reasons.append("WINDOW_FEE_NOT_EXACT_COHORT")
            else:
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("FEE_NOT_CONFIRMED_FOR_EXACT_COHORT")
        if additional < 0:
            reasons.append("NET_FEE_CREDIT_REQUIRES_REVIEW")
            status = cls._merge_status(status, "PARTIAL")
        return {
            "status": status,
            "additional_exact_cohort_rub": cls._money(additional) if status == "COMPLETE" else None,
            "observed_additional_exact_cohort_rub": cls._money(additional),
            "base_included_exact_cohort_rub": cls._money(base_included),
            "account_level_rub": cls._money(account),
            "window_allocated_rub": cls._money(window),
            "account_component_count": account_component_count,
            "window_component_count": window_component_count,
            "component_count": len(components),
            "reasons": sorted(set(reasons)),
        }

    @classmethod
    def _summarize_quantity(cls, quantity, cohort_matches):
        delivered = quantity["delivered_units"]
        returned = quantity["confirmed_returned_units_from_deliveries"]
        retained = delivered - returned
        complete = (
            quantity["status"] == "COMPLETE"
            and quantity["attribution"] == "EXACT_COHORT"
            and quantity["source_coverage"] == {
                "postings_complete": True, "returns_complete": True, "unit_links_complete": True,
            }
            and cohort_matches
        )
        status = "COMPLETE" if complete else (
            "CONFLICT" if quantity["status"] == "CONFLICT" or returned > delivered
            else "PARTIAL"
        )
        provided_retained = quantity["retained_units"]
        if returned > delivered or (provided_retained is not None and provided_retained != retained):
            status = "CONFLICT"
        elif retained <= 0 and complete:
            status = "INCOMPLETE"
        usable_retained = retained if status == "COMPLETE" else None
        return {
            "status": status,
            "delivered_units": delivered,
            "confirmed_returned_units_from_deliveries": returned,
            "retained_units": usable_retained,
            "observed_retained_units": retained if retained >= 0 else None,
            "denominator_kind": "RETAINED_UNITS_EXACT_COHORT",
            "cohort_matches": cohort_matches,
            "source_coverage": quantity["source_coverage"],
        }

    @classmethod
    def _summarize_inventory(
        cls, value, *, identity, cohort_ref, confirmed_returned_units,
        zero_return_sample_confirmed,
    ):
        if value is None and zero_return_sample_confirmed:
            return {
                "status": "CONFIRMED_ZERO", "inventory_loss_cogs_rub": "0.00",
                "observed_inventory_loss_cogs_rub": "0.00",
                "base_included_cogs_rub": "0.00", "observed_base_included_cogs_rub": "0.00",
                "confirmed_compensation_rub": "0.00", "observed_confirmed_compensation_rub": "0.00",
                "compensation_deduction_rub": "0.00", "observed_compensation_deduction_rub": "0.00",
                "disposition_units": 0,
                "pending_units": 0, "reasons": [],
            }
        if not isinstance(value, dict):
            return cls._inventory_unavailable("INVENTORY_DISPOSITION_UNAVAILABLE")
        coverage = value.get("source_coverage")
        rows = value.get("dispositions")
        if (
            type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or value.get("identity") != identity
            or not cls._valid_cohort_ref(cohort_ref)
            or value.get("cohort_ref") != cohort_ref
            or not cls._valid_window(value.get("source_window"))
            or value.get("status") not in {"COMPLETE", "PARTIAL", "UNKNOWN", "CONFLICT"}
            or not isinstance(coverage, dict)
            or set(coverage) != {"disposition_complete", "cogs_complete", "compensation_complete"}
            or any(type(item) is not bool for item in coverage.values())
            or not isinstance(rows, list)
            or len(rows) > cls._MAX_DISPOSITIONS
            or any(not isinstance(item, dict) for item in rows)
        ):
            return cls._inventory_unavailable("INVENTORY_EVIDENCE_INVALID")

        loss_cogs = Decimal("0.00")
        base_cogs = Decimal("0.00")
        compensation_total = Decimal("0.00")
        compensation_deduction = Decimal("0.00")
        units = 0
        pending_units = 0
        reasons = []
        status = (
            "CONFLICT" if value["status"] == "CONFLICT"
            else "COMPLETE" if value["status"] == "COMPLETE" and all(coverage.values())
            else "PARTIAL"
        )
        for row in rows:
            quantity = cls._count(row.get("quantity"))
            disposition = row.get("disposition")
            if quantity is None or quantity <= 0 or disposition not in cls._DISPOSITIONS:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("DISPOSITION_ROW_INVALID")
                continue
            units += quantity
            if disposition in {"PENDING", "UNKNOWN"}:
                pending_units += quantity
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("PENDING_OR_UNKNOWN_INVENTORY_DISPOSITION")
                continue
            cogs = cls._component_amount({"normalized_expense_rub": row.get("irrecoverable_cogs_rub")})
            compensation = cls._component_amount({"normalized_expense_rub": row.get("compensation_rub")})
            ownership = row.get("cogs_ownership")
            treatment = row.get("compensation_treatment")
            if (
                row.get("compensation_treatment") not in cls._COMPENSATION_TREATMENTS
                or cogs is None and disposition == "IRRECOVERABLE_CONFIRMED"
                or ownership not in {"ADDITIONAL", "BASE_ALREADY_INCLUDED"}
                and disposition == "IRRECOVERABLE_CONFIRMED"
            ):
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("COGS_OR_COMPENSATION_TREATMENT_UNCONFIRMED")
                continue
            if compensation is None and treatment == "NONE_CONFIRMED":
                compensation = Decimal("0.00")
            elif compensation is None and treatment != "UNKNOWN":
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("COMPENSATION_AMOUNT_UNAVAILABLE")
                continue
            if treatment == "UNKNOWN":
                status = cls._merge_status(status, "PARTIAL")
                reasons.append("COMPENSATION_TREATMENT_UNKNOWN")
                continue
            compensation = compensation or Decimal("0.00")
            if treatment == "NONE_CONFIRMED" and compensation != 0:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("NONE_CONFIRMED_COMPENSATION_HAS_AMOUNT")
                continue
            compensation_total += compensation
            if disposition == "SALEABLE_RESTORED":
                if cogs not in {None, Decimal("0.00")}:
                    status = cls._merge_status(status, "CONFLICT")
                    reasons.append("RESTORED_STOCK_CANNOT_BE_INVENTORY_LOSS")
                    continue
                if treatment == "NON_OVERLAPPING" and compensation != 0:
                    status = cls._merge_status(status, "PARTIAL")
                    reasons.append("COMPENSATION_WITHOUT_IRRECOVERABLE_COGS_REQUIRES_REVIEW")
                continue
            if cogs is None or cogs < 0 or compensation < 0:
                status = cls._merge_status(status, "CONFLICT")
                reasons.append("NEGATIVE_OR_MISSING_INVENTORY_AMOUNT")
                continue
            if ownership == "ADDITIONAL":
                loss_cogs += cogs
                if treatment == "NON_OVERLAPPING":
                    compensation_deduction += compensation
            else:
                base_cogs += cogs
                if treatment == "NON_OVERLAPPING" and compensation > 0:
                    status = cls._merge_status(status, "PARTIAL")
                    reasons.append("COMPENSATION_OWNERSHIP_MISMATCH_REQUIRES_REVIEW")
        if units != confirmed_returned_units:
            status = cls._merge_status(status, "CONFLICT")
            reasons.append("RETURNED_UNIT_DISPOSITION_QUANTITY_MISMATCH")
        if compensation_deduction > loss_cogs:
            reasons.append("NET_INVENTORY_CREDIT_REQUIRES_REVIEW")
            status = cls._merge_status(status, "PARTIAL")
        complete = status == "COMPLETE"
        return {
            "status": status,
            "inventory_loss_cogs_rub": cls._money(loss_cogs) if complete else None,
            "observed_inventory_loss_cogs_rub": cls._money(loss_cogs),
            "base_included_cogs_rub": cls._money(base_cogs) if complete else None,
            "observed_base_included_cogs_rub": cls._money(base_cogs),
            "confirmed_compensation_rub": cls._money(compensation_total) if complete else None,
            "observed_confirmed_compensation_rub": cls._money(compensation_total),
            "compensation_deduction_rub": cls._money(compensation_deduction) if complete else None,
            "observed_compensation_deduction_rub": cls._money(compensation_deduction),
            "disposition_units": units,
            "pending_units": pending_units,
            "reasons": sorted(set(reasons)),
        }

    @classmethod
    def _strict_loss(cls, fees, quantity, inventory):
        base = {
            "status": "UNAVAILABLE", "loss_pool_rub": None,
            "fee_loss_pool_rub": None, "inventory_loss_cogs_rub": inventory.get("inventory_loss_cogs_rub"),
            "compensation_deduction_rub": inventory.get("compensation_deduction_rub"),
            "loss_per_retained_unit_rub": None, "denominator_units": None,
            "denominator_kind": "RETAINED_UNITS_EXACT_COHORT",
            "model_scope": "STRICT_RETAINED_COHORT",
        }
        if fees["status"] != "COMPLETE":
            base["reason"] = "RETURN_FEE_EVIDENCE_INCOMPLETE"
            return base
        if quantity["status"] != "COMPLETE":
            base["reason"] = "EXACT_RETAINED_QUANTITY_UNAVAILABLE"
            return base
        if inventory["status"] not in {"COMPLETE", "CONFIRMED_ZERO"}:
            base["reason"] = "INVENTORY_DISPOSITION_OR_COGS_PENDING"
            return base
        fee_amount = Decimal(fees["additional_exact_cohort_rub"])
        inventory_cogs = Decimal(inventory["inventory_loss_cogs_rub"])
        compensation = Decimal(inventory["compensation_deduction_rub"])
        loss_pool = fee_amount + inventory_cogs - compensation
        if fee_amount < 0 or loss_pool < 0:
            base.update({
                "status": "REVIEW_REQUIRED",
                "fee_loss_pool_rub": cls._money(fee_amount),
                "loss_pool_rub": cls._money(loss_pool),
                "reason": "NET_RETURN_CREDIT_REQUIRES_REVIEW",
            })
            return base
        retained = quantity["retained_units"]
        if type(retained) is not int or retained <= 0:
            base["reason"] = "POSITIVE_RETAINED_DENOMINATOR_REQUIRED"
            return base
        unit_loss = (loss_pool / Decimal(retained)).quantize(
            cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP,
        )
        return {
            "status": "AVAILABLE",
            "loss_pool_rub": cls._money(loss_pool),
            "fee_loss_pool_rub": cls._money(fee_amount),
            "inventory_loss_cogs_rub": cls._money(inventory_cogs),
            "compensation_deduction_rub": cls._money(compensation),
            "loss_per_retained_unit_rub": cls._money(unit_loss),
            "denominator_units": retained,
            "denominator_kind": "RETAINED_UNITS_EXACT_COHORT",
            "model_scope": "STRICT_RETAINED_COHORT",
        }

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
        try:
            return amount.quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return None

    @classmethod
    def _valid_window(cls, value):
        keys = {"from_date", "to_date", "date_basis", "timezone"}
        if not isinstance(value, dict) or set(value) != keys:
            return False
        if not all(isinstance(value.get(key), str) and value[key] for key in keys):
            return False
        try:
            return date.fromisoformat(value["from_date"]) <= date.fromisoformat(value["to_date"])
        except ValueError:
            return False

    @staticmethod
    def _valid_identity(value):
        keys = {"owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema"}
        return (
            isinstance(value, dict) and set(value) == keys
            and all(isinstance(value.get(key), str) and value[key].strip() for key in keys)
            and value.get("sale_schema") in {"FBO", "FBS"}
        )

    @classmethod
    def _valid_cohort_ref(cls, value):
        return isinstance(value, str) and cls._COHORT_REF_RE.fullmatch(value) is not None

    @classmethod
    def _same_window(cls, first, second):
        return cls._valid_window(first) and cls._valid_window(second) and first == second

    @classmethod
    def _count(cls, value):
        if type(value) is not int or not 0 <= value <= cls._MAX_UNITS:
            return None
        return value

    @classmethod
    def _money(cls, value):
        amount = value.quantize(cls._MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        return format(abs(amount) if amount.is_zero() else amount, ".2f")

    @staticmethod
    def _merge_status(current, incoming):
        order = {"COMPLETE": 0, "CONFIRMED_ZERO": 0, "INCOMPLETE": 1, "PARTIAL": 2, "CONFLICT": 3}
        return incoming if order.get(incoming, 0) > order.get(current, 0) else current

    @staticmethod
    def _inventory_unavailable(reason):
        return {
            "status": "PARTIAL", "inventory_loss_cogs_rub": None,
            "observed_inventory_loss_cogs_rub": None,
            "base_included_cogs_rub": None, "confirmed_compensation_rub": None,
            "observed_base_included_cogs_rub": None,
            "observed_confirmed_compensation_rub": None,
            "compensation_deduction_rub": None, "observed_compensation_deduction_rub": None,
            "disposition_units": None,
            "pending_units": None, "reasons": [reason],
        }

    @staticmethod
    def _warnings(fees, quantity, inventory, strict_loss):
        warnings = []
        if fees["status"] != "COMPLETE":
            warnings.append("RETURN_FEES_INCOMPLETE_OR_NOT_EXACT_COHORT")
        if fees["account_component_count"]:
            warnings.append("ACCOUNT_LEVEL_RETURN_FEES_NOT_ALLOCATED")
        if fees["window_component_count"]:
            warnings.append("WINDOW_RETURN_FEES_NOT_EXACT_COHORT")
        if quantity["status"] != "COMPLETE":
            warnings.append("RETURNED_UNITS_NOT_LINKED_TO_EXACT_DELIVERED_COHORT")
        if inventory["status"] not in {"COMPLETE", "CONFIRMED_ZERO"}:
            warnings.append("PENDING_OR_UNKNOWN_COGS_IS_NOT_ZERO")
        if strict_loss["status"] != "AVAILABLE":
            warnings.append(strict_loss.get("reason", "STRICT_RETURN_LOSS_UNAVAILABLE"))
        return sorted(set(warnings))

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
