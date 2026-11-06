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

    def __init__(self, repository: FifoCostRepository | None = None, *, date_provider=None):
        self.repository = repository or FifoCostRepository()
        self.date_provider = date_provider or date.today

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
            as_of_value = as_of_date if as_of_date is not None else self.date_provider()
            as_of = (
                as_of_value if isinstance(as_of_value, date)
                else date.fromisoformat(str(as_of_value))
            )
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_HISTORY_DATE_INVALID"}

        reconciliations_by_rate = {
            row["reconciled_rate_sequence"]: row
            for row in snapshot.get("rate_reconciliations", ())
        }
        rates = []
        for row in snapshot["rates"]:
            effective_date = date.fromisoformat(row["effective_date"])
            reconciliation = reconciliations_by_rate.get(row["sequence"])
            rates.append({
                **row,
                "status": (
                    "CANCELLED" if row.get("cancelled") is True else
                    "EFFECTIVE" if effective_date <= as_of else "PLANNED"
                ),
                "provenance_label": self._provenance_label(row.get("provenance")),
                "reconciled_quantity": (
                    reconciliation["prior_rate_units"] if reconciliation else None
                ),
                "reconciled_total_units": (
                    reconciliation["reconciled_total_units"] if reconciliation else None
                ),
            })
        rate_reconciliations = list(snapshot.get("rate_reconciliations", ()))
        effective_rates = [item for item in rates if item["status"] == "EFFECTIVE"]
        planned_rates = [item for item in rates if item["status"] == "PLANNED"]
        active_rate = effective_rates[-1] if effective_rates else None
        next_planned_rate = planned_rates[0] if planned_rates else None

        replayed_layers = self._current_replayed_layers(snapshot)
        movements_need_replay = (
            snapshot["movement_count"] > 0 and replayed_layers is None
        )
        layers = []
        for row in snapshot["layers"]:
            replayed = (
                replayed_layers.get(row["sequence"])
                if replayed_layers is not None else None
            )
            remaining_units = (
                replayed["remaining_units"] if replayed is not None else
                None if movements_need_replay else row["recorded_quantity"]
            )
            layers.append({
                **row,
                "recorded_location_label": self._LOCATION_LABELS.get(
                    row.get("location"), "место не подтверждено",
                ),
                "provenance_label": self._provenance_label(row.get("provenance")),
                "remaining_units": remaining_units,
                "remaining_status": (
                    "REPLAY_REQUIRED" if movements_need_replay else
                    "AFTER_CONFIRMED_REPLAY" if replayed_layers is not None else
                    "AT_CONFIRMED_SNAPSHOT"
                ),
            })

        rate_by_sequence = {row["sequence"]: row for row in rates}
        reconciled_rate_layers = []
        for reconciliation in rate_reconciliations:
            sequence = reconciliation.get("reconciled_rate_sequence")
            rate = rate_by_sequence.get(sequence)
            transition = rate_by_sequence.get(
                reconciliation.get("transition_rate_sequence"),
            )
            quantity = reconciliation.get("prior_rate_units")
            if (
                not isinstance(rate, dict) or not isinstance(transition, dict)
                or rate.get("status") != "EFFECTIVE"
                or rate.get("cancelled") is True
                or transition.get("status") != "EFFECTIVE"
                or type(quantity) is not int or quantity <= 0
            ):
                continue
            reconciled_rate_layers.append({
                "sequence": sequence,
                "recorded_quantity": quantity,
                "remaining_units": quantity,
                "unit_cost_rub": rate["unit_cost_rub"],
                "effective_date": rate["effective_date"],
                "provenance": rate.get("provenance"),
                "provenance_label": rate.get("provenance_label"),
                "kind": "RECONCILED_RATE",
            })

        next_unit_cost = None
        next_unit_cost_basis = "UNAVAILABLE"
        if not movements_need_replay:
            first_finite_layer = next(
                (item for item in layers if item["remaining_units"] > 0), None,
            ) or next(
                (item for item in reconciled_rate_layers
                 if item["remaining_units"] > 0), None,
            )
            if first_finite_layer is not None:
                next_unit_cost = first_finite_layer["unit_cost_rub"]
                next_unit_cost_basis = (
                    "RECONCILED_RATE_LAYER"
                    if first_finite_layer.get("kind") == "RECONCILED_RATE"
                    else "FINITE_FIFO_LAYER"
                )
            elif active_rate is not None:
                next_unit_cost = active_rate["unit_cost_rub"]
                next_unit_cost_basis = "OPEN_RATE_QUANTITY_UNKNOWN"
        elif replayed_layers is not None:
            first_finite_layer = next(
                (item for item in layers if item["remaining_units"] > 0), None,
            )
            if first_finite_layer is not None:
                next_unit_cost = first_finite_layer["unit_cost_rub"]
                next_unit_cost_basis = "FINITE_FIFO_LAYER"

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
            "reconciled_rate_layers": reconciled_rate_layers,
            "rates": rates,
            "rate_reconciliations": rate_reconciliations,
            "rate_cancellations": list(snapshot.get("rate_cancellations", ())),
            "active_rate": active_rate,
            "next_planned_rate": next_planned_rate,
            "next_unit_cost_rub": next_unit_cost,
            "next_unit_cost_basis": next_unit_cost_basis,
            "movement_count": snapshot["movement_count"],
            "remaining_status": (
                "REPLAY_REQUIRED" if movements_need_replay else
                "AFTER_CONFIRMED_REPLAY" if replayed_layers is not None else
                "AT_CONFIRMED_SNAPSHOT"
            ),
            "latest_allocation": snapshot["latest_allocation"],
        }

    @staticmethod
    def _current_replayed_layers(snapshot):
        if snapshot.get("movement_count", 0) <= 0:
            return None
        allocation = snapshot.get("latest_allocation")
        if (
            not isinstance(allocation, dict)
            or allocation.get("status") != "COMPLETE"
            or allocation.get("cutoff_status") != "RECONCILED"
            or allocation.get("stale") is not False
            or allocation.get("stream_revision") != snapshot.get("revision")
        ):
            return None
        rows = allocation.get("replayed_remaining_layers")
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or type(row.get("sequence")) is not int
            or type(row.get("remaining_units")) is not int
            or row["remaining_units"] < 0
            for row in rows
        ):
            return None
        return {row["sequence"]: row for row in rows}

    @classmethod
    def _provenance_label(cls, value):
        return cls._PROVENANCE_LABELS.get(value, "источник не подтверждён")
