"""Pure transition rules for durable unit-economics price experiments."""


class UnitEconomicsExperimentStateMachine:
    """Describe lifecycle transitions without performing storage or source I/O."""

    STATES = frozenset({
        "DRAFT", "READY", "BASELINE_ACTIVE", "BASELINE_REVIEW", "CANDIDATE_READY",
        "CANDIDATE_ACTIVE", "CANDIDATE_REVIEW", "PAUSED", "CANCELLED", "COMPLETED",
        "ARCHIVED",
    })
    _TERMINAL = frozenset({"CANCELLED", "COMPLETED", "ARCHIVED"})
    _ACTIVE = frozenset({"BASELINE_ACTIVE", "CANDIDATE_ACTIVE"})

    @classmethod
    def transition(
        cls, current_state, action, *, readiness_passed=False, phase_confirmed=False,
        evidence_frozen=False, candidate_selected=False, comparable_baseline=False,
        decision_recorded=False, resume_target=None, fresh_confirmation=False,
        active_guard_available=False,
    ):
        if current_state not in cls.STATES or not isinstance(action, str):
            return cls._error("EXPERIMENT_STATE_OR_ACTION_INVALID")

        target = None
        effects = []
        if action == "mark_ready" and current_state == "DRAFT":
            if readiness_passed is not True:
                return cls._error("EXPERIMENT_READINESS_GATE_FAILED")
            target = "READY"
        elif action == "activate_baseline" and current_state == "READY":
            if phase_confirmed is not True:
                return cls._error("EXPERIMENT_PHASE_CONFIRMATION_REQUIRED")
            if active_guard_available is not True:
                return cls._error("EXPERIMENT_ACTIVE_SKU_GUARD_UNAVAILABLE")
            target = "BASELINE_ACTIVE"
            effects = ["CREATE_BASELINE_PHASE", "ACQUIRE_ACTIVE_SKU_GUARD"]
        elif action == "finish_baseline" and current_state == "BASELINE_ACTIVE":
            if evidence_frozen is not True:
                return cls._error("EXPERIMENT_PHASE_EVIDENCE_REQUIRED")
            target = "BASELINE_REVIEW"
            effects = ["FREEZE_PHASE_EVIDENCE", "APPEND_RESULT", "RELEASE_ACTIVE_SKU_GUARD"]
        elif action == "pause" and current_state in cls._ACTIVE:
            target = "PAUSED"
            resume_target = "READY" if current_state == "BASELINE_ACTIVE" else "CANDIDATE_READY"
            effects = ["CLOSE_ACTIVE_SEGMENT", "STORE_RESUME_TARGET", "RELEASE_ACTIVE_SKU_GUARD"]
        elif action == "select_candidate" and current_state in {
            "BASELINE_REVIEW", "CANDIDATE_REVIEW",
        }:
            if candidate_selected is not True:
                return cls._error("EXPERIMENT_CANDIDATE_NOT_SELECTED")
            if comparable_baseline is not True:
                return cls._error("EXPERIMENT_BASELINE_NOT_COMPARABLE")
            target = "CANDIDATE_READY"
        elif action == "activate_candidate" and current_state == "CANDIDATE_READY":
            if phase_confirmed is not True:
                return cls._error("EXPERIMENT_PHASE_CONFIRMATION_REQUIRED")
            if active_guard_available is not True:
                return cls._error("EXPERIMENT_ACTIVE_SKU_GUARD_UNAVAILABLE")
            target = "CANDIDATE_ACTIVE"
            effects = ["CREATE_CANDIDATE_PHASE", "ACQUIRE_ACTIVE_SKU_GUARD"]
        elif action == "finish_candidate" and current_state == "CANDIDATE_ACTIVE":
            if evidence_frozen is not True:
                return cls._error("EXPERIMENT_PHASE_EVIDENCE_REQUIRED")
            target = "CANDIDATE_REVIEW"
            effects = ["FREEZE_PHASE_EVIDENCE", "APPEND_RESULT", "RELEASE_ACTIVE_SKU_GUARD"]
        elif action == "complete" and current_state == "CANDIDATE_REVIEW":
            if decision_recorded is not True:
                return cls._error("EXPERIMENT_OWNER_DECISION_REQUIRED")
            target = "COMPLETED"
        elif action == "resume" and current_state == "PAUSED":
            if resume_target not in {"READY", "CANDIDATE_READY"}:
                return cls._error("EXPERIMENT_RESUME_TARGET_INVALID")
            if fresh_confirmation is not True:
                return cls._error("EXPERIMENT_FRESH_CONFIRMATION_REQUIRED")
            if active_guard_available is not True:
                return cls._error("EXPERIMENT_ACTIVE_SKU_GUARD_UNAVAILABLE")
            target = "BASELINE_ACTIVE" if resume_target == "READY" else "CANDIDATE_ACTIVE"
            effects = ["CREATE_NEW_SEGMENT", "ACQUIRE_ACTIVE_SKU_GUARD"]
        elif action == "cancel" and current_state not in cls._ACTIVE | cls._TERMINAL:
            target = "CANCELLED"
            effects = ["PRESERVE_HISTORY", "RELEASE_ACTIVE_SKU_GUARD"]
        elif action == "archive" and current_state not in cls._ACTIVE | {"ARCHIVED"}:
            target = "ARCHIVED"
            effects = ["PRESERVE_HISTORY", "RELEASE_ACTIVE_SKU_GUARD"]

        if target is None:
            return cls._error("EXPERIMENT_TRANSITION_NOT_ALLOWED")
        return {
            "error": False, "from_state": current_state, "to_state": target,
            "action": action, "effects": effects,
            "resume_target": resume_target if target == "PAUSED" else None,
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
