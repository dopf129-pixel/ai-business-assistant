"""Resolve one SKU's next-unit cost without hiding an incomplete FIFO stream."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class FifoCurrentUnitCostAdapter:
    """Provide one shared current-cost view for unit economics and price plans.

    An uninitialized FIFO stream keeps the existing effective-dated seller cost.
    Once a FIFO stream exists, an incomplete stream stays unknown instead of
    falling back to a legacy row. FIFO values are planning evidence only; this
    adapter never makes them eligible for factual Period Profit COGS.
    """

    def __init__(self, legacy_cost_service, history_service):
        self.legacy_cost_service = legacy_cost_service
        self.history_service = history_service

    def get_current_cost_date(self):
        getter = getattr(self.legacy_cost_service, "get_current_cost_date", None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
            normalized = self._date(value)
            if normalized is not None:
                return normalized
        return date.today().isoformat()

    def get_cost(self, product_id):
        """Keep the legacy row-shaped interface for existing consumers."""
        getter = getattr(self.legacy_cost_service, "get_cost", None)
        return getter(product_id) if callable(getter) else None

    def get_all_costs(self):
        getter = getattr(self.legacy_cost_service, "get_all_costs", None)
        return getter() if callable(getter) else []

    def resolve_current_cost(
        self, product, *, store_id=None, as_of_date=None,
    ):
        identity = self._identity(product)
        if identity is None:
            return self._result(
                identity={}, as_of_date=as_of_date,
                method="UNAVAILABLE", completeness="IDENTITY_INCOMPLETE",
                reason_code="FIFO_COST_IDENTITY_INCOMPLETE",
            )
        current_date = self._date(as_of_date) or self.get_current_cost_date()
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        _owner, active_store = split_store_tenant_scope(tenant_scope)
        requested_store = str(store_id or active_store or "").strip()
        if active_store and requested_store != str(active_store):
            return self._result(
                identity=identity, store_id=requested_store,
                as_of_date=current_date, method="UNAVAILABLE",
                completeness="STORE_SCOPE_MISMATCH",
                reason_code="FIFO_COST_STORE_SCOPE_MISMATCH",
            )

        if not requested_store or not tenant_scope:
            # Legacy standalone callers may have no Ozon store context. Do not
            # guess a FIFO stream or bind a shared-store record in that case.
            return self._legacy_result(identity, current_date, reason="NO_STORE_SCOPE")

        try:
            history = self.history_service.get_sku_history(
                store_id=requested_store,
                product_id=identity["product_id"],
                offer_id=identity["offer_id"],
                sku=identity["sku"],
                as_of_date=current_date,
            )
        except Exception:
            history = None
        if not isinstance(history, dict) or history.get("error") is True:
            return self._result(
                identity=identity, store_id=requested_store,
                as_of_date=current_date, method="UNAVAILABLE",
                completeness="FIFO_HISTORY_UNAVAILABLE",
                reason_code=(
                    history.get("code") if isinstance(history, dict)
                    else "FIFO_HISTORY_RESPONSE_INVALID"
                ) or "FIFO_HISTORY_UNAVAILABLE",
            )

        if (
            history.get("code") == "FIFO_HISTORY_NOT_INITIALIZED"
            and history.get("revision") == 0
        ):
            return self._legacy_result(identity, current_date)

        return self._fifo_result(identity, requested_store, current_date, history)

    def _fifo_result(self, identity, store_id, current_date, history):
        movement_count = history.get("movement_count")
        try:
            movement_count = int(movement_count)
        except (TypeError, ValueError, OverflowError):
            movement_count = None
        cost = self._money(history.get("next_unit_cost_rub"))
        next_basis = history.get("next_unit_cost_basis")
        remaining_units = None
        effective_date = None
        if cost is not None and next_basis == "FINITE_FIFO_LAYER":
            next_layer = next(
                (
                    layer for layer in history.get("layers", ())
                    if isinstance(layer, dict)
                    and type(layer.get("remaining_units")) is int
                    and layer["remaining_units"] > 0
                ),
                None,
            )
            if next_layer is None or self._money(next_layer.get("unit_cost_rub")) != cost:
                cost = None
            else:
                remaining_units = next_layer["remaining_units"]
                effective_date = next_layer.get("effective_date")
        elif cost is not None and next_basis == "OPEN_RATE_QUANTITY_UNKNOWN":
            active_rate = history.get("active_rate")
            if not isinstance(active_rate, dict) or self._money(
                active_rate.get("unit_cost_rub")
            ) != cost:
                cost = None
            else:
                effective_date = active_rate.get("effective_date")
        else:
            cost = None

        if movement_count is None or movement_count > 0:
            cost = None
            remaining_units = None
            completeness = "REPLAY_REQUIRED"
            reason_code = "FIFO_COST_MOVEMENT_REPLAY_REQUIRED"
        elif cost is None:
            completeness = "FIFO_COST_BASIS_UNAVAILABLE"
            reason_code = "FIFO_NEXT_UNIT_COST_UNAVAILABLE"
        else:
            completeness = "CONFIRMED_SNAPSHOT_MODEL_ONLY"
            reason_code = None

        next_planned = history.get("next_planned_rate")
        if isinstance(next_planned, dict):
            next_planned = {
                "unit_cost_rub": next_planned.get("unit_cost_rub"),
                "effective_date": next_planned.get("effective_date"),
                "sequence": next_planned.get("sequence"),
            }
        else:
            next_planned = None

        material = {
            "mode": "FIFO",
            "store_id": store_id,
            **identity,
            "as_of_date": current_date,
            "stream_revision": history.get("revision"),
            "stream_state": history.get("stream_state"),
            "cutoff_date": history.get("cutoff_date"),
            "projection": history.get("projection"),
            "next_unit_cost_rub": cost,
            "next_unit_cost_basis": next_basis if cost is not None else None,
            "next_layer_remaining_units": remaining_units,
            "next_layer_effective_date": effective_date,
            "next_planned_rate": next_planned,
            "movement_count": movement_count,
            "remaining_status": history.get("remaining_status"),
            "completeness": completeness,
            "reason_code": reason_code,
            # A restored database can contain different FIFO history while
            # presenting the same next layer. Bind cache invalidation to the
            # sanitized history snapshot, not only its current projection.
            "history_snapshot": {
                "layers": history.get("layers", ()),
                "rates": history.get("rates", ()),
                "rate_reconciliations": history.get("rate_reconciliations", ()),
                "rate_cancellations": history.get("rate_cancellations", ()),
                "latest_allocation": history.get("latest_allocation"),
            },
        }
        revision = self._fingerprint(material)
        cost_method = (
            "FIFO_FINITE_LAYER" if next_basis == "FINITE_FIFO_LAYER"
            and cost is not None else
            "FIFO_OPEN_RATE" if next_basis == "OPEN_RATE_QUANTITY_UNKNOWN"
            and cost is not None else "FIFO_UNAVAILABLE"
        )
        return {
            "cost_per_unit_rub": cost,
            "cost_updated_at": effective_date,
            "cost_revision": revision,
            "cost_method": cost_method,
            "cost_basis": {
                "method": cost_method,
                "completeness": completeness,
                "reason_code": reason_code,
                "as_of_date": current_date,
                "cutoff_date": history.get("cutoff_date"),
                "stream_revision": history.get("revision"),
                "next_unit_cost_rub": cost,
                "next_unit_cost_basis": next_basis if cost is not None else None,
                "next_layer_remaining_units": remaining_units,
                "next_layer_effective_date": effective_date,
                "next_planned_rate": next_planned,
                "remaining_status": history.get("remaining_status"),
                "movement_count": movement_count,
                "model_only": True,
                "factual_period_profit_eligible": False,
                "cache_revision": revision,
            },
        }

    def _legacy_result(self, identity, current_date, *, reason=None):
        row = None
        if identity.get("product_id"):
            try:
                row = self.get_cost(identity["product_id"])
            except Exception:
                row = None
        amount, updated_at, currency = self._legacy_row(row, identity)
        if amount is None:
            completeness = "LEGACY_COST_UNAVAILABLE"
            reason_code = "LEGACY_EFFECTIVE_COST_UNAVAILABLE"
        else:
            completeness = "LEGACY_EFFECTIVE_COST_CONFIRMED"
            reason_code = None
        material = {
            "mode": "LEGACY",
            **identity,
            "as_of_date": current_date,
            "cost": amount,
            "effective_date": updated_at,
            "currency": currency,
            "reason": reason,
            "completeness": completeness,
        }
        revision = self._fingerprint(material)
        return {
            "cost_per_unit_rub": amount,
            "cost_updated_at": updated_at,
            "cost_revision": revision,
            "cost_method": "LEGACY_EFFECTIVE_DATED" if amount is not None else "LEGACY_UNAVAILABLE",
            "cost_basis": {
                "method": "LEGACY_EFFECTIVE_DATED" if amount is not None else "LEGACY_UNAVAILABLE",
                "completeness": completeness,
                "reason_code": reason_code,
                "as_of_date": current_date,
                "effective_date": updated_at,
                "next_unit_cost_rub": amount,
                "next_unit_cost_basis": "LEGACY_EFFECTIVE_COST" if amount is not None else None,
                "next_layer_remaining_units": None,
                "next_planned_rate": None,
                "remaining_status": "NOT_TRACKED",
                "model_only": True,
                "factual_period_profit_eligible": False,
                "cache_revision": revision,
            },
        }

    @staticmethod
    def _legacy_row(row, identity):
        if isinstance(row, dict):
            product_id = row.get("product_id")
            sku = row.get("sku")
            offer_id = row.get("offer_id")
            amount = row.get("cost_price")
            currency = row.get("currency") or "RUB"
            updated_at = row.get("effective_from") or row.get("updated_at")
        elif isinstance(row, (tuple, list)) and len(row) >= 5:
            product_id, sku, offer_id, amount, currency = row[:5]
            updated_at = row[5] if len(row) > 5 else None
        else:
            return None, None, None
        if str(product_id or "") != identity["product_id"]:
            return None, None, None
        if sku not in (None, "") and str(sku) != identity["sku"]:
            return None, None, None
        if offer_id not in (None, "") and str(offer_id) != identity["offer_id"]:
            return None, None, None
        parsed = FifoCurrentUnitCostAdapter._money(amount)
        currency = str(currency or "RUB").upper()
        if parsed is None or currency != "RUB":
            return None, None, currency
        return parsed, str(updated_at) if updated_at else None, currency

    @staticmethod
    def _identity(product):
        if not isinstance(product, dict):
            return None
        values = {
            key: str(product.get(key) or "").strip()
            for key in ("product_id", "offer_id", "sku")
        }
        if not all(values.values()):
            return None
        return values

    @staticmethod
    def _money(value):
        if isinstance(value, bool) or value in (None, ""):
            return None
        try:
            parsed = Decimal(str(value).strip().replace(" ", "").replace("\u00a0", ""))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not parsed.is_finite() or parsed < 0:
            return None
        return format(parsed.quantize(Decimal("0.01")), "f")

    @staticmethod
    def _date(value):
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fingerprint(material):
        encoded = json.dumps(
            material, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _result(
        self, *, identity, as_of_date, method, completeness, reason_code,
        store_id=None,
    ):
        material = {
            "method": method,
            "completeness": completeness,
            "reason_code": reason_code,
            "store_id": store_id,
            "identity": identity,
            "as_of_date": self._date(as_of_date),
        }
        revision = self._fingerprint(material)
        basis = {
            "method": method,
            "completeness": completeness,
            "reason_code": reason_code,
            "as_of_date": self._date(as_of_date),
            "next_unit_cost_rub": None,
            "next_unit_cost_basis": None,
            "next_layer_remaining_units": None,
            "next_planned_rate": None,
            "remaining_status": "UNKNOWN",
            "model_only": True,
            "factual_period_profit_eligible": False,
            "cache_revision": revision,
        }
        return {
            "cost_per_unit_rub": None,
            "cost_updated_at": None,
            "cost_revision": revision,
            "cost_method": method,
            "cost_basis": basis,
        }
