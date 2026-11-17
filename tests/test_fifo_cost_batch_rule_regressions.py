"""Regression coverage for the automatic FIFO batch rule flow (B01/B02)."""

from datetime import datetime, timezone

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_transition_contracts import ScopeIdentity, SupplyTotalMode
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)
from services.telegram_fifo_cost_batch_rule_service import (
    TelegramFifoCostBatchRuleService,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "test-store-a",
    "product_id": "101",
    "offer_id": "test-a",
    "sku": "1000000001",
}


def _confirm_text(runtime, text):
    preview = runtime.handle_text(101, text)
    assert preview["error"] is False, preview
    return runtime.handle_callback(
        101, preview["keyboard"]["buttons"][0]["callback"],
    )


def test_unknown_total_opens_auto_rule_preview_without_owner_consent(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "batch-rule.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)
        rule_service = FifoCostBatchRuleService(repository, now_provider=now)
        telegram_rules = TelegramFifoCostBatchRuleService(rule_service, repository)
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=telegram_rules,
        )
        started = runtime.start_new_case(
            101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED",
        )
        assert "старую итоговую себестоимость" in started["message"].lower()

        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            response = _confirm_text(runtime, value)
            assert response["error"] is False, response
        assert "как учитывать последующие поставки" in response["message"].lower()

        # The shortcut enters the automatic path but does not confirm either
        # the start-day policy or the rule itself.
        preview = runtime.handle_text(101, "не знаю")
        assert preview["error"] is False, preview
        assert "все отправки этого sku" in preview["message"].lower()
        saved = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert saved["case"]["declared_shipped_units"] is None
        assert saved["case_revision"] == 6
        assert saved["state"] == "AWAITING_EVIDENCE"
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False

        include_day = next(
            button["callback"] for button in preview["keyboard"]["buttons"]
            if button["text"] == "Да, все отправки дня"
        )
        preview = runtime.handle_callback(101, include_day)
        assert "проверьте границу партии" in preview["message"].lower()
        assert any(
            "подтверд" in button["text"].lower()
            for button in preview["keyboard"]["buttons"]
        )
        confirm = next(
            button["callback"] for button in preview["keyboard"]["buttons"]
            if button["text"] == "Подтвердить правило"
        )
        saved_rule = runtime.handle_callback(101, confirm)
        assert saved_rule["error"] is False, saved_rule
        assert "fifo и расчёт прибыли не изменились" in saved_rule["message"].lower()
        current = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert current["case"]["supply_total_mode"] == SupplyTotalMode.AUTO_FROM_SUPPLIES.value
        assert current["case_revision"] == 7
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
        tenant_scope = repository._tenant_scope(IDENTITY["store_id"])
        scope = ScopeIdentity(
            owner_id="test-owner-a", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )
        connection = repository.get_connection()
        try:
            rules = FifoCostBatchSupplyStore.read_rule_revisions(
                connection, scope=scope, case_id=current["case_id"],
                tenant_fingerprint=tenant_scope["tenant_fingerprint"],
            )
        finally:
            connection.close()
        assert len(rules) == 1
        assert rules[0]["start_local_date"] == "2026-11-05"
        assert runtime.handle_callback(101, confirm) == saved_rule
    finally:
        reset_current_tenant_user_id(tenant)


def test_manual_quantity_is_a_dated_control_and_does_not_replace_case_total(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "control.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)
        telegram_rules = TelegramFifoCostBatchRuleService(
            FifoCostBatchRuleService(repository, now_provider=now), repository,
        )
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=telegram_rules,
        )
        response = runtime.start_new_case(
            101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED",
        )
        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            response = _confirm_text(runtime, value)
        control_choice = next(
            button["callback"] for button in response["keyboard"]["buttons"]
            if button["text"] == "Добавить контрольное количество"
        )
        response = runtime.handle_callback(101, control_choice)
        accepted_kind = next(
            button["callback"] for button in response["keyboard"]["buttons"]
            if button["text"] == "Принято на складе"
        )
        response = runtime.handle_callback(101, accepted_kind)
        for value in ("100", "05.11.2026", "10.11.2026"):
            response = runtime.handle_text(101, value)
        assert "не подтверждённое ozon количество" in response["message"].lower()
        saved = runtime.handle_callback(101, response["keyboard"]["buttons"][0]["callback"])
        assert saved["error"] is False, saved
        assert "не заменяет общий итог партии" in saved["message"].lower()

        case = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert case["case"]["declared_shipped_units"] is None
        assert case["case"]["supply_total_mode"] == SupplyTotalMode.LEGACY_OWNER_TOTAL.value
        assert case["case_revision"] == 6
        scope = ScopeIdentity(
            owner_id="test-owner-a", store_id=IDENTITY["store_id"],
            product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )
        tenant_scope = repository._tenant_scope(IDENTITY["store_id"])
        connection = repository.get_connection()
        try:
            controls = FifoCostBatchSupplyStore.read_total_controls(
                connection, scope=scope, case_id=case["case_id"],
                tenant_fingerprint=tenant_scope["tenant_fingerprint"],
            )
        finally:
            connection.close()
        assert len(controls) == 1
        assert controls[0]["total_units"] == 100
        assert controls[0]["window_from"] == "2026-11-05"
        assert controls[0]["window_through"] == "2026-11-10"
        assert controls[0]["control_kind"] == "ACCEPTED_UNITS"
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)


