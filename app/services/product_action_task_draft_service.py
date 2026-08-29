from copy import deepcopy
from datetime import datetime, timezone


class ProductActionTaskDraftService:

    STATUS_DRAFT = "DRAFT"
    STATUS_DISMISSED = "DISMISSED"
    STATUS_STALE = "STALE"
    STATUS_ARCHIVED = "ARCHIVED"

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
        if index is not None and self.records[index].get("status") == (
            self.STATUS_ARCHIVED
        ):
            return self._result(self.records[index], saved=False)

        now = str(self.clock())
        previous = self.records[index] if index is not None else None
        previous_status = previous.get("status") if previous else None
        record = {
            "draft_key": draft_key,
            "draft_id": (
                self.records[index].get("draft_id")
                if index is not None
                else self._next_draft_id()
            ),
            "sku": sku,
            "proposal_type": proposal_type,
            "status": self.STATUS_DRAFT,
            "decision_type": decision.get("decision_type"),
            "priority": decision.get("priority"),
            "decision_recorded_at": recorded_at,
            "current_stock": decision.get("current_stock"),
            "sales_velocity": decision.get("sales_velocity"),
            "days_of_stock": decision.get("days_of_stock"),
            "profit_per_unit": decision.get("profit_per_unit"),
            "margin_percent": decision.get("margin_percent"),
            "economics_basis": decision.get("economics_basis"),
            "created_at": (
                self.records[index].get("created_at")
                if index is not None
                else now
            ),
            "updated_at": now,
            "events": list(previous.get("events") or []) if previous else [],
            "execution_allowed": False,
            "executed": False,
        }
        self._append_event(
            record,
            event_type="CREATED" if previous is None else "REOPENED",
            from_status=previous_status,
            to_status=self.STATUS_DRAFT,
            source="CONFIRMATION",
            occurred_at=now,
        )
        if index is None:
            self.records.append(record)
        else:
            self.records[index] = record
        self._save_records()
        return self._result(record, saved=True)

    def reconcile(
        self,
        sku,
        current_proposal_type,
        current_decision_recorded_at,
    ):
        sku = str(sku or "").strip()
        current_key = self._draft_key(
            sku,
            str(current_proposal_type or "").strip().upper(),
            str(current_decision_recorded_at or "").strip(),
        )
        changed = []
        for record in self.records:
            if (
                str(record.get("sku")) != sku
                or record.get("status") != self.STATUS_DRAFT
                or record.get("draft_key") == current_key
            ):
                continue
            record["status"] = self.STATUS_STALE
            occurred_at = str(self.clock())
            record["updated_at"] = occurred_at
            self._append_event(
                record,
                event_type="MARKED_STALE",
                from_status=self.STATUS_DRAFT,
                to_status=self.STATUS_STALE,
                source="DECISION_RECONCILE",
                occurred_at=occurred_at,
            )
            changed.append(deepcopy(record))
        if changed:
            self._save_records()
        return {
            "error": False,
            "stale_count": len(changed),
            "stale_drafts": changed,
            "executed": False,
            "execution_allowed": False,
        }

    def archive(self, draft_id):
        index = self._index_by_id(draft_id)
        if index is None:
            return self._error("TASK_DRAFT_NOT_FOUND", None)
        record = self.records[index]
        if record.get("status") == self.STATUS_ARCHIVED:
            return self._result(record, saved=False)
        if record.get("status") not in {
            self.STATUS_DRAFT,
            self.STATUS_STALE,
            self.STATUS_DISMISSED,
        }:
            return self._error("TASK_DRAFT_NOT_ARCHIVABLE", record.get("sku"))
        previous_status = record.get("status")
        occurred_at = str(self.clock())
        record["status"] = self.STATUS_ARCHIVED
        record["updated_at"] = occurred_at
        self._append_event(
            record,
            event_type="ARCHIVED",
            from_status=previous_status,
            to_status=self.STATUS_ARCHIVED,
            source="USER_REVIEW",
            occurred_at=occurred_at,
        )
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
        if record.get("status") == self.STATUS_ARCHIVED:
            return self._result(record, saved=False)
        if record.get("status") == self.STATUS_DISMISSED:
            return self._result(record, saved=False)
        previous_status = record.get("status")
        occurred_at = str(self.clock())
        record["status"] = self.STATUS_DISMISSED
        record["updated_at"] = occurred_at
        self._append_event(
            record,
            event_type="DISMISSED",
            from_status=previous_status,
            to_status=self.STATUS_DISMISSED,
            source="PROPOSAL_REJECTION",
            occurred_at=occurred_at,
        )
        self._save_records()
        return self._result(record, saved=True)

    def latest_for_sku(self, sku):
        sku = str(sku or "").strip()
        for record in reversed(self.records):
            if str(record.get("sku")) == sku:
                return deepcopy(record)
        return None

    def get(self, draft_id):
        index = self._index_by_id(draft_id)
        if index is None:
            return self._error("TASK_DRAFT_NOT_FOUND", None)
        record = deepcopy(self.records[index])
        return {
            "error": False,
            "code": None,
            "task_draft": record,
            "audit_events": deepcopy(record.get("events") or []),
            "legacy_history_unavailable": not bool(record.get("events")),
            "executed": False,
            "execution_allowed": False,
        }

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
        counts = {
            self.STATUS_DRAFT: 0,
            self.STATUS_STALE: 0,
            self.STATUS_DISMISSED: 0,
            self.STATUS_ARCHIVED: 0,
        }
        for record in self.records:
            status = record.get("status")
            if status in counts:
                counts[status] += 1
        return {
            "error": False,
            "total": len(self.records),
            "counts": counts,
            "drafts": self.list_drafts(limit=10),
            "audit_events_count": sum(
                len(record.get("events") or [])
                for record in self.records
            ),
            "executed_count": 0,
        }

    def _draft_key(self, sku, proposal_type, recorded_at):
        return "|".join((sku, proposal_type, recorded_at))

    def _index_by_key(self, key):
        for index, record in enumerate(self.records):
            if record.get("draft_key") == key:
                return index
        return None

    def _index_by_id(self, draft_id):
        draft_id = str(draft_id or "").strip()
        for index, record in enumerate(self.records):
            if str(record.get("draft_id")) == draft_id:
                return index
        return None

    def _next_draft_id(self):
        maximum = 0
        for record in self.records:
            value = str(record.get("draft_id") or "")
            if value.startswith("d") and value[1:].isdigit():
                maximum = max(maximum, int(value[1:]))
        return "d" + str(maximum + 1)

    def _append_event(
        self,
        record,
        event_type,
        from_status,
        to_status,
        source,
        occurred_at,
    ):
        events = record.setdefault("events", [])
        events.append({
            "event_id": "e" + str(len(events) + 1),
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "source": source,
            "occurred_at": str(occurred_at),
            "executed": False,
        })

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
        normalized = [
            dict(item) for item in records if isinstance(item, dict)
        ]
        used = {
            str(item.get("draft_id"))
            for item in normalized
            if item.get("draft_id")
        }
        next_number = 1
        for item in normalized:
            if item.get("draft_id"):
                continue
            while "d" + str(next_number) in used:
                next_number += 1
            item["draft_id"] = "d" + str(next_number)
            used.add(item["draft_id"])
            next_number += 1
        for item in normalized:
            events = item.get("events")
            item["events"] = (
                [dict(event) for event in events if isinstance(event, dict)]
                if isinstance(events, list)
                else []
            )
        return normalized

    def _save_records(self):
        if self.storage_service is not None:
            self.storage_service.save(self.records)
