from copy import deepcopy
from datetime import datetime, timezone


class ProductDecisionHistoryService:

    CODE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    def __init__(
        self,
        storage_service=None,
        clock=None,
        max_records_per_sku=50
    ):
        self.storage_service = storage_service
        self.clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        self.max_records_per_sku = max(1, int(max_records_per_sku))
        self.records = self._load_records()

    def record(self, decision):
        if not self._is_recordable(decision):
            return self._empty_context()

        sku = str(decision.get("sku"))
        previous = self.latest(sku)
        changed = previous is not None and self._signature(
            previous
        ) != self._signature(decision)

        if previous is None or changed:
            snapshot = self._snapshot(decision)
            self.records.append(snapshot)
            self._trim(sku)
            self._save_records()
            history_count = len(self.history(sku))
            return {
                "decision_history_available": True,
                "decision_changed": changed,
                "previous_decision_type": (
                    previous.get("decision_type") if previous else None
                ),
                "previous_priority": (
                    previous.get("priority") if previous else None
                ),
                "decision_recorded_at": snapshot["recorded_at"],
                "decision_history_count": history_count,
            }

        return {
            "decision_history_available": True,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": previous.get("recorded_at"),
            "decision_history_count": len(self.history(sku)),
        }

    def latest(self, sku):
        items = self.history(sku, limit=1)
        return items[0] if items else None

    def history(self, sku, limit=None):
        sku = str(sku)
        items = [
            deepcopy(item)
            for item in reversed(self.records)
            if str(item.get("sku")) == sku
        ]
        if limit is not None:
            items = items[:max(0, int(limit))]
        return items

    def _snapshot(self, decision):
        return {
            "sku": str(decision.get("sku")),
            "product_id": decision.get("product_id"),
            "decision_type": decision.get("decision_type"),
            "priority": decision.get("priority"),
            "confidence": decision.get("confidence"),
            "sales_velocity": decision.get("sales_velocity"),
            "days_of_stock": decision.get("days_of_stock"),
            "profit_per_unit": decision.get("decision_profit_per_unit"),
            "margin_percent": decision.get("decision_margin_percent"),
            "economics_basis": decision.get("economics_basis"),
            "recorded_at": str(self.clock()),
        }

    def _signature(self, decision):
        return (
            decision.get("decision_type"),
            decision.get("priority"),
        )

    def _is_recordable(self, decision):
        return (
            isinstance(decision, dict)
            and not decision.get("error")
            and decision.get("sku") is not None
            and decision.get("decision_type")
            not in {None, self.CODE_INSUFFICIENT_DATA}
            and decision.get("priority") is not None
        )

    def _trim(self, sku):
        matching_indexes = [
            index
            for index, item in enumerate(self.records)
            if str(item.get("sku")) == str(sku)
        ]
        excess = len(matching_indexes) - self.max_records_per_sku
        for index in reversed(matching_indexes[:max(0, excess)]):
            self.records.pop(index)

    def _load_records(self):
        if self.storage_service is None:
            return []
        records = self.storage_service.load()
        if not isinstance(records, list):
            return []
        return [dict(item) for item in records if isinstance(item, dict)]

    def _save_records(self):
        if self.storage_service is not None:
            self.storage_service.save(self.records)

    def _empty_context(self):
        return {
            "decision_history_available": False,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": None,
            "decision_history_count": 0,
        }
