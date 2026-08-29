from product_task_freshness_operational_diagnostics import (
    build_freshness_diagnostics_audit,
    build_freshness_runtime_activation_readiness,
    collect_freshness_snapshot_diagnostics,
    inspect_freshness_reader_capabilities,
)
from services.assistant_freshness_operational_runtime_service import (
    AssistantFreshnessOperationalRuntimeService,
)
from services.freshness_operational_snapshot_provider import (
    FreshnessOperationalSnapshotProvider,
)


FLAGS = {
    "application_allowed": False,
    "application_started": False,
    "persistent": False,
    "product_decision_recomputed": False,
    "product_decision_mutated": False,
    "task_draft_mutated": False,
    "execution_allowed": False,
    "execution_ready": False,
    "executed": False,
    "source_freshness_proven": False,
}


class _Reader:
    def __init__(self, values=None):
        self.values = values or {}

    def _get(self, name):
        value = self.values.get(name)
        if isinstance(value, Exception):
            raise value
        return value

    def get_preparation_audit(self):
        return self._get("preparation_audit")

    def get_executor_admission_audit(self):
        return self._get("executor_admission_audit")

    def get_write_protocol_audit(self):
        return self._get("write_protocol_audit")

    def get_adapter_boundary_audit(self):
        return self._get("adapter_boundary_audit")


class _PartialReader:
    def get_preparation_audit(self):
        return None


def _artifact(status):
    return dict(FLAGS, error=False, status=status)


def test_v204_reader_capability_matrix_is_exact_and_read_only():
    result = inspect_freshness_reader_capabilities(_Reader())
    assert result["status"] == "FRESHNESS_READER_CAPABILITIES"
    assert result["capability_count"] == 4
    assert result["missing_capability_count"] == 0
    assert result["reader_complete"] is True
    assert result["persistent"] is False
    assert result["executed"] is False


def test_v205_partial_reader_reports_missing_capabilities_without_throwing():
    result = collect_freshness_snapshot_diagnostics(_PartialReader())
    assert result["reader_complete"] is False
    assert result["snapshot_usable"] is False
    assert result["blocker_count"] == 3
    assert all("CAPABILITY_MISSING" in item for item in result["blockers"])


def test_v206_diagnostics_distinguish_missing_error_malformed_and_available():
    reader = _Reader({
        "preparation_audit": _artifact("APPLICATION_PREPARATION_AUDIT_READY"),
        "executor_admission_audit": None,
        "write_protocol_audit": RuntimeError("boom"),
        "adapter_boundary_audit": "bad",
    })
    result = collect_freshness_snapshot_diagnostics(reader)
    states = {item["artifact"]: item["state"] for item in result["artifacts"]}
    assert states == {
        "preparation_audit": "AVAILABLE",
        "executor_admission_audit": "MISSING",
        "write_protocol_audit": "READ_ERROR",
        "adapter_boundary_audit": "MALFORMED",
    }
    assert result["snapshot_usable"] is False


def test_v207_activation_readiness_does_not_claim_lifecycle_or_mutation_readiness():
    diagnostics = collect_freshness_snapshot_diagnostics(_Reader())
    ready = build_freshness_runtime_activation_readiness(diagnostics)
    assert ready["activation_ready"] is True
    assert ready["lifecycle_ready"] is False
    assert ready["mutation_ready"] is False
    assert ready["business_execution_ready"] is False
    assert ready["executed"] is False


def test_v208_provider_exposes_diagnostics_without_changing_snapshot_contract():
    provider = FreshnessOperationalSnapshotProvider(_Reader())
    diagnostics = provider.get_diagnostics()
    snapshot = provider.get_snapshot()
    assert diagnostics["status"] == "FRESHNESS_SNAPSHOT_DIAGNOSTICS"
    assert snapshot == {
        "preparation_audit": None,
        "executor_admission_audit": None,
        "write_protocol_audit": None,
        "adapter_boundary_audit": None,
    }


def test_v209_runtime_diagnostics_route_is_separate_from_status_route():
    provider = FreshnessOperationalSnapshotProvider(_Reader())
    runtime = AssistantFreshnessOperationalRuntimeService(provider)
    diagnostics = runtime.handle_text("freshness diagnostics")
    assert diagnostics["status"] == "FRESHNESS_DIAGNOSTICS_AUDIT_READY"
    assert diagnostics["activation_ready"] is True
    assert diagnostics["mutation_ready"] is False
    assert runtime.handle_text("что с продажами") is None


def test_v210_diagnostics_audit_rejects_forged_activation_claim():
    diagnostics = collect_freshness_snapshot_diagnostics(_Reader())
    ready = build_freshness_runtime_activation_readiness(diagnostics)
    forged = dict(ready, lifecycle_ready=True)
    result = build_freshness_diagnostics_audit(diagnostics, forged)
    assert result["error"] is True
    assert result["code"] == "FRESHNESS_DIAGNOSTICS_AUDIT_CONTRADICTION"


def test_safety_violating_artifact_is_reported_and_never_activation_ready():
    unsafe = _artifact("APPLICATION_PREPARATION_AUDIT_READY")
    unsafe["persistent"] = True
    diagnostics = collect_freshness_snapshot_diagnostics(_Reader({"preparation_audit": unsafe}))
    assert "preparation_audit:SAFETY_VIOLATION" in diagnostics["blockers"]
    ready = build_freshness_runtime_activation_readiness(diagnostics)
    assert ready["activation_ready"] is False
