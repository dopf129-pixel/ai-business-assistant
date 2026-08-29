from services.assistant_freshness_operational_runtime_service import AssistantFreshnessOperationalRuntimeService
from services.freshness_operational_snapshot_provider import FreshnessOperationalSnapshotProvider


def create_freshness_operational_runtime(reader=None):
    """Create the read-only freshness runtime only when an explicit reader exists."""
    if reader is None:
        return None
    provider = FreshnessOperationalSnapshotProvider(reader)
    return AssistantFreshnessOperationalRuntimeService(provider)