def test_existing_unknown_quantity_draft_resumes_at_mode_choice_without_reset(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "resume.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)
        legacy_runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
        )
        legacy_runtime.start_new_case(
            101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED",
        )
        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            _confirm_text(legacy_runtime, value)
        before = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert before["case_revision"] == 6
        assert before["case"]["declared_shipped_units"] is None

        telegram_rules = TelegramFifoCostBatchRuleService(
            FifoCostBatchRuleService(repository, now_provider=now), repository,
        )
        resumed_runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=telegram_rules,
        )
        prompt = resumed_runtime.resume_case(
            101, identity=IDENTITY, display_name="Synthetic item",
            case_id=before["case_id"], expected_case_revision=before["case_revision"],
        )
        assert "как учитывать последующие поставки" in prompt["message"].lower()
        after = transitions.get_case(case_id=before["case_id"], **IDENTITY)
        assert after["case_revision"] == before["case_revision"]
        for field, value in {
            "old_unit_cost_rub": "21.00",
            "new_unit_cost_rub": "14.65",
            "dispatch_date": "2026-11-05",
            "owner_old_home_units": 0,
            "owner_old_transit_units": 0,
            "declared_shipped_units": None,
        }.items():
            assert after["case"][field] == value
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)


def test_existing_legacy_total_is_preserved_when_resuming_at_mode_choice(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "legacy-total.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)
        legacy_runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
        )
        legacy_runtime.start_new_case(
            101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED",
        )
        for value in ("21", "14.65", "05.11.2026", "0", "0", "6982"):
            _confirm_text(legacy_runtime, value)
        before = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert before["case"]["declared_shipped_units"] == 6982

        telegram_rules = TelegramFifoCostBatchRuleService(
            FifoCostBatchRuleService(repository, now_provider=now), repository,
        )
        resumed_runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=telegram_rules,
        )
        prompt = resumed_runtime.resume_case(
            101, identity=IDENTITY, display_name="Synthetic item",
            case_id=before["case_id"], expected_case_revision=before["case_revision"],
        )
        assert "как учитывать последующие поставки" in prompt["message"].lower()
        auto = next(
            button["callback"] for button in prompt["keyboard"]["buttons"]
            if button["text"] == "Считать по поставкам Ozon"
        )
        policy = resumed_runtime.handle_callback(101, auto)
        include = next(
            button["callback"] for button in policy["keyboard"]["buttons"]
            if button["text"] == "Да, все отправки дня"
        )
        preview = resumed_runtime.handle_callback(101, include)
        assert "legacy-контролем без даты" in preview["message"].lower()
        unchanged = transitions.get_case(case_id=before["case_id"], **IDENTITY)
        assert unchanged["case_revision"] == before["case_revision"]
        assert unchanged["case"]["declared_shipped_units"] == 6982
        assert unchanged["case"]["supply_total_mode"] == SupplyTotalMode.LEGACY_OWNER_TOTAL.value
    finally:
        reset_current_tenant_user_id(tenant)


def test_start_day_no_or_unknown_cannot_reuse_all_day_confirmation_button(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "day-policy.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)
        rules = FifoCostBatchRuleService(repository, now_provider=now)
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=TelegramFifoCostBatchRuleService(rules, repository),
        )
        runtime.start_new_case(101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED")
        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            response = _confirm_text(runtime, value)
        auto = next(
            button["callback"] for button in response["keyboard"]["buttons"]
            if button["text"] == "Считать по поставкам Ozon"
        )
        policy = runtime.handle_callback(101, auto)
        stale_all_day = next(
            button["callback"] for button in policy["keyboard"]["buttons"]
            if button["text"] == "Да, все отправки дня"
        )
        select = next(
            button["callback"] for button in policy["keyboard"]["buttons"]
            if button["text"].startswith("Нет / не уверен")
        )
        unresolved = runtime.handle_callback(101, select)
        assert "правило не сохранено" in unresolved["message"].lower()
        assert runtime.handle_callback(101, stale_all_day)["error"] is True
        saved = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert saved["case"]["supply_total_mode"] == SupplyTotalMode.LEGACY_OWNER_TOTAL.value
        assert saved["case_revision"] == 6
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)
