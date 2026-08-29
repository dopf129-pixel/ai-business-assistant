from product_task_freshness_operational_readiness import (
    build_freshness_operational_projection,
    build_freshness_readiness_summary,
)
from services.assistant_freshness_operational_runtime_service import (
    AssistantFreshnessOperationalRuntimeService,
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


def _artifact(status, **overrides):
    result = dict(FLAGS, error=False, status=status)
    result.update(overrides)
    return result


def _snapshot():
    prep_decision = "prep-decision-1"
    prep_audit = "evidence-application-preparation-audit:" + prep_decision
    auth = "executor-auth-1"
    executor_audit = "evidence-application-executor-admission-audit:" + auth
    write_audit = "evidence-write-protocol-audit:write-decision-1"
    return {
        "preparation_audit": _artifact(
            "APPLICATION_PREPARATION_AUDIT_READY",
            preparation_decision_id=prep_decision,
            preparation_audit_id=prep_audit,
        ),
        "executor_admission_audit": _artifact(
            "APPLICATION_EXECUTOR_ADMISSION_AUDIT_READY",
            preparation_decision_id=prep_decision,
            preparation_audit_id=prep_audit,
            executor_authorization_id=auth,
            executor_admission_audit_id=executor_audit,
            target_revision_id="rev-9",
            target_version=9,
        ),
        "write_protocol_audit": _artifact(
            "APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
            executor_authorization_id=auth,
            executor_admission_audit_id=executor_audit,
            write_protocol_audit_id=write_audit,
            expected_target_revision_id="rev-9",
            expected_target_version=9,
        ),
        "adapter_boundary_audit": _artifact(
            "WRITE_ADAPTER_BOUNDARY_AUDIT_READY",
            executor_authorization_id=auth,
            write_protocol_audit_id=write_audit,
            expected_target_revision_id="rev-9",
            expected_target_version=9,
        ),
    }


def test_v194_projects_exact_stage_completion_without_mutation_claim():
    result = build_freshness_operational_projection(_snapshot())
    assert result["status"] == "FRESHNESS_OPERATIONAL_READINESS"
    assert result["highest_complete_stage"] == "ADAPTER_BOUNDARY"
    assert result["operationally_ready"] is True
    assert result["mutation_ready"] is False
    assert result["business_execution_ready"] is False
    assert result["persistent"] is False
    assert result["executed"] is False


def test_v195_exposes_blockers_fail_closed():
    snapshot = _snapshot()
    snapshot["write_protocol_audit"] = _artifact(
        "APPLICATION_WRITE_PROTOCOL_AUDIT_READY",
        persistent=True,
    )
    result = build_freshness_operational_projection(snapshot)
    assert result["operationally_ready"] is False
    assert "WRITE_PROTOCOL_SAFETY_VIOLATION" in result["blockers"]
    assert result["next_action"] == "REVIEW_BLOCKERS"


def test_v195_rejects_forged_cross_stage_lineage():
    snapshot = _snapshot()
    snapshot["adapter_boundary_audit"]["executor_authorization_id"] = "forged"
    result = build_freshness_operational_projection(snapshot)
    assert result["operationally_ready"] is False
    assert "WRITE_ADAPTER_LINEAGE_MISMATCH" in result["blockers"]


def test_v196_selects_next_missing_stage_deterministically():
    snapshot = _snapshot()
    snapshot["write_protocol_audit"] = None
    snapshot["adapter_boundary_audit"] = None
    result = build_freshness_operational_projection(snapshot)
    assert result["highest_complete_stage"] == "EXECUTOR_ADMISSION"
    assert result["next_action"] == "CONTINUE_WRITE_PROTOCOL"
    assert result["blockers"] == []


def test_v197_summary_recomputes_readiness_and_rejects_contradiction():
    projection = build_freshness_operational_projection(_snapshot())
    summary = build_freshness_readiness_summary(projection)
    assert summary["status"] == "FRESHNESS_OPERATIONAL_READINESS_SUMMARY"
    assert summary["operationally_ready"] is True
    assert summary["next_action"] == "AWAIT_REAL_WRITE_ADAPTER"

    forged = dict(projection, operationally_ready=False)
    blocked = build_freshness_readiness_summary(forged)
    assert blocked["code"] == "FRESHNESS_OPERATIONAL_READY_CONTRADICTORY"


class _Provider:
    def __init__(self, value):
        self.value = value

    def get_snapshot(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_v198_runtime_routes_only_explicit_status_requests():
    runtime = AssistantFreshnessOperationalRuntimeService(_Provider(_snapshot()))
    assert runtime.handle_text("покажи статус свежести")["operationally_ready"] is True
    assert runtime.handle_text("что с продажами") is None


def test_v198_runtime_provider_failure_is_read_only_blocked():
    runtime = AssistantFreshnessOperationalRuntimeService(_Provider(RuntimeError("boom")))
    result = runtime.handle_text("freshness status")
    assert result["code"] == "FRESHNESS_OPERATIONAL_SNAPSHOT_UNAVAILABLE"
    assert result["read_only"] is True
    assert result["persistent"] is False
