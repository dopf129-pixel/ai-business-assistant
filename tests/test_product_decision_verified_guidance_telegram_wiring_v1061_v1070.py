from copy import deepcopy

import telegram_assistant_factory as telegram_factory

from app.product_decision_user_action_checklist import (
    build_product_decision_user_action_checklist,
)
from app.product_decision_user_action_guidance import (
    build_product_decision_user_action_guidance,
)
from app.services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:
    pass


class _Query:
    def __init__(self, result):
        self.result = result
        self.decision_history_service = None
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None

    def query(self, sku):
        result = deepcopy(self.result)
        result["sku"] = sku
        return result


class _Verifier:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def verify_latest(self, sku):
        self.calls.append(sku)
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


class _BuilderSpy:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, source):
        self.calls.append(deepcopy(source))
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


def _decision(**values):
    result = {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "missing_data": [],
        "decision_history_available": True,
        "decision_changed": False,
        "previous_decision_type": None,
        "previous_priority": None,
        "decision_recorded_at": "2026-09-01T20:00:00+00:00",
        "decision_history_count": 1,
        "previous_feedback": None,
        "decision_outcome": None,
        "decision_history_error": False,
    }
    result.update(values)
    return result


def _verification(**values):
    application_id = "product-decision-persistence-application:ready-1"
    result = {
        "error": False,
        "status": "PRODUCT_DECISION_PERSISTENCE_VERIFIED",
        "decision_persistence_verification_id": (
            "product-decision-persistence-verification:" + application_id
        ),
        "decision_persistence_application_id": application_id,
        "decision_persistence_application_readiness_id": "ready-1",
        "decision_persistence_authorization_id": "auth-1",
        "decision_persistence_eligibility_id": "eligibility-1",
        "decision_preview_review_id": "review-1",
        "decision_preview_delta_id": "delta-1",
        "recompute_preview_id": "preview-1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_verified": True,
        "verified_recorded_at": "2026-09-01T20:00:00+00:00",
        "verified_snapshot": {
            "sku": "hook-2",
            "product_id": "101",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
            "recorded_at": "2026-09-01T20:00:00+00:00",
        },
        "mismatched_fields": [],
        "verification_source": "DURABLE_HISTORY_READBACK",
        "externally_verified": False,
        "persistent": True,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _guidance():
    return build_product_decision_user_action_guidance(
        _verification()
    )


def _checklist():
    return build_product_decision_user_action_checklist(
        _guidance()
    )


def _handler(
    decision=None,
    verifier=None,
    guidance_builder=None,
    checklist_builder=None,
):
    return AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=_Query(
            decision or _decision()
        ),
        product_decision_persistence_verifier=verifier,
        product_decision_user_action_guidance_builder=guidance_builder,
        product_decision_user_action_checklist_builder=checklist_builder,
    )


def test_v1061_missing_verified_dependencies_preserves_decision_card():
    handler = _handler()

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert "🎯 Решение по товару" in result["message"]
    assert "Проверенный ручной чек-лист" not in result["message"]
    assert "verified_user_action_guidance_available" not in result


