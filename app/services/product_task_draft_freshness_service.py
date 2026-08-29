from copy import deepcopy
from datetime import datetime, timezone


class ProductTaskDraftFreshnessService:

    STATUS_FRESH = "FRESH"
    STATUS_STALE = "STALE"
    STATUS_UNKNOWN = "UNKNOWN"

    def __init__(self, max_snapshot_age_seconds=3600, clock=None):
        self.max_snapshot_age_seconds = max(0, float(max_snapshot_age_seconds))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, draft):
        source = deepcopy(draft or {})
        snapshot = self._component(
            source.get("decision_recorded_at"),
            stale_code="DECISION_SNAPSHOT_STALE",
            unknown_code="DECISION_SNAPSHOT_TIMESTAMP_UNKNOWN",
        )
        components = {
            "sales": self._component(
                source.get("sales_source_recorded_at"),
                stale_code="SALES_DATA_STALE",
                unknown_code="SALES_TIMESTAMP_UNKNOWN",
            ),
            "stock": self._component(
                source.get("stock_source_recorded_at"),
                stale_code="STOCK_DATA_STALE",
                unknown_code="STOCK_TIMESTAMP_UNKNOWN",
            ),
            "unit_economics": self._component(
                source.get("unit_economics_source_recorded_at"),
                stale_code="UNIT_ECONOMICS_DATA_STALE",
                unknown_code="UNIT_ECONOMICS_TIMESTAMP_UNKNOWN",
            ),
        }
        statuses = [snapshot["status"]] + [
            item["status"] for item in components.values()
        ]
        if self.STATUS_STALE in statuses:
            status = self.STATUS_STALE
        elif self.STATUS_UNKNOWN in statuses:
            status = self.STATUS_UNKNOWN
        else:
            status = self.STATUS_FRESH
        reasons = list(snapshot["reasons"])
        for item in components.values():
            reasons.extend(item["reasons"])
        return {
            "error": False,
            "draft_id": source.get("draft_id"),
            "status": status,
            "decision_snapshot": snapshot,
            "components": components,
            "reasons": reasons,
            "execution_ready": False,
            "executed": False,
        }

    def _component(self, timestamp, stale_code, unknown_code):
        parsed = self._parse_timestamp(timestamp)
        if parsed is None:
            return {
                "status": self.STATUS_UNKNOWN,
                "recorded_at": timestamp,
                "age_seconds": None,
                "reasons": [unknown_code],
            }
        now = self.clock()
        if isinstance(now, str):
            now = self._parse_timestamp(now)
        if now is None:
            return {
                "status": self.STATUS_UNKNOWN,
                "recorded_at": timestamp,
                "age_seconds": None,
                "reasons": [unknown_code],
            }
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (now - parsed).total_seconds())
        stale = age_seconds > self.max_snapshot_age_seconds
        return {
            "status": self.STATUS_STALE if stale else self.STATUS_FRESH,
            "recorded_at": timestamp,
            "age_seconds": age_seconds,
            "reasons": [stale_code] if stale else [],
        }

    def _parse_timestamp(self, value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
