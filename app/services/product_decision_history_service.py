from copy import deepcopy
from datetime import datetime, timezone


class ProductDecisionHistoryService:

    CODE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FEEDBACK_USEFUL = "USEFUL"
    FEEDBACK_NOT_RELEVANT = "NOT_RELEVANT"
    ALLOWED_FEEDBACK = {
        FEEDBACK_USEFUL,
        FEEDBACK_NOT_RELEVANT,
    }
    PROPOSAL_CONFIRMED = "CONFIRMED"
    PROPOSAL_DISMISSED = "DISMISSED"
    ALLOWED_PROPOSAL_STATUSES = {
        PROPOSAL_CONFIRMED,
        PROPOSAL_DISMISSED,
    }
    OUTCOME_PRIORITY_DECREASED = "PRIORITY_DECREASED"
    OUTCOME_PRIORITY_INCREASED = "PRIORITY_INCREASED"
    OUTCOME_DECISION_CHANGED = "DECISION_CHANGED"
    PRIORITY_RANK = {
        "NONE": 0,
        "LOW": 1,
        "NORMAL": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }

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
            snapshot = self._snapshot(decision, previous=previous)
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
                "previous_feedback": snapshot.get("source_feedback"),
                "decision_outcome": snapshot.get("outcome"),
            }

        return {
            "decision_history_available": True,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": previous.get("recorded_at"),
            "decision_history_count": len(self.history(sku)),
            "previous_feedback": None,
            "decision_outcome": None,
        }

    def latest(self, sku):
        items = self.history(sku, limit=1)
        return items[0] if items else None

    def record_feedback(self, sku, feedback):
        sku = str(sku or "").strip()
        feedback = str(feedback or "").strip().upper()

        if feedback not in self.ALLOWED_FEEDBACK:
            return {
                "error": True,
                "code": "INVALID_FEEDBACK",
                "sku": sku or None,
                "feedback": None,
                "saved": False,
            }

        index = self._latest_index(sku)
        if index is None:
            return {
                "error": True,
                "code": "DECISION_HISTORY_NOT_FOUND",
                "sku": sku or None,
                "feedback": None,
                "saved": False,
            }

        record = self.records[index]
        if record.get("feedback") == feedback:
            return {
                "error": False,
                "code": None,
                "sku": sku,
                "feedback": feedback,
                "saved": False,
            }

        record["feedback"] = feedback
        record["feedback_at"] = str(self.clock())
        self._save_records()
        return {
            "error": False,
            "code": None,
            "sku": sku,
            "feedback": feedback,
            "saved": True,
        }

    def record_proposal_status(self, sku, proposal_type, status):
        sku = str(sku or "").strip()
        proposal_type = str(proposal_type or "").strip().upper()
        status = str(status or "").strip().upper()

        if not proposal_type or status not in self.ALLOWED_PROPOSAL_STATUSES:
            return {
                "error": True,
                "code": "INVALID_PROPOSAL_STATUS",
                "sku": sku or None,
                "proposal_type": proposal_type or None,
                "proposal_status": None,
                "saved": False,
            }

        index = self._latest_index(sku)
        if index is None:
            return {
                "error": True,
                "code": "DECISION_HISTORY_NOT_FOUND",
                "sku": sku or None,
                "proposal_type": proposal_type,
                "proposal_status": None,
                "saved": False,
            }

        record = self.records[index]
        if (
            record.get("proposal_type") == proposal_type
            and record.get("proposal_status") == status
        ):
            return {
                "error": False,
                "code": None,
                "sku": sku,
                "proposal_type": proposal_type,
                "proposal_status": status,
                "saved": False,
            }

        record["proposal_type"] = proposal_type
        record["proposal_status"] = status
        record["proposal_status_at"] = str(self.clock())
        self._save_records()
        return {
            "error": False,
            "code": None,
            "sku": sku,
            "proposal_type": proposal_type,
            "proposal_status": status,
            "saved": True,
        }

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

    def learning_summary(self):
        records = [
            item for item in self.records if isinstance(item, dict)
        ]
        feedback_counts = {
            self.FEEDBACK_USEFUL: 0,
            self.FEEDBACK_NOT_RELEVANT: 0,
        }
        outcome_counts = {
            self.OUTCOME_PRIORITY_DECREASED: 0,
            self.OUTCOME_PRIORITY_INCREASED: 0,
            self.OUTCOME_DECISION_CHANGED: 0,
        }

        for record in records:
            feedback = record.get("feedback")
            if feedback in feedback_counts:
                feedback_counts[feedback] += 1
            outcome = record.get("outcome")
            if outcome in outcome_counts:
                outcome_counts[outcome] += 1

        return {
            "error": False,
            "products_count": len({
                str(record.get("sku"))
                for record in records
                if record.get("sku") is not None
            }),
            "decision_snapshots_count": len(records),
            "feedback_count": sum(feedback_counts.values()),
            "feedback_counts": feedback_counts,
            "outcome_count": sum(outcome_counts.values()),
            "outcome_counts": outcome_counts,
        }

    def _snapshot(self, decision, previous=None):
        recorded_at = str(self.clock())
        outcome = self._outcome(previous, decision)
        return {
            "sku": str(decision.get("sku")),
            "product_id": decision.get("product_id"),
            "decision_type": decision.get("decision_type"),
            "priority": decision.get("priority"),
            "confidence": decision.get("confidence"),
            "reasons": list(decision.get("reasons") or []),
            "sales_velocity": decision.get("sales_velocity"),
            "days_of_stock": decision.get("days_of_stock"),
            "profit_per_unit": decision.get("decision_profit_per_unit"),
            "margin_percent": decision.get("decision_margin_percent"),
            "economics_basis": decision.get("economics_basis"),
            "recorded_at": recorded_at,
            "feedback": None,
            "feedback_at": None,
            "proposal_type": None,
            "proposal_status": None,
            "proposal_status_at": None,
            "source_feedback": (
                previous.get("feedback") if previous else None
            ),
            "outcome": outcome,
            "outcome_recorded_at": recorded_at if outcome else None,
        }

    def _outcome(self, previous, current):
        if previous is None or not previous.get("feedback"):
            return None

        previous_rank = self.PRIORITY_RANK.get(
            str(previous.get("priority") or "NONE").upper()
        )
        current_rank = self.PRIORITY_RANK.get(
            str(current.get("priority") or "NONE").upper()
        )
        if previous_rank is None or current_rank is None:
            return self.OUTCOME_DECISION_CHANGED
        if current_rank < previous_rank:
            return self.OUTCOME_PRIORITY_DECREASED
        if current_rank > previous_rank:
            return self.OUTCOME_PRIORITY_INCREASED
        return self.OUTCOME_DECISION_CHANGED

    def _latest_index(self, sku):
        if not sku:
            return None
        for index in range(len(self.records) - 1, -1, -1):
            if str(self.records[index].get("sku")) == str(sku):
                return index
        return None

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
            "previous_feedback": None,
            "decision_outcome": None,
        }