def test_v1062_blocked_verification_preserves_card_and_skips_builders():
    verifier = _Verifier({
        "error": True,
        "code": "DECISION_PERSISTENCE_READONLY_HISTORY_NOT_FOUND",
    })
    guidance = _BuilderSpy(_guidance())
    checklist = _BuilderSpy(_checklist())
    handler = _handler(
        verifier=verifier,
        guidance_builder=guidance,
        checklist_builder=checklist,
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert verifier.calls == ["hook-2"]
    assert guidance.calls == []
    assert checklist.calls == []
    assert "Проверенный ручной чек-лист" not in result["message"]


def test_v1063_malformed_verification_never_becomes_verified_ui():
    guidance = _BuilderSpy(_guidance())
    handler = _handler(
        verifier=_Verifier({"error": False}),
        guidance_builder=guidance,
        checklist_builder=_BuilderSpy(_checklist()),
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert guidance.calls == []
    assert "verified_user_action_guidance_available" not in result


def test_v1064_verified_snapshot_must_match_current_decision():
    verification = _verification()
    verification["verified_snapshot"]["priority"] = "HIGH"
    handler = _handler(
        verifier=_Verifier(verification),
        guidance_builder=_BuilderSpy(_guidance()),
        checklist_builder=_BuilderSpy(_checklist()),
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert "Проверенный ручной чек-лист" not in result["message"]


def test_v1065_malformed_guidance_suppresses_checklist_only():
    checklist = _BuilderSpy(_checklist())
    handler = _handler(
        verifier=_Verifier(_verification()),
        guidance_builder=_BuilderSpy({"error": False}),
        checklist_builder=checklist,
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert checklist.calls == []
    assert "verified_user_action_guidance_available" not in result


def test_v1066_malformed_checklist_suppresses_verified_ui():
    handler = _handler(
        verifier=_Verifier(_verification()),
        guidance_builder=_BuilderSpy(_guidance()),
        checklist_builder=_BuilderSpy({
            "error": False,
            "status": "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY",
        }),
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert "verified_user_action_guidance_available" not in result
    assert "Проверенный ручной чек-лист" not in result["message"]


def test_v1067_valid_verified_guidance_is_presented_as_manual_checklist():
    handler = _handler(
        verifier=_Verifier(_verification()),
        guidance_builder=build_product_decision_user_action_guidance,
        checklist_builder=build_product_decision_user_action_checklist,
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert result["verified_user_action_guidance_available"] is True
    assert result["decision_persistence_verification"][
        "verification_source"
    ] == "DURABLE_HISTORY_READBACK"
    assert result["user_action_guidance"]["executed"] is False
    assert result["user_action_checklist"]["execution_allowed"] is False
    assert "✅ Проверенный ручной чек-лист" in result["message"]
    assert "Продолжить наблюдение" in result["message"]
    assert "1. Сохраните текущие условия" in result["message"]
    assert "Автоматическое выполнение отключено." in result["message"]


def test_v1068_unsafe_guidance_cannot_reach_verified_ui():
    guidance = _guidance()
    guidance["automatic_execution_prohibited"] = False
    handler = _handler(
        verifier=_Verifier(_verification()),
        guidance_builder=_BuilderSpy(guidance),
        checklist_builder=_BuilderSpy(_checklist()),
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert "verified_user_action_guidance_available" not in result


def test_v1069_verifier_exception_is_contained_without_secret_leak():
    handler = _handler(
        verifier=_Verifier(
            error=OSError("secret durable path")
        ),
        guidance_builder=build_product_decision_user_action_guidance,
        checklist_builder=build_product_decision_user_action_checklist,
    )

    result = handler.handle("product_decision:hook-2")

    assert result["error"] is False
    assert "secret durable path" not in str(result)
    assert "Проверенный ручной чек-лист" not in result["message"]


def test_v1070_factory_shares_history_with_readonly_verifier(monkeypatch):
    system = {
        "core": object(),
        "storage": object(),
        "context": object(),
        "task_context": object(),
    }
    history = object()
    query = object()
    unit = object()
    captured = {}

    monkeypatch.setattr(
        telegram_factory,
        "create_telegram_core",
        lambda: system,
    )
    monkeypatch.setattr(
        telegram_factory,
        "create_current_unit_economics_query",
        lambda core_components: unit,
    )
    monkeypatch.setattr(
        telegram_factory,
        "create_product_decision_history",
        lambda: history,
    )

    def create_query(**kwargs):
        captured["query_history"] = kwargs[
            "decision_history_service"
        ]
        return query

    monkeypatch.setattr(
        telegram_factory,
        "create_product_business_decision_query",
        create_query,
    )
    monkeypatch.setattr(
        telegram_factory,
        "create_product_returns_finance_impact_query",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "AssistantTelegramMemoryService",
        lambda storage: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "AssistantMemoryCommandService",
        lambda memory: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "AssistantHistoryService",
        lambda storage: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "AssistantKeyboardService",
        lambda: object(),
    )

    class Handler:
        def __init__(self, *args, **kwargs):
            captured["handler_kwargs"] = kwargs

    monkeypatch.setattr(
        telegram_factory,
        "AssistantButtonHandlerService",
        Handler,
    )
    monkeypatch.setattr(
        telegram_factory,
        "AssistantTelegramAdapter",
        lambda *args: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "TelegramCommandService",
        lambda adapter: object(),
    )
    monkeypatch.setattr(
        telegram_factory,
        "TelegramBotService",
        lambda *args: object(),
    )

    class Runner:
        def __init__(self, bot):
            self.bot = bot

    monkeypatch.setattr(
        telegram_factory,
        "TelegramRunner",
        Runner,
    )

    runner = telegram_factory.create_telegram_assistant()

    verifier = captured["handler_kwargs"][
        "product_decision_persistence_verifier"
    ]
    assert captured["query_history"] is history
    assert verifier.history_service is history
    assert runner.product_decision_history_service is history
    assert runner.product_decision_persistence_verifier is verifier
    assert (
        captured["handler_kwargs"][
            "product_decision_user_action_guidance_builder"
        ]
        is telegram_factory.build_product_decision_user_action_guidance
    )
    assert (
        captured["handler_kwargs"][
            "product_decision_user_action_checklist_builder"
        ]
        is telegram_factory.build_product_decision_user_action_checklist
    )
