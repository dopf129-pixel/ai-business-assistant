"""Bounded, source-free sensitivity sweeps for unit-price scenarios."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


class UnitPriceSensitivityService:
    MAX_VALUES_PER_AXIS = 7
    MIN_VALUES_PER_AXIS = 3
    MAX_CELLS = 49
    MAX_RAW_TEXT_LENGTH = 512
    MAX_SOURCE_AGE_SECONDS = 600
    AXES = {
        "price": {
            "label": "Цена продавца",
            "unit": "RUB/unit",
            "max_digits": 15,
            "minimum": Decimal("0"),
            "exclusive_minimum": True,
            "maximum": None,
        },
        "cost": {
            "label": "Себестоимость",
            "unit": "RUB/unit",
            "max_digits": 15,
            "minimum": Decimal("0"),
            "exclusive_minimum": False,
            "maximum": None,
        },
        "advertising_rate": {
            "label": "Реклама",
            "unit": "percent",
            "max_digits": 28,
            "minimum": Decimal("0"),
            "exclusive_minimum": False,
            "maximum": Decimal("100"),
        },
    }

    def __init__(self, scenario_service):
        self.scenario_service = scenario_service

    def parse_axis_values(self, raw_text, axis):
        if axis not in self.AXES or not isinstance(raw_text, str):
            return self._error("SENSITIVITY_AXIS_OR_VALUES_INVALID")
        if len(raw_text) > self.MAX_RAW_TEXT_LENGTH:
            return self._error("SENSITIVITY_INPUT_TOO_LONG")
        tokens = re.split(r"[;\r\n]+", raw_text)
        tokens = [token.strip() for token in tokens]
        if any(not token for token in tokens):
            return self._error("SENSITIVITY_EMPTY_VALUE")
        if not self.MIN_VALUES_PER_AXIS <= len(tokens) <= self.MAX_VALUES_PER_AXIS:
            return self._error("SENSITIVITY_VALUE_COUNT_INVALID")
        parsed = []
        for token in tokens:
            value = self._parse_value(token, axis)
            if value is None:
                return self._error("SENSITIVITY_VALUE_INVALID")
            parsed.append(value)
        keys = [self._decimal_key(value) for value in parsed]
        if len(set(keys)) != len(keys):
            return self._error("SENSITIVITY_VALUES_NOT_UNIQUE")
        return {
            "error": False,
            "axis": axis,
            "values": [format(value, "f") for value in parsed],
            "read_only": True,
            "executed": False,
        }

    def build_sweep(self, context, axes, target_margin_percent=None):
        """Evaluate one or two absolute-value axes against a fixed snapshot."""
        normalized_axes = self._normalize_axes(axes)
        if not isinstance(normalized_axes, dict) or normalized_axes.get("error") is True:
            return normalized_axes
        source = self._normalize_context(context)
        if isinstance(source, dict) and source.get("error") is True:
            return source
        target = None
        if target_margin_percent is not None:
            target = self._parse_target(target_margin_percent)
            if target is None:
                return self._error("SENSITIVITY_TARGET_INVALID")

        base_inputs = deepcopy(source["inputs"])
        input_signature = self._signature({
            "identity": source["identity"],
            "version": source["source_version"],
            "inputs": base_inputs,
            "provenance": source["provenance"],
            "sources": source["sources"],
            "as_of": source["source_as_of"],
            "tariff_snapshot": source["frozen_tariff_resolution"],
            "legacy_tariff_price_cents": source["legacy_tariff_price_cents"],
        })
        axis_names = list(normalized_axes)
        cell_count = 1
        for values in normalized_axes.values():
            cell_count *= len(values)
        if cell_count > self.MAX_CELLS:
            return self._error("SENSITIVITY_CELL_LIMIT_EXCEEDED")

        fresh = (
            source["source_age_seconds"] < source["source_ttl_seconds"]
            and source["source_ttl_seconds"] <= self.MAX_SOURCE_AGE_SECONDS
        )
        cells = []
        if len(axis_names) == 1:
            combinations = [({axis_names[0]: value}, {axis_names[0]: index})
                            for index, value in enumerate(normalized_axes[axis_names[0]])]
        else:
            first_axis, second_axis = axis_names
            combinations = [
                (
                    {first_axis: first, second_axis: second},
                    {first_axis: first_index, second_axis: second_index},
                )
                for first_index, first in enumerate(normalized_axes[first_axis])
                for second_index, second in enumerate(normalized_axes[second_axis])
            ]

        for coordinates, coordinate_indexes in combinations:
            candidate_inputs = deepcopy(base_inputs)
            for axis, value in coordinates.items():
                candidate_inputs[axis] = format(value, "f")
            cell_identity = {
                **source["identity"],
                "sensitivity_input_signature": input_signature,
                "sensitivity_coordinates": {
                    key: format(value, "f") for key, value in coordinates.items()
                },
            }
            cell_signature = self._signature({
                "base": input_signature,
                "coordinates": cell_identity["sensitivity_coordinates"],
            })
            cell = {
                "cell_id": cell_signature[:20],
                "base_input_signature": input_signature,
                "coordinates": cell_identity["sensitivity_coordinates"],
                "coordinate_indexes": coordinate_indexes,
                "input_signature": cell_signature,
                "inputs": candidate_inputs,
                "provenance": deepcopy(source["provenance"]),
                "source_as_of": deepcopy(source["source_as_of"]),
                "status": "SOURCE_STALE" if not fresh else "INCOMPLETE_INPUTS",
                "tariff_resolution": None,
                "target_reached": None,
                "scenario": None,
            }
            if fresh:
                candidate_provenance = deepcopy(source["provenance"])
                for axis in coordinates:
                    candidate_provenance[axis] = "sensitivity_absolute_value"
                tariff_result = self._resolve_cell_tariff(source, candidate_inputs)
                if tariff_result is not None:
                    cell["tariff_resolution"] = {
                        key: tariff_result.get(key)
                        for key in ("available", "status", "reason", "commission_rate", "origin")
                    }
                    if tariff_result.get("available") is not True:
                        candidate_inputs["commission_rate"] = None
                        candidate_provenance["commission_rate"] = "unknown"
                        cell["inputs"] = deepcopy(candidate_inputs)
                        cell["provenance"] = deepcopy(candidate_provenance)
                        cell["status"] = (
                            "SOURCE_UNAVAILABLE"
                            if tariff_result.get("status") == "SOURCE_UNAVAILABLE"
                            else "COMMISSION_UNKNOWN"
                        )
                        cells.append(cell)
                        continue
                    candidate_inputs["commission_rate"] = tariff_result.get("commission_rate")
                    candidate_provenance["commission_rate"] = tariff_result.get("origin") or "unknown"
                    cell["inputs"] = deepcopy(candidate_inputs)
                cell["provenance"] = candidate_provenance
                scenario = self.scenario_service.calculate(
                    candidate_inputs,
                    identity=cell_identity,
                    provenance=candidate_provenance,
                    sources=source["sources"],
                )
                cell["scenario"] = scenario
                if scenario.get("available") is True:
                    cell["status"] = "AVAILABLE"
                    if target is not None:
                        cell["target_reached"] = self._reaches_target(
                            scenario, candidate_inputs, target
                        )
                elif scenario.get("invalid_inputs"):
                    cell["status"] = "INVALID_INPUTS"
                else:
                    cell["status"] = "INCOMPLETE_INPUTS"
            cells.append(cell)

        available = [
            cell for cell in cells
            if cell.get("status") == "AVAILABLE"
            and self._finite_decimal(
                (cell.get("scenario") or {}).get("calculated", {}).get("profit")
            ) is not None
        ]
        best = max(available, key=lambda cell: Decimal(str(cell["scenario"]["calculated"]["profit"])), default=None)
        worst = min(available, key=lambda cell: Decimal(str(cell["scenario"]["calculated"]["profit"])), default=None)
        return {
            "error": False,
            "kind": "UNIT_PRICE_SENSITIVITY",
            "schema_version": 1,
            "sensitivity_id": sha256((input_signature + "|" + self._signature(normalized_axes) + "|" + (format(target, "f") if target is not None else "unknown")).encode("utf-8")).hexdigest()[:20],
            "source_identity": deepcopy(source["identity"]),
            "source_version": source["source_version"],
            "source_as_of": deepcopy(source["source_as_of"]),
            "source_age_seconds": source["source_age_seconds"],
            "source_ttl_seconds": source["source_ttl_seconds"],
            "base_input_signature": input_signature,
            "tariff_scope": source["tariff_scope"],
            "axes": {
                axis: {
                    "label": self.AXES[axis]["label"],
                    "unit": self.AXES[axis]["unit"],
                    "values": [format(value, "f") for value in normalized_axes[axis]],
                }
                for axis in axis_names
            },
            "target_margin_percent": format(target, "f") if target is not None else None,
            "cell_count": len(cells),
            "available_cell_count": len(available),
            "cells": cells,
            "best_checked_cell_id": best.get("cell_id") if best else None,
            "worst_checked_cell_id": worst.get("cell_id") if worst else None,
            "best_worst_basis": "among_checked_scenarios_only",
            "read_only": True,
            "executed": False,
        }

    def context_signature(self, context):
        """Return the stable, source-bound signature used by sensitivity sweeps."""
        source = self._normalize_context(context)
        if source.get("error") is True:
            return source
        return self._signature({
            "identity": source["identity"],
            "version": source["source_version"],
            "inputs": source["inputs"],
            "provenance": source["provenance"],
            "sources": source["sources"],
            "as_of": source["source_as_of"],
            "tariff_snapshot": source["frozen_tariff_resolution"],
            "legacy_tariff_price_cents": source["legacy_tariff_price_cents"],
        })

    def _normalize_axes(self, axes):
        if not isinstance(axes, dict) or len(axes) not in (1, 2):
            return self._error("SENSITIVITY_AXES_INVALID")
        result = {}
        for axis, values in axes.items():
            if axis not in self.AXES or axis in result:
                return self._error("SENSITIVITY_AXES_INVALID")
            if not isinstance(values, (list, tuple)):
                return self._error("SENSITIVITY_VALUES_INVALID")
            if not self.MIN_VALUES_PER_AXIS <= len(values) <= self.MAX_VALUES_PER_AXIS:
                return self._error("SENSITIVITY_VALUE_COUNT_INVALID")
            parsed = []
            for raw in values:
                if isinstance(raw, bool):
                    return self._error("SENSITIVITY_VALUE_INVALID")
                value = self._parse_value(str(raw), axis)
                if value is None:
                    return self._error("SENSITIVITY_VALUE_INVALID")
                parsed.append(value)
            keys = [self._decimal_key(value) for value in parsed]
            if len(set(keys)) != len(keys):
                return self._error("SENSITIVITY_VALUES_NOT_UNIQUE")
            result[axis] = parsed
        return result

    def _normalize_context(self, context):
        if not isinstance(context, dict):
            return self._error("SENSITIVITY_CONTEXT_INVALID")
        snapshot = context.get("snapshot")
        identity = context.get("identity")
        inputs = context.get("inputs")
        provenance = context.get("provenance")
        sources = context.get("sources")
        if not all(isinstance(value, dict) for value in (snapshot, identity, inputs, provenance, sources)):
            return self._error("SENSITIVITY_CONTEXT_INVALID")
        snapshot_identity = snapshot.get("identity") or {}
        required = ("product_id", "offer_id", "sku", "tenant_scope")
        if any(
            not identity.get(field)
            or str(identity.get(field)) != str(snapshot_identity.get(field) or "")
            for field in required
        ):
            return self._error("SENSITIVITY_IDENTITY_MISMATCH")
        owner, store = self._scope_parts(identity.get("tenant_scope"))
        if not owner or not store or str(snapshot_identity.get("store_id") or "") != store:
            return self._error("SENSITIVITY_IDENTITY_MISMATCH")
        age = self._finite_decimal(context.get("source_age_seconds"))
        ttl = self._finite_decimal(context.get("source_ttl_seconds"))
        if (
            age is None
            or ttl is None
            or age < 0
            or ttl <= 0
            or age > Decimal("1000000000000")
            or ttl > Decimal("1000000000000")
        ):
            return self._error("SENSITIVITY_SOURCE_FRESHNESS_UNKNOWN")
        version = context.get("source_version")
        if isinstance(version, bool) or not isinstance(version, (int, str)) or not str(version):
            return self._error("SENSITIVITY_SOURCE_VERSION_UNKNOWN")
        tariff_snapshot = context.get("frozen_tariff_resolution")
        legacy_tariff_price_cents = context.get("legacy_tariff_price_cents")
        tariff_identity = {
            "owner_id": str(identity.get("owner_id") or identity.get("user_id") or ""),
            "store_id": str(identity.get("store_id") or ""),
            "product_id": str(identity.get("product_id") or ""),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
        }
        if tariff_snapshot is not None:
            tariff_snapshot = UnitPriceTariffSnapshotAdapter.validate(
                tariff_snapshot, tariff_identity, inputs,
            )
            if tariff_snapshot is None:
                return self._error("SENSITIVITY_TARIFF_SNAPSHOT_INVALID")
        if legacy_tariff_price_cents is not None and (
            type(legacy_tariff_price_cents) is not int or legacy_tariff_price_cents < 1
        ):
            return self._error("SENSITIVITY_TARIFF_SNAPSHOT_INVALID")
        tariff_scope = (
            "FROZEN_PROFILE_SET" if tariff_snapshot is not None
            else "EXACT_PRICE_ONLY" if legacy_tariff_price_cents is not None
            else "FIXED_RATE_ASSUMPTION"
        )
        return {
            "snapshot": deepcopy(snapshot),
            "identity": deepcopy(identity),
            "inputs": deepcopy(inputs),
            "provenance": deepcopy(provenance),
            "sources": deepcopy(sources),
            "source_age_seconds": float(age),
            "source_ttl_seconds": float(ttl),
            "source_version": str(version),
            "source_as_of": deepcopy(context.get("source_as_of") or {}),
            "frozen_tariff_resolution": deepcopy(tariff_snapshot),
            "legacy_tariff_price_cents": legacy_tariff_price_cents,
            "tariff_scope": tariff_scope,
        }

    def _resolve_cell_tariff(self, source, candidate_inputs):
        """Resolve each price-axis cell against the exact frozen evidence."""
        frozen = source.get("frozen_tariff_resolution")
        identity = source["identity"]
        tariff_identity = {
            "owner_id": str(identity.get("owner_id") or identity.get("user_id") or ""),
            "store_id": str(identity.get("store_id") or ""),
            "product_id": str(identity.get("product_id") or ""),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
        }
        candidate_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
            candidate_inputs.get("price")
        )
        if frozen is not None:
            if candidate_cents is None:
                return {"available": False, "status": "UNKNOWN", "reason": "SELLER_PRICE_INVALID"}
            resolution = UnitPriceTariffSnapshotAdapter.resolve_frozen(
                frozen, tariff_identity, candidate_cents,
            )
            if resolution.get("error") is True:
                return {"available": False, "status": "SOURCE_UNAVAILABLE", "reason": resolution.get("code")}
            profile = resolution.get("selected_profile") or {}
            origin = {
                "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
                "CURRENT_PRICE_POINT": "current_price_point",
                "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
            }.get(profile.get("origin"), "unknown")
            return {
                "available": resolution.get("available") is True,
                "status": resolution.get("status"),
                "reason": resolution.get("reason"),
                "commission_rate": resolution.get("commission_rate"),
                "origin": origin,
            }
        exact_cents = source.get("legacy_tariff_price_cents")
        base_cents = UnitPriceTariffSnapshotAdapter.price_to_cents(
            source["inputs"].get("price")
        )
        if exact_cents is not None:
            if candidate_cents == exact_cents == base_cents:
                return {
                    "available": True, "status": "LEGACY_EXACT_PRICE_ONLY",
                    "reason": None,
                    "commission_rate": source["inputs"].get("commission_rate"),
                    "origin": "legacy_frozen_plan_rate",
                }
            return {
                "available": False, "status": "UNKNOWN",
                "reason": "LEGACY_RATE_CONFIRMED_AT_SAVED_PRICE_ONLY",
            }
        # Old integrations that do not provide tariff evidence remain an
        # explicit fixed-rate what-if mode. A source/current/manual point is
        # not extrapolated to another price.
        origin = str(source["provenance"].get("commission_rate") or "unknown")
        point_origins = {
            "current_price_point", "ozon_current_fbo_rate", "manual",
            "manual_seller_assumption", "manual_unit_economics_input",
            "legacy_frozen_plan_rate",
        }
        if candidate_cents != base_cents and origin in point_origins:
            return {
                "available": False, "status": "UNKNOWN",
                "reason": "POINT_COMMISSION_NOT_EXTRAPOLATED",
            }
        return {
            "available": True, "status": "FIXED_RATE_ASSUMPTION",
            "reason": "NO_TARIFF_PROFILE_ATTACHED",
            "commission_rate": source["inputs"].get("commission_rate"),
            "origin": origin,
        }

    def _parse_value(self, raw, axis):
        spec = self.AXES[axis]
        text = str(raw if raw is not None else "").strip().replace("\u00a0", "").replace(" ", "")
        if not text or text.startswith("+") or ("," in text and "." in text):
            return None
        try:
            value = Decimal(text.replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not value.is_finite()
            or len(value.as_tuple().digits) > spec["max_digits"]
            or value.adjusted() > 12
            or value.adjusted() < -12
            or (value <= spec["minimum"] if spec["exclusive_minimum"] else value < spec["minimum"])
            or (spec["maximum"] is not None and value > spec["maximum"])
        ):
            return None
        return value

    @staticmethod
    def _parse_target(value):
        if isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value).strip().replace(",", ".").replace("%", ""))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not number.is_finite() or number < 0 or number > 100:
            return None
        return number

    @staticmethod
    def _finite_decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() else None

    @staticmethod
    def _reaches_target(scenario, inputs, target):
        try:
            profit = Decimal(str(scenario["calculated"]["profit"]))
            price = Decimal(str(inputs["price"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return None
        if not profit.is_finite() or not price.is_finite() or price <= 0:
            return None
        return profit * Decimal("100") >= target * price

    @staticmethod
    def _decimal_key(value):
        return format(value.normalize(), "f")

    @staticmethod
    def _signature(value):
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _scope_parts(scope):
        parts = str(scope or "").split("::")
        if len(parts) != 3 or parts[1] != "ozon":
            return None, None
        return parts[0], parts[2]

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "read_only": True,
            "executed": False,
        }
