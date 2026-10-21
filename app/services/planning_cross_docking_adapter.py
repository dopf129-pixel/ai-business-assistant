"""Versioned, allowlisted cross-docking evidence for saved planning plans.

The durable representation intentionally excludes raw Ozon payloads and all
external supply, act, order, product, and SKU identifiers. SKU identity is
already stored separately as part of the saved plan's exact product identity.
"""

from decimal import Decimal, InvalidOperation
import re
from copy import deepcopy


class PlanningCrossDockingAdapter:
    LEGACY_VERSION = 1
    CURRENT_VERSION = 2
    METHODS = frozenset({
        "sku_accrual_cost_per_delivered_crossdock_unit",
        "store_accrual_cost_per_delivered_crossdock_unit",
    })
    DENOMINATOR_KIND = "DELIVERED_CROSSDOCK_UNITS"
    _SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,80}$")

    @classmethod
    def is_current(cls, payload):
        return cls._version(payload) == cls.CURRENT_VERSION

    @classmethod
    def supports(cls, payload, current_version):
        if not isinstance(payload, dict) or type(current_version) is not int:
            return False
        version = cls._version(payload)
        if current_version == cls.CURRENT_VERSION:
            return version in {cls.LEGACY_VERSION, cls.CURRENT_VERSION}
        return version == current_version

    @classmethod
    def items_for_sales_mix(cls, payload):
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return items
        if cls.is_current(payload):
            return items
        if cls._version(payload) != cls.LEGACY_VERSION:
            return items
        adapted = deepcopy(items)
        for item in adapted:
            if not isinstance(item, dict):
                continue
            inputs = item.get("inputs")
            if isinstance(inputs, dict):
                inputs.pop("cross_docking_per_unit", None)
            sources = item.get("sources")
            if isinstance(sources, dict):
                sources.pop("cross_docking", None)
                completeness = sources.get("completeness")
                if isinstance(completeness, dict):
                    completeness.pop("cross_docking", None)
        return adapted

    @classmethod
    def project_source(cls, evidence):
        """Project an in-memory provider result to safe, durable evidence."""
        evidence = evidence if isinstance(evidence, dict) else {}
        method = evidence.get("method")
        if method not in cls.METHODS:
            method = None
        denominator_kind = evidence.get("denominator_kind")
        if denominator_kind != cls.DENOMINATOR_KIND:
            denominator_kind = None
        window_complete = evidence.get("evidence_complete") is True
        applicable_to_sku = evidence.get("applicable_to_sku") is True
        amount_per_unit = cls._amount(evidence.get("cross_docking_per_unit"))
        rate_available = (
            window_complete
            and applicable_to_sku
            and method is not None
            and denominator_kind == cls.DENOMINATOR_KIND
            and amount_per_unit is not None
        )
        return {
            # This marks complete collection of the source window. A complete
            # window can still have no usable SKU rate (for example, no
            # cross-dock units); keep that state distinct from availability.
            "evidence_complete": window_complete,
            "rate_available": rate_available,
            "status": cls._code(evidence.get("status")),
            "reason": cls._code(evidence.get("reason")),
            "method": method,
            "amount_per_unit": amount_per_unit if rate_available else None,
            "applicable_to_sku": applicable_to_sku,
            "denominator_kind": denominator_kind,
            "expense_total": cls._amount(evidence.get("expense_total"), allow_negative=True),
            "expense_by_sku": cls._amount(evidence.get("expense_by_sku"), allow_negative=True),
            "supplied_units_sku": cls._count(evidence.get("supplied_units_sku")),
            "supplied_units_store": cls._count(evidence.get("supplied_units_store")),
            "days_complete": cls._count(evidence.get("days_complete")),
            "days_expected": cls._count(evidence.get("days_expected")),
            "date_from": cls._date(evidence.get("date_from")),
            "date_to": cls._date(evidence.get("date_to")),
            "as_of": cls._date(evidence.get("as_of")),
            "timezone": cls._label(evidence.get("timezone"), 40),
            "financial_date_basis": cls._label(evidence.get("financial_date_basis"), 48),
            "supply_date_basis": cls._label(evidence.get("supply_date_basis"), 64),
            "model_version": cls._count(evidence.get("model_version")),
        }

    @classmethod
    def restore_item(cls, payload, item):
        """Return inputs and evidence according to the saved calculation version.

        Version 1 deliberately discards any cross-docking key. Version 2 reads
        only the frozen allowlisted evidence stored with that exact revision.
        """
        version = cls._version(payload)
        inputs = dict(item.get("inputs") or {}) if isinstance(item, dict) else {}
        sources = item.get("sources") if isinstance(item, dict) else {}
        sources = sources if isinstance(sources, dict) else {}
        if version == cls.LEGACY_VERSION:
            inputs.pop("cross_docking_per_unit", None)
            return inputs, {}
        if version != cls.CURRENT_VERSION:
            return None, None
        evidence = sources.get("cross_docking")
        if not isinstance(evidence, dict):
            return None, None
        rate = cls._amount(inputs.get("cross_docking_per_unit"))
        if evidence.get("rate_available") is True:
            if (rate is None or rate != evidence.get("amount_per_unit")
                    or evidence.get("evidence_complete") is not True
                    or evidence.get("denominator_kind") != cls.DENOMINATOR_KIND
                    or evidence.get("applicable_to_sku") is not True):
                return None, None
        elif (rate is not None or evidence.get("amount_per_unit") is not None
              or evidence.get("applicable_to_sku") is True):
            return None, None
        return inputs, dict(evidence)

    @classmethod
    def _version(cls, payload):
        """Resolve the repository's implicit v1 default for old payloads."""
        if not isinstance(payload, dict):
            return None
        version = payload.get("calculation_version")
        schema = payload.get("schema_version")
        if version is None:
            if schema is None or (type(schema) is int and schema == cls.LEGACY_VERSION):
                return cls.LEGACY_VERSION
            return None
        if (type(version) is not int
                or (schema is not None and (type(schema) is not int or schema != version))):
            return None
        return version

    @classmethod
    def display_source(cls, evidence):
        """Expose only the harmless fields needed for plan screens/exports."""
        safe = cls.project_source(evidence)
        if isinstance(evidence, dict) and "amount_per_unit" in evidence:
            safe["amount_per_unit"] = cls._amount(evidence.get("amount_per_unit"))
        return safe

    @classmethod
    def completeness_projection(cls, safe_evidence):
        safe_evidence = safe_evidence if isinstance(safe_evidence, dict) else {}
        result = {
            "complete": safe_evidence.get("evidence_complete") is True,
            "rate_available": safe_evidence.get("rate_available") is True,
        }
        for key in ("status", "reason"):
            value = cls._code(safe_evidence.get(key))
            if value is not None:
                result[key] = value
        return result

    @classmethod
    def _amount(cls, value, *, allow_negative=False):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (not amount.is_finite() or (amount < 0 and not allow_negative)
                or amount.adjusted() > 12):
            return None
        return format(amount, "f")

    @classmethod
    def _count(cls, value):
        if type(value) is not int or value < 0 or value > 1_000_000:
            return None
        return value

    @classmethod
    def _date(cls, value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        value = value.strip()
        return value if value and all(char.isalnum() or char in "-:.+TZ" for char in value) else None

    @staticmethod
    def _label(value, limit):
        if not isinstance(value, str):
            return None
        value = " ".join(value.split())
        return value[:limit] if value else None

    @classmethod
    def _code(cls, value):
        return value if isinstance(value, str) and cls._SAFE_CODE.fullmatch(value) else None
