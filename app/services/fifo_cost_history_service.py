"""Read-only, conservative FIFO history projection for one exact seller SKU."""

from __future__ import annotations

from datetime import date

from services.fifo_cost_repository import FifoCostRepository


class FifoCostHistoryService:
    """Expose recorded layers/rates without presenting unreplayed stock as current."""

    _PROVENANCE_LABELS = {
        "OWNER_CONFIRMED": "подтверждено владельцем",
        "OZON_CONFIRMED_FIELD": "подтверждено полем Ozon",
        "DOCUMENT_RECONCILED": "сверено по документу",
        "LEGACY_DATED_COST": "взято из датированной истории",
    }
    _LOCATION_LABELS = {
        "HOME": "дома",
        "TRANSIT": "в пути",
        "OZON": "на Ozon",
        "UNKNOWN": "место не подтверждено",
    }

    def __init__(self, repository: FifoCostRepository | None = None):
        self.repository = repository or FifoCostRepository()

    def get_sku_history(
        self, *, store_id, product_id=None, offer_id=None, sku, as_of_date=None,
    ):
        snapshot = self.repository.read_cost_history_snapshot(
            store_id=store_id,
            product_id=product_id,
            offer_id=offer_id,
            sku=sku,
        )
        if not isinstance(snapshot, dict) or snapshot.get("error") is not False:
            return snapshot if isinstance(snapshot, dict) else {
                "error": True, "code": "FIFO_HISTORY_UNAVAILABLE",
            }
        try:
            as_of = date.fromisoformat(str(as_of_date)) if as_of_date is not None else date.today()
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_HISTORY_DATE_INVALID"}

        rates = []
        for row in snapshot["rates"]:
            effective_date = date.fromisoformat(row["effective_date"])
            rates.append({
                **row,
                "status": "EFFECTIVE" if effective_date <= as_of else "PLANNED",
                "provenance_label": self._provenance_label(row.get("provenance")),
            })
        effective_rates = [item for item in rates if item["status"] == "EFFECTIVE"]
        planned_rates = [item for item in rates if item["status"] == "PLANNED"]
        active_rate = effective_rates[-1] if effective_rates else None
        next_planned_rate = planned_rates[0] if planned_rates else None

        movements_need_replay = snapshot["movement_count"] > 0
        layers = []
        for row in snapshot["layers"]:
            layers.append({
                **row,
                "recorded_location_label": self._LOCATION_LABELS.get(
                    row.get("location"), "место не подтверждено",
                ),
                "provenance_label": self._provenance_label(row.get("provenance")),
                "remaining_units": None if movements_need_replay else row["recorded_quantity"],
                "remaining_status": (
                    "REPLAY_REQUIRED" if movements_need_replay else "AT_CONFIRMED_SNAPSHOT"
                ),
            })

        next_unit_cost = None
        next_unit_cost_basis = "UNAVAILABLE"
        if not movements_need_replay:
            first_finite_layer = next(
                (item for item in layers if item["remaining_units"] > 0),
                None,
            )
            if first_finite_layer is not None:
                next_unit_cost = first_finite_layer["unit_cost_rub"]
                next_unit_cost_basis = "FINITE_FIFO_LAYER"
            elif active_rate is not None:
                next_unit_cost = active_rate["unit_cost_rub"]
                next_unit_cost_basis = "OPEN_RATE_QUANTITY_UNKNOWN"

        return {
            "error": False,
            "code": snapshot["code"],
            "revision": snapshot["revision"],
            "as_of_date": as_of.isoformat(),
            "queue_initialized": snapshot["code"] == "FIFO_HISTORY_READY",
            "stream_state": snapshot["stream_state"],
            "cutoff_date": snapshot["cutoff_date"],
            "projection": snapshot["projection"],
            "layers": layers,
            "rates": rates,
            "active_rate": active_rate,
            "next_planned_rate": next_planned_rate,
            "next_unit_cost_rub": next_unit_cost,
            "next_unit_cost_basis": next_unit_cost_basis,
            "movement_count": snapshot["movement_count"],
            "remaining_status": (
                "REPLAY_REQUIRED" if movements_need_replay
                else "AT_CONFIRMED_SNAPSHOT"
            ),
            "latest_allocation": snapshot["latest_allocation"],
        }

    @classmethod
    def _provenance_label(cls, value):
        return cls._PROVENANCE_LABELS.get(value, "источник не подтверждён")
