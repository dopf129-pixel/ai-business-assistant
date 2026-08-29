from copy import deepcopy
from datetime import datetime, timezone


class ProductTaskDraftFreshnessService:

    STATUS_FRESH = "FRESH"
    STATUS_STALE = "STALE"
    STATUS_UNKNOWN = "UNKNOWN"

    REQUIRED_COMPONENTS = {
        "REVIEW_REPLENISHMENT": ("sales", "stock"),
        "REVIEW_UNIT_ECONOMICS": ("unit_economics",),
        "REVIEW_MARGIN": ("unit_economics",),
    }

    COMPONENT_FIELDS = {
        "sales": (
            "sales_source_recorded_at",
            "SALES_DATA_STALE",
            "SALES_TIMESTAMP_UNKNOWN",
            "SALES_TIMESTAMP_IN_FUTURE",
        ),
        "stock": (
            "stock_source_recorded_at",
            "STOCK_DATA_STALE",
            "STOCK_TIMESTAMP_UNKNOWN",
            "STOCK_TIMESTAMP_IN_FUTURE",
        ),
        "unit_economics": (
            "unit_economics_source_recorded_at",
            "UNIT_ECONOMICS_DATA_STALE",
            "UNIT_ECONOMICS_TIMESTAMP_UNKNOWN",
            "UNIT_ECONOMICS_TIMESTAMP_IN_FUTURE",
        ),
    }

    def __init__(self, max_snapshot_age_seconds=3600, clock=None):
        self.max_snapshot_age_seconds = max(0, float(max_snapshot_age_seconds))
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, draft):
        source = deepcopy(draft or {})
        proposal_type = str(source.get("proposal_type") or "").upper()
        required_components = self.REQUIRED_COMPONENTS.get(proposal_type)

        snapshot = self._component(
            source.get("decision_recorded_at"),
            stale_code="DECISION_SNAPSHOT_STALE",
            unknown_code="DECISION_SNAPSHOT_TIMESTAMP_UNKNOWN",
            future_code="DECISION_SNAPSHOT_TIMESTAMP_IN_FUTURE",
        )

        components = {}
        if required_components is None:
            required_components = tuple(self.COMPONENT_FIELDS)

        for component_name in required_components:
            field, stale_code, unknown_code, future_code = (
                self.COMPONENT_FIELDS[component_name]
            )
            components[component_name] = self._component(
                source.get(field),
                stale_code=stale_code,
                unknown_code=unknown_code,
                future_code=future_code,
            )

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
            "proposal_type": proposal_type or None,
            "status": status,
            "decision_snapshot": snapshot,
            "components": components,
            "reasons": reasons,
            "execution_ready": False,
            "executed": False,
        }

    def _component(
        self,
        timestamp,
        stale_code,
        unknown_code,
        future_code,
    ):
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
        now = now.astimezone(timezone.utc)

        age_seconds = (now - parsed).total_seconds()
        if age_seconds < 0:
            return {
                "status": self.STATUS_UNKNOWN,
                "recorded_at": timestamp,
                "age_seconds": None,
                "reasons": [future_code],
            }

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
