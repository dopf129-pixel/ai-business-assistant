from product_task_freshness_operational_readiness import (
    build_freshness_operational_projection,
    build_freshness_readiness_summary,
)


class AssistantFreshnessOperationalRuntimeService:
    """Read-only route for explicit freshness lifecycle status requests."""

    TOKENS = (
        "статус freshness",
        "freshness status",
        "готовность freshness",
        "статус свежести",
        "freshness readiness",
    )

    def __init__(self, snapshot_provider):
        self.snapshot_provider = snapshot_provider

    def handle_text(self, text):
        value = " ".join(str(text or "").strip().lower().split())
        if not any(token in value for token in self.TOKENS):
            return None

        try:
            snapshot = self.snapshot_provider.get_snapshot()
        except Exception:
            return self._unavailable("FRESHNESS_OPERATIONAL_SNAPSHOT_UNAVAILABLE")

        if not isinstance(snapshot, dict):
            return self._unavailable("FRESHNESS_OPERATIONAL_SNAPSHOT_INVALID")

        projection = build_freshness_operational_projection(snapshot)
        return build_freshness_readiness_summary(projection)

    @staticmethod
    def _unavailable(code):
        return {
            "error": True,
            "code": code,
            "status": "FRESHNESS_OPERATIONAL_READINESS_BLOCKED",
            "operationally_ready": False,
            "mutation_ready": False,
            "business_execution_ready": False,
            "human_action_required": True,
            "read_only": True,
            "application_allowed": False,
            "persistent": False,
            "task_draft_mutated": False,
            "execution_allowed": False,
            "executed": False,
        }
