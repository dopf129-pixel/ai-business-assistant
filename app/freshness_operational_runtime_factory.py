from product_task_freshness_operational_diagnostics import (
    build_freshness_diagnostics_audit,
    build_freshness_runtime_activation_readiness,
    collect_freshness_snapshot_diagnostics,
)
from services.assistant_freshness_operational_runtime_service import (
    AssistantFreshnessOperationalRuntimeService,
)
from services.freshness_operational_snapshot_provider import (
    FreshnessOperationalSnapshotProvider,
)


def evaluate_freshness_operational_runtime_activation(reader=None):
    """Return a read-only activation audit; never implies lifecycle or mutation readiness."""
    diagnostics = collect_freshness_snapshot_diagnostics(reader)
    activation = build_freshness_runtime_activation_readiness(diagnostics)
    return build_freshness_diagnostics_audit(diagnostics, activation)


def create_freshness_operational_runtime(reader=None):
    """Create the read-only runtime only for an explicitly supplied complete reader."""
    if reader is None:
        return None
    activation = evaluate_freshness_operational_runtime_activation(reader)
    if activation.get("error") is not False or activation.get("activation_ready") is not True:
        return None
    provider = FreshnessOperationalSnapshotProvider(reader)
    return AssistantFreshnessOperationalRuntimeService(provider)
