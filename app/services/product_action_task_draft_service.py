from copy import deepcopy
from datetime import datetime, timezone


class ProductActionTaskDraftService:

    STATUS_DRAFT = "DRAFT"
    STATUS_DISMISSED = "DISMISSED"

    def __init__(self, storage_service=None, clock=None):
        self.storage_service = storage_service
        self.clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        self.records = self._load_records()

    def create_from_confirmation(self, decision, proposal):
        decision = dict(decision or {})
        proposal = dict(proposal or {})
        sku = str(decision.get("sku") or "").strip()
        proposal_type = str(
            proposal.get("proposal_type") or ""
        ).strip().upper()
        recorded_at = str(decision.get("recorded_at") or "").strip()

        if (
            not sku
            or not proposal_type
            or not recorded_at
            or not proposal.get("action_required")
        ):
            return self._error("INVALID_TASK_DRAFT_SOURCE", sku)

        draft_key = self._draft_key(sku, proposal_type, recorded_at)
        index = self._index_by_key(draft_key)
        if index is not None and self.records[index].get("status") == (
            self.STATUS_DRAFT
        ):
            return self._result(self.records[index], saved=False)

        now = str(self.clock())
        record = {
            "draft_key": draft_key,
            "sku": sku,
            "proposal_type": proposal_type,
            "status": self.STATUS_DRAFT,
            "decision_type": decision.get("decision_type"),
            "priority": decision.get("priority"),
            "decision_recorded_at": recorded_at,
            "profit_per_unit": decision.get("profit_per_unit"),
            "margin_percent": decision.get("margin_percent"),
            "created_at": (
                self.records[index].get("created_at")
                if index is not None
                else now
            ),
            "updated_at": now,
            "execution_allowed": False,
            "executed": False,
        }
        if index is None:
            self.records.append(record)
        else:
            self.records[index] = record
        self._save_records()
        return self._result(record, saved=True)

    def dismiss(self, sku, proposal_type, decision_recorded_at):
        key = self._draft_key(
            str(sku or "").strip(),
            str(proposal_type or "").strip().upper(),
            str(decision_recorded_at or "").strip(),
        )
        index = self._index_by_key(key)
        if index is None:
            return {
                "error": False,
                "code": None,
                "task_draft": None,
                "saved": False,
                "executed": False,
                "execution_allowed": False,
            }
        record = self.records[index]
        if record.get("status") == self.STATUS_DISMISSED:
            return self._result(record, saved=False)
        record["status"] = self.STATUS_DISMISSED
        record["updated_at"] = str(self.clock())
        self._save_records()
        return self._result(record, saved=True)

    def latest_for_sku(self, sku):
        sku = str(sku or "").strip()
        for record in reversed(self.records):
            if str(record.get("sku")) == sku:
                return deepcopy(record)
        return None

    def list_drafts(self, status=None, limit=None):
        items = [deepcopy(item) for item in reversed(self.records)]
        if status is not None:
            normalized = str(status).upper()
            items = [
                item for item in items
                if item.get("status") == normalized
            ]
        if limit is not None:
            items = items[:max(0, int(limit))]
        return items

    def summary(self):
        counts = {self.STATUS_DRAFT: 0, self.STATUS_DISMISSED: 0}
        for record in self.records:
            status = record.get("status")
            if status in counts:
                counts[status] += 1
        return {
            "error": False,
            "total": len(self.records),
            "counts": counts,
            "drafts": self.list_drafts(limit=10),
            "executed_count": 0,
        }

    def _draft_key(self, sku, proposal_type, recorded_at):
        return "|".join((sku, proposal_type, recorded_at))

    def _index_by_key(self, key):
        for index, record in enumerate(self.records):
            if record.get("draft_key") == key:
                return index
        return None

    def _result(self, record, saved):
        return {
            "error": False,
            "code": None,
            "task_draft": deepcopy(record),
            "saved": saved,
            "executed": False,
            "execution_allowed": False,
        }

    def _error(self, code, sku):
        return {
            "error": True,
            "code": code,
            "sku": sku or None,
            "task_draft": None,
            "saved": False,
            "executed": False,
            "execution_allowed": False,
        }

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
