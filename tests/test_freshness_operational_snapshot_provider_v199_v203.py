from freshness_operational_runtime_factory import create_freshness_operational_runtime
from services.freshness_operational_snapshot_provider import FreshnessOperationalSnapshotProvider


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


def _snapshot_parts():
    prep_decision = "prep-decision-1"
    prep_audit = "evidence-application-preparation-audit:" + prep_decision
    auth = "executor-auth-1"
    executor_audit = "evidence-application-executor-admission-audit:" + auth
    write_audit = "evidence-write-protocol-audit:write-decision-1"
    common_target = {"target_revision_id": "rev-1", "target_version": 1}
    return {
        "preparation_audit": dict(FLAGS, error=False, status="APPLICATION_PREPARATION_AUDIT_READY",
            preparation_decision_id=prep_decision, preparation_audit_id=prep_audit),
        "executor_admission_audit": dict(FLAGS, error=False, status="APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY",
            preparation_decision_id=prep_decision, preparation_audit_id=prep_audit,
            executor_authorization_id=auth, executor_admission_audit_id=executor_audit, **common_target),
        "write_protocol_audit": dict(FLAGS, error=False, status="APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
            executor_authorization_id=auth, executor_admission_audit_id=executor_audit,
            write_protocol_audit_id=write_audit,
            expected_target_revision_id="rev-1", expected_target_version=1),
        "adapter_boundary_audit": dict(FLAGS, error=False, status="WRITE_ADAPTER_BOUNDARY_AUDIT_READY",
            executor_authorization_id=auth, write_protocol_audit_id=write_audit,
            expected_target_revision_id="rev-1", expected_target_version=1),
    }


class _Reader:
    def __init__(self, values=None):
        self.values = values or _snapshot_parts()

    def get_preparation_audit(self): return self.values.get("preparation_audit")
    def get_executor_admission_audit(self): return self.values.get("executor_admission_audit")
    def get_write_protocol_audit(self): return self.values.get("write_protocol_audit")
    def get_adapter_boundary_audit(self): return self.values.get("adapter_boundary_audit")


def test_v199_provider_aggregates_only_explicit_readers():
    provider = FreshnessOperationalSnapshotProvider(_Reader())
    snapshot = provider.get_snapshot()
    assert set(snapshot) == {"preparation_audit", "executor_admission_audit", "write_protocol_audit", "adapter_boundary_audit"}
    assert snapshot["preparation_audit"]["status"] == "APPLICATION_PREPARATION_AUDIT_READY"


def test_v200_factory_is_inactive_without_real_reader():
    assert create_freshness_operational_runtime() is None


def test_v201_factory_runtime_reaches_read_only_operational_projection():
    runtime = create_freshness_operational_runtime(_Reader())
    result = runtime.handle_text("статус свежести")
    assert result["status"] == "FRESHNESS_OPERATIONAL_READINESS_SUMMARY"
    assert result["operationally_ready"] is True
    assert result["mutation_ready"] is False
    assert result["persistent"] is False
    assert result["executed"] is False


def test_v202_missing_reader_capability_fails_closed_through_runtime():
    class BrokenReader:
        def get_preparation_audit(self): return None
    runtime = create_freshness_operational_runtime(BrokenReader())
    result = runtime.handle_text("freshness status")
    assert result["error"] is True
    assert result["code"] == "FRESHNESS_OPERATIONAL_SNAPSHOT_UNAVAILABLE"
    assert result["read_only"] is True


def test_v203_provider_returns_copies_not_mutable_reader_objects():
    values = _snapshot_parts()
    provider = FreshnessOperationalSnapshotProvider(_Reader(values))
    snapshot = provider.get_snapshot()
    snapshot["preparation_audit"]["status"] = "FORGED"
    assert values["preparation_audit"]["status"] == "APPLICATION_PREPARATION_AUDIT_READY"
