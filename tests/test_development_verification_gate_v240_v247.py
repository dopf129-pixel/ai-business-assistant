from app.services.assistant_development_agent import (
    AssistantDevelopmentAgent,
)
from app.services.assistant_development_decision_service import (
    AssistantDevelopmentDecisionService,
)
from app.services.assistant_development_workflow_service import (
    AssistantDevelopmentWorkflowService,
)
from app.services.assistant_git_checkpoint_service import (
    AssistantGitCheckpointService,
)
from app.services.assistant_project_verification_service import (
    AssistantProjectVerificationService,
)
from app.services.assistant_test_runner_service import (
    AssistantTestRunnerService,
)


CURRENT_SHA = "441eee4a87b1f20ef3dd7f92bb655056644ad5a3"
OLD_SHA = "11883f901d3bb344816735b834392a59185c0c81"


def _verification():
    return AssistantProjectVerificationService()


def _report(sha, passed=1000, failed=0):
    return AssistantTestRunnerService().create_test_report(
        passed=passed,
        failed=failed,
        total=passed + failed,
        commit_sha=sha,
    )


def test_v240_workflow_exposes_current_sha_verification_metadata():
    service = AssistantDevelopmentWorkflowService(
        verification_service=_verification()
    )

    result = service.start_workflow(
        "change",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["status"] == "started"
    assert result["test_validation_status"] == "verified"
    assert result["verification"]["status"] == "CURRENT_VERIFIED"


def test_v241_test_validation_step_blocks_stale_baseline():
    service = AssistantDevelopmentWorkflowService(
        verification_service=_verification()
    )
    service.start_workflow("change")

    result = service.complete_step(
        "test_validation",
        current_sha=CURRENT_SHA,
        test_report=_report(OLD_SHA, passed=982),
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "current_suite_not_verified"
    assert result["verification"]["status"] == "STALE_BASELINE"


def test_v241_test_validation_step_accepts_exact_current_green_report():
    service = AssistantDevelopmentWorkflowService(
        verification_service=_verification()
    )
    service.start_workflow("change")

    result = service.complete_step(
        "test_validation",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["status"] == "completed"
    assert result["verification"]["current_suite_passed"] is True


def test_v242_verified_checkpoint_blocks_without_current_verification():
    service = AssistantGitCheckpointService(
        verification_service=_verification()
    )

    result = service.prepare_verified_checkpoint(
        ["app/a.py"],
        "checkpoint",
        current_sha=CURRENT_SHA,
        test_report=_report(OLD_SHA, passed=982),
    )

    assert result["status"] == "blocked"
    assert result["code"] == "CURRENT_SUITE_NOT_VERIFIED"
    assert result["checkpoint_ready"] is False


def test_v242_verified_checkpoint_accepts_exact_current_green_report():
    service = AssistantGitCheckpointService(
        verification_service=_verification()
    )

    result = service.prepare_verified_checkpoint(
        ["app/a.py", "tests/test_a.py"],
        "checkpoint",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["status"] == "ready"
    assert result["checkpoint_ready"] is True
    assert result["files_changed"] == 2
    assert result["current_sha"] == CURRENT_SHA


def test_v243_development_decision_blocks_completed_report_with_stale_suite():
    verification = _verification().evaluate(
        CURRENT_SHA,
        _report(OLD_SHA, passed=982),
    )

    result = AssistantDevelopmentDecisionService().evaluate({
        "status": "completed",
        "verification": verification,
    })

    assert result["decision"] == "blocked"
    assert result["reason"] == "current_suite_not_verified"


def test_v243_development_decision_blocks_verified_failed_suite():
    verification = _verification().evaluate(
        CURRENT_SHA,
        _report(CURRENT_SHA, passed=999, failed=1),
    )

    result = AssistantDevelopmentDecisionService().evaluate({
        "status": "completed",
        "verification": verification,
    })

    assert result["decision"] == "blocked"
    assert result["reason"] == "current_suite_failed"


def test_v244_v245_agent_cycle_blocks_checkpoint_on_stale_baseline():
    verification_service = _verification()
    agent = AssistantDevelopmentAgent(
        workflow=AssistantDevelopmentWorkflowService(
            verification_service=verification_service
        ),
        checkpoint_service=AssistantGitCheckpointService(
            verification_service=verification_service
        ),
    )

    result = agent.run_development_cycle(
        "change",
        current_sha=CURRENT_SHA,
        test_report=_report(OLD_SHA, passed=982),
    )

    assert result["status"] == "workflow_blocked"
    assert result["workflow"]["test_validation_status"] == "unverified"
    assert result["checkpoint"]["status"] == "blocked"
    assert result["checkpoint"]["checkpoint_ready"] is False
    assert result["report"]["status"] == "blocked"
    assert result["report"]["verification"]["status"] == "STALE_BASELINE"


def test_v244_v245_agent_cycle_allows_current_verified_checkpoint_metadata():
    verification_service = _verification()
    agent = AssistantDevelopmentAgent(
        workflow=AssistantDevelopmentWorkflowService(
            verification_service=verification_service
        ),
        checkpoint_service=AssistantGitCheckpointService(
            verification_service=verification_service
        ),
    )

    result = agent.run_development_cycle(
        "change",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["status"] == "workflow_completed"
    assert result["workflow"]["test_validation_status"] == "verified"
    assert result["checkpoint"]["status"] == "ready"
    assert result["checkpoint"]["checkpoint_ready"] is True
    assert result["report"]["status"] == "completed"


def test_v246_legacy_workflow_and_checkpoint_calls_remain_compatible():
    workflow = AssistantDevelopmentWorkflowService()
    started = workflow.start_workflow("change")
    completed = workflow.complete_step("test_validation")

    checkpoint = AssistantGitCheckpointService().prepare_checkpoint(
        ["a.py"],
        "legacy",
    )

    assert started == {
        "change": "change",
        "status": "started",
        "steps": [
            "change_analysis",
            "test_validation",
            "documentation_validation",
            "checkpoint_preparation",
        ],
    }
    assert completed == {
        "step": "test_validation",
        "status": "completed",
    }
    assert checkpoint["status"] == "ready"
    assert "checkpoint_ready" not in checkpoint


def test_v247_agent_fails_closed_when_verified_checkpoint_capability_missing():
    class LegacyCheckpoint:
        def prepare_checkpoint(self, files, message):
            return {
                "status": "ready",
                "files_changed": len(files),
                "files": list(files),
                "message": message,
            }

    agent = AssistantDevelopmentAgent(
        checkpoint_service=LegacyCheckpoint(),
    )

    result = agent.run_development_cycle(
        "change",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["status"] == "workflow_blocked"
    assert result["checkpoint"]["status"] == "blocked"
    assert result["checkpoint"]["code"] == (
        "VERIFIED_CHECKPOINT_CAPABILITY_MISSING"
    )


def test_v247_agent_with_partial_verification_wiring_fails_closed():
    verification_service = _verification()
    agent = AssistantDevelopmentAgent(
        workflow=AssistantDevelopmentWorkflowService(
            verification_service=verification_service
        ),
    )

    result = agent.run_development_cycle(
        "change",
        current_sha=CURRENT_SHA,
        test_report=_report(CURRENT_SHA),
    )

    assert result["workflow"]["test_validation_status"] == "verified"
    assert result["checkpoint"] == "not_connected"
    assert result["report"]["status"] == "blocked"
    assert result["status"] == "workflow_blocked"
