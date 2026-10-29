"""Safe, additive persistence adapter for extended unit-economics evidence."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class PlanningExtendedScenarioAdapter:
    """Keep only bounded, non-raw evidence needed to reopen an extended plan."""

    EXTENDED_FIELDS = frozenset({
        "schema_version", "calculation_mode", "expense_snapshot_ref",
        "quantity_evidence_ref", "expense_policy_revision", "included_component_keys",
        "excluded_component_statuses", "numerator_and_denominator_basis",
        "source_completeness", "assumed_inputs", "scope", "denominator_units",
        "components",
    })
    STRICT_IDENTITY_FIELDS = frozenset({
        "owner_id", "store_id", "product_id", "offer_id", "sku", "sale_schema",
    })
    _SAFE_REF = re.compile(r"^[a-f0-9]{64}$")
    _SAFE_POLICY = re.compile(r"^[a-zA-Z0-9._:-]{1,64}$")
    _COMPONENT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
    _ASSUMPTIONS = frozenset({
        "OWNER_PRICE", "OWNER_COST", "OWNER_TARIFF_OVERRIDE", "OWNER_ADVERTISING",
        "OWNER_DISCOUNT_POINTS",
    })
    _MONEY = re.compile(r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")
    _FORBIDDEN_KEYS = frozenset({
        "apikey", "clientid", "authorization", "token", "password", "secret",
        "headers", "rawjson", "rawresponse", "rawpayload", "cohortref",
        "returnid", "postingid", "supplyid", "actid",
    })
    MAX_BYTES = 16 * 1024

    @classmethod
    def observation_cost_basis(cls, value, strict_return_evidence=None, expected_identity=None):
        """Return a safe comparison identity for the frozen additional-cost basis.

        The signature covers calculation mode, numerator/denominator, dates,
        policy, source references and component amounts. It deliberately does
        not contain raw provider identifiers or responses.
        """
        if value is None:
            if strict_return_evidence is not None:
                return None
            return {
                "mode": "NOT_APPLIED", "origin": "NOT_APPLIED",
                "signature": None, "per_unit_rub": None,
            }
        contract = cls.project_extended(value)
        if contract is None:
            return None
        mode = contract["calculation_mode"]
        strict_projection = None
        if mode == "STRICT_RETAINED_COHORT":
            strict_projection = cls.project_strict_evidence(
                strict_return_evidence, expected_identity,
            )
            if strict_projection is None:
                return None
            per_unit = Decimal(strict_projection["strict_retained_cohort_loss"][
                "loss_per_retained_unit_rub"
            ])
        else:
            if strict_return_evidence is not None:
                return None
            numerator = sum((
                Decimal(item["numerator_rub"]) for item in contract["components"]
            ), Decimal("0"))
            per_unit = (numerator / Decimal(contract["denominator_units"])).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )

        assumed_inputs = contract["assumed_inputs"]
        if "OWNER_COST" in assumed_inputs:
            origin = "MANUAL_ASSUMPTION"
        elif (
            contract["source_completeness"] == "COMPLETE"
            and isinstance(contract["expense_snapshot_ref"], str)
            and (mode != "STRICT_RETAINED_COHORT"
                 or isinstance(contract["quantity_evidence_ref"], str))
        ):
            origin = "CONFIRMED"
        else:
            origin = "UNCONFIRMED"

        # Canonicalize equivalent decimal spellings before hashing.
        material_contract = deepcopy(contract)
        material_contract["components"] = [
            {**item, "numerator_rub": format(Decimal(item["numerator_rub"]), ".2f")}
            for item in contract["components"]
        ]
        material = {
            "contract": material_contract,
            "strict_return_evidence": strict_projection,
        }
        try:
            encoded = json.dumps(
                material, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            return None
        if len(encoded) > cls.MAX_BYTES * 2:
            return None
        from hashlib import sha256
        return {
            "mode": mode, "origin": origin,
            "signature": sha256(encoded).hexdigest(),
            "per_unit_rub": format(per_unit, ".2f"),
        }

    @classmethod
    def project_extended(cls, value):
        if not isinstance(value, dict) or set(value) != cls.EXTENDED_FIELDS:
            return None
        if (type(value.get("schema_version")) is not int
                or value["schema_version"] != 1
                or value.get("calculation_mode") not in {
                    "WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT",
                }
                or value.get("source_completeness") not in {
                    "COMPLETE", "PARTIAL", "UNKNOWN", "CONFLICT",
                }
                or not isinstance(value.get("expense_policy_revision"), str)
                or cls._SAFE_POLICY.fullmatch(value["expense_policy_revision"]) is None
                or type(value.get("denominator_units")) is not int
                or not 1 <= value["denominator_units"] <= 1_000_000_000):
            return None
        mode = value["calculation_mode"]
        basis = value.get("numerator_and_denominator_basis")
        allowed_basis = (
            {"numerator": "WINDOW_EXPENSE_RUB", "denominator": "ORDERED_UNITS_WINDOW"},
            {"numerator": "WINDOW_EXPENSE_RUB", "denominator": "SOLD_UNITS_WINDOW"},
            {"numerator": "STRICT_COHORT_LOSS_RUB", "denominator": "RETAINED_UNITS_EXACT_COHORT"},
        )
        if (not isinstance(basis, dict) or set(basis) != {"numerator", "denominator"}
                or basis not in allowed_basis
                or (mode == "WINDOW_COST_ALLOCATION" and basis["numerator"] != "WINDOW_EXPENSE_RUB")
                or (mode == "STRICT_RETAINED_COHORT"
                    and (basis["numerator"] != "STRICT_COHORT_LOSS_RUB"
                         or basis["denominator"] != "RETAINED_UNITS_EXACT_COHORT"))):
            return None
        for field in ("expense_snapshot_ref", "quantity_evidence_ref"):
            reference = value.get(field)
            if reference is not None and (
                not isinstance(reference, str) or cls._SAFE_REF.fullmatch(reference) is None
            ):
                return None
        if value["calculation_mode"] == "STRICT_RETAINED_COHORT" and any(
            value.get(field) is None
            for field in ("expense_snapshot_ref", "quantity_evidence_ref")
        ):
            return None
        assumptions = value.get("assumed_inputs")
        components = value.get("components")
        included = value.get("included_component_keys")
        excluded = value.get("excluded_component_statuses")
        if (not isinstance(assumptions, list) or len(assumptions) > 16
                or any(not isinstance(item, str) or item not in cls._ASSUMPTIONS
                       for item in assumptions)
                or len(assumptions) != len(set(assumptions))
                or not isinstance(components, list) or len(components) > 64
                or not isinstance(included, list) or len(included) > 64
                or any(not isinstance(key, str) or cls._COMPONENT_KEY.fullmatch(key) is None
                       for key in included)
                or included != sorted(set(included))
                or not isinstance(excluded, dict) or len(excluded) > 64):
            return None
        component_keys = []
        total = Decimal("0")
        for component in components:
            if (not isinstance(component, dict)
                    or set(component) != {"component_key", "numerator_rub", "ownership"}
                    or component.get("ownership") != "ADDITIONAL"):
                return None
            key = component.get("component_key")
            raw_amount = component.get("numerator_rub")
            if (not isinstance(key, str) or cls._COMPONENT_KEY.fullmatch(key) is None
                    or key in component_keys or not isinstance(raw_amount, str)
                    or len(raw_amount) > 32):
                return None
            try:
                amount = Decimal(raw_amount)
            except (InvalidOperation, ValueError):
                return None
            if (not amount.is_finite() or amount < 0
                    or amount > Decimal("999999999999.99")):
                return None
            total += amount
            if total > Decimal("999999999999.99"):
                return None
            component_keys.append(key)
        if component_keys != included:
            return None
        if any(not isinstance(key, str) or cls._COMPONENT_KEY.fullmatch(key) is None
               or not isinstance(status, str) or status not in {"EXCLUDED", "UNKNOWN"}
               or key in component_keys
               for key, status in excluded.items()):
            return None
        if mode == "STRICT_RETAINED_COHORT" and component_keys:
            return None
        scope = value.get("scope")
        if (not isinstance(scope, dict)
                or set(scope) != {"scope_kind", "from_date", "to_date", "date_basis", "timezone"}
                or scope.get("scope_kind") not in {
                    "REFERENCE_56_COMPLETED_LOCAL_DAYS", "EXPERIMENT_PHASE_WINDOW",
                }
                or scope.get("date_basis") != "LOCAL_CALENDAR_DAY"
                or not isinstance(scope.get("timezone"), str)
                or not 1 <= len(scope["timezone"]) <= 128):
            return None
        try:
            ZoneInfo(scope["timezone"])
            start = date.fromisoformat(scope["from_date"])
            end = date.fromisoformat(scope["to_date"])
        except (TypeError, ValueError, ZoneInfoNotFoundError, OSError):
            return None
        days = (end - start).days + 1
        if (start > end
                or (scope["scope_kind"] == "REFERENCE_56_COMPLETED_LOCAL_DAYS" and days != 56)
                or (scope["scope_kind"] == "EXPERIMENT_PHASE_WINDOW" and not 1 <= days <= 28)):
            return None
        if mode == "STRICT_RETAINED_COHORT" and scope["scope_kind"] != "EXPERIMENT_PHASE_WINDOW":
            return None
        if not cls._bounded_json(value):
            return None
        return deepcopy(value)

    @classmethod
    def project_strict_evidence(cls, value, expected_identity):
        """Strip resolver-only fields/IDs while retaining canonical proof inputs."""
        if not isinstance(value, dict) or value.get("error") is not False:
            return None
        identity = value.get("identity")
        if (not isinstance(identity, dict)
                or set(identity) != cls.STRICT_IDENTITY_FIELDS
                or not isinstance(expected_identity, dict)
                or any(identity.get(key) != expected_identity.get(key)
                       for key in cls.STRICT_IDENTITY_FIELDS)):
            return None
        if (any(not isinstance(item, str) or not item.strip()
                for item in identity.values())
                or identity.get("sale_schema") not in {"FBO", "FBS"}):
            return None
        fees = value.get("fees")
        quantity = value.get("quantity")
        inventory = value.get("inventory")
        loss = value.get("strict_retained_cohort_loss")
        if (not isinstance(fees, dict) or not isinstance(quantity, dict)
                or not isinstance(inventory, dict) or not isinstance(loss, dict)):
            return None
        projected = {
            "error": False,
            "status": value.get("status"),
            "identity": {key: identity[key] for key in sorted(identity)},
            "fees": {
                key: fees.get(key)
                for key in ("status", "cohort_matches", "additional_exact_cohort_rub")
            },
            "quantity": {
                key: quantity.get(key)
                for key in (
                    "status", "cohort_matches", "delivered_units",
                    "confirmed_returned_units_from_deliveries", "retained_units",
                )
            },
            "inventory": {
                key: inventory.get(key)
                for key in (
                    "status", "disposition_units", "inventory_loss_cogs_rub",
                    "compensation_deduction_rub",
                )
            },
            "strict_retained_cohort_loss": {
                key: loss.get(key)
                for key in (
                    "status", "model_scope", "denominator_kind", "denominator_units",
                    "fee_loss_pool_rub", "loss_pool_rub", "loss_per_retained_unit_rub",
                )
            },
            "read_only": True,
            "executed": False,
        }
        if not cls._valid_strict_projection(projected) or not cls._bounded_json(projected):
            return None
        return projected

    @classmethod
    def _valid_strict_projection(cls, value):
        fees, quantity = value["fees"], value["quantity"]
        inventory, loss = value["inventory"], value["strict_retained_cohort_loss"]
        if (value.get("status") != "COMPLETE"
                or fees.get("status") != "COMPLETE" or fees.get("cohort_matches") is not True
                or quantity.get("status") != "COMPLETE" or quantity.get("cohort_matches") is not True
                or inventory.get("status") not in {"COMPLETE", "CONFIRMED_ZERO"}
                or loss.get("status") != "AVAILABLE"
                or loss.get("model_scope") != "STRICT_RETAINED_COHORT"
                or loss.get("denominator_kind") != "RETAINED_UNITS_EXACT_COHORT"):
            return False
        delivered = quantity.get("delivered_units")
        returned = quantity.get("confirmed_returned_units_from_deliveries")
        retained = quantity.get("retained_units")
        denominator = loss.get("denominator_units")
        if (type(delivered) is not int or delivered <= 0
                or type(returned) is not int or not 0 <= returned <= delivered
                or type(retained) is not int or retained <= 0
                or retained != delivered - returned or type(denominator) is not int
                or denominator != retained
                or type(inventory.get("disposition_units")) is not int
                or inventory["disposition_units"] != returned):
            return False
        money_keys = {
            "additional_exact_cohort_rub": fees.get("additional_exact_cohort_rub"),
            "inventory_loss_cogs_rub": inventory.get("inventory_loss_cogs_rub"),
            "compensation_deduction_rub": inventory.get("compensation_deduction_rub"),
            "fee_loss_pool_rub": loss.get("fee_loss_pool_rub"),
            "loss_pool_rub": loss.get("loss_pool_rub"),
            "loss_per_retained_unit_rub": loss.get("loss_per_retained_unit_rub"),
        }
        amounts = {}
        for key, raw in money_keys.items():
            if not isinstance(raw, str) or cls._MONEY.fullmatch(raw) is None:
                return False
            try:
                amounts[key] = Decimal(raw)
            except (InvalidOperation, ValueError):
                return False
        if (amounts["compensation_deduction_rub"] > amounts["inventory_loss_cogs_rub"]
                or amounts["loss_pool_rub"] < 0):
            return False
        return (
            amounts["additional_exact_cohort_rub"] == amounts["fee_loss_pool_rub"]
            and amounts["loss_pool_rub"] == (
                amounts["fee_loss_pool_rub"] + amounts["inventory_loss_cogs_rub"]
                - amounts["compensation_deduction_rub"]
            )
            and amounts["loss_per_retained_unit_rub"]
            == (amounts["loss_pool_rub"] / Decimal(retained)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            )
        )

    @classmethod
    def _bounded_json(cls, value):
        def safe(item, depth=0):
            if depth > 8:
                return False
            if item is None or type(item) in {bool, int}:
                return True
            if isinstance(item, str):
                return len(item) <= 2048
            if isinstance(item, list):
                return len(item) <= 64 and all(safe(child, depth + 1) for child in item)
            if isinstance(item, dict):
                return len(item) <= 64 and all(
                    isinstance(key, str)
                    and len(key) <= 80
                    and key.casefold().replace("_", "") not in cls._FORBIDDEN_KEYS
                    and safe(child, depth + 1)
                    for key, child in item.items()
                )
            return False

        if not safe(value):
            return False
        try:
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= cls.MAX_BYTES
        except (TypeError, ValueError, UnicodeError):
            return False
