"""Regression coverage for the automatic FIFO batch rule flow (B01/B02)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_current_unit_cost_adapter import FifoCurrentUnitCostAdapter
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
from telegram_app_layer.telegram_progress_feedback import (
    MAX_TELEGRAM_TEXT_UNITS,
    progress_text,
    split_telegram_text,
)


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


def test_automatic_batch_card_is_offline_and_refresh_is_scoped_bounded_and_replay_safe(tmp_path):
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("test-owner-a", IDENTITY["store_id"]),
    )
    try:
        now = lambda: datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
        repository = FifoCostRepository(db_path=tmp_path / "batch-card.sqlite", now_provider=now)
        history = FifoCostHistoryService(repository)
        transitions = FifoCostTransitionService(repository, now_provider=now)

        class _FakeSource:
            def __init__(self):
                self.calls = []
                self.results = [
                    SimpleNamespace(
                        read_only=True, status="PARTIAL", actual_http_attempts=10,
                        issue_codes=("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED",),
                        continuation_token="a" * 32, orders_observed=10,
                        supplies_observed=12, pagination_complete=False,
                        details_complete=False,
                    ),
                    SimpleNamespace(
                        read_only=True, status="PARTIAL", actual_http_attempts=4,
                        issue_codes=("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED",),
                        continuation_token=None, orders_observed=20,
                        supplies_observed=25, pagination_complete=True,
                        details_complete=True,
                    ),
                ]

            def collect_supplies(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return self.results[len(self.calls) - 1]

        source = _FakeSource()
        rule_service = FifoCostBatchRuleService(repository, now_provider=now)
        telegram_rules = TelegramFifoCostBatchRuleService(
            rule_service, repository, supply_source_service=source,
        )
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
            batch_rule_telegram_service=telegram_rules,
        )
        runtime.start_new_case(101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED")

        class _LegacyCost:
            def get_current_cost_date(self):
                return "2026-11-14"

            def get_cost(self, product_id):
                return (
                    str(product_id), IDENTITY["sku"], IDENTITY["offer_id"],
                    "21.00", "RUB", "2026-11-01",
                )

        current_cost_adapter = FifoCurrentUnitCostAdapter(
            _LegacyCost(), history,
        )
        product = {
            "product_id": "101", "offer_id": IDENTITY["offer_id"],
            "sku": IDENTITY["sku"],
        }
        before_rule_cost = current_cost_adapter.resolve_current_cost(
            product, store_id=IDENTITY["store_id"],
        )
        assert before_rule_cost["cost_per_unit_rub"] == "21.00"
        assert before_rule_cost["cost_method"] == "LEGACY_EFFECTIVE_DATED"
        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            response = _confirm_text(runtime, value)
        first_day = runtime.handle_text(101, "не знаю")
        include = next(
            button["callback"] for button in first_day["keyboard"]["buttons"]
            if button["text"] == "Да, все отправки дня"
        )
        preview = runtime.handle_callback(101, include)
        confirm = next(
            button["callback"] for button in preview["keyboard"]["buttons"]
            if button["text"] == "Подтвердить правило"
        )
        rule_saved = runtime.handle_callback(101, confirm)
        show_case = next(
            button["callback"] for button in rule_saved["keyboard"]["buttons"]
            if button["text"] == "К делу"
        )
        card = runtime.handle_callback(101, show_case)

        labels = {button["text"] for button in card["keyboard"]["buttons"]}
        assert {"Обновить поставки", "Проверить найденные", "Изменить правило", "Контрольное количество"} <= labels
        assert any("Проверить готовность" in label for label in labels)
        assert any("Посмотреть пересчёт" in label for label in labels)
        assert "редакция 1" in card["message"].lower()
        assert "первая редакция подтверждена владельцем" in card["message"].lower()
        assert "ставка правила 14.65 ₽/шт." in card["message"].lower()
        assert "не текущая себестоимость fifo" in card["message"].lower()
        assert "время среза ozon не подтверждены" in card["message"].lower()
        assert not source.calls  # Opening the card performs no Ozon request.
        assert "не обращается к ozon" in card["message"].lower()

        edit_rule = next(
            button["callback"] for button in card["keyboard"]["buttons"]
            if button["text"] == "Изменить правило"
        )
        guidance = runtime.handle_callback(101, edit_rule)
        assert "себестоимость fifo" in guidance["message"].lower()
        assert "новая себестоимость" in guidance["message"].lower()
        assert "предпросмотра" in guidance["message"].lower()
        assert "исправления/пересчёта" in guidance["message"].lower()
        assert not source.calls

        refresh = next(
            button["callback"] for button in card["keyboard"]["buttons"]
            if button["text"] == "Обновить поставки"
        )
        competing_stale = runtime._issue_ticket(
            "101", runtime._sessions["101"], "batch_refresh",
        )
        checked = runtime.handle_callback(101, next(
            button["callback"] for button in card["keyboard"]["buttons"]
            if button["text"] == "Проверить найденные"
        ))
        assert "сначала нажмите" in checked["message"].lower()
        assert not source.calls

        first_scan = runtime.handle_callback(101, refresh)
        assert len(source.calls) == 1
        args, kwargs = source.calls[0]
        assert args[0].owner_id == "test-owner-a"
        assert args[0].store_id == IDENTITY["store_id"]
        assert args[0].sku == IDENTITY["sku"]
        assert args[1] == runtime._sessions["101"]["case_id"]
        assert args[2:] == (7, 1)
        assert kwargs["continuation_token"] is None
        assert "не полностью" in first_scan["message"].lower()
        assert "fifo_batch" not in first_scan["message"].lower()
        assert "заявок в ответах: 10" in first_scan["message"].lower()
        batch_card = runtime._show_summary("101")
        assert "время чтения ботом" in batch_card["message"].lower()
        assert "время среза ozon" in batch_card["message"].lower()
        assert "покрытие текущего запроса: список — неполная" in batch_card["message"].lower()
        assert runtime.handle_callback(101, refresh) == first_scan
        assert len(source.calls) == 1
        assert runtime.handle_callback(101, competing_stale)["error"] is True
        assert len(source.calls) == 1
        other_tenant = set_current_tenant_user_id(
            make_store_tenant_scope("test-owner-a", "test-store-b"),
        )
        try:
            foreign_replay = runtime.handle_callback(101, refresh)
            assert foreign_replay["error"] is True
            assert "10" not in foreign_replay["message"]
        finally:
            reset_current_tenant_user_id(other_tenant)

        continue_scan = next(
            button["callback"] for button in first_scan["keyboard"]["buttons"]
            if button["text"] == "Продолжить поиск"
        )
        second_scan = runtime.handle_callback(101, continue_scan)
        assert len(source.calls) == 2
        assert source.calls[1][1]["continuation_token"] == "a" * 32
        assert "полнота исторического охвата" in second_scan["message"].lower()
        assert not any("id=" in line.lower() for line in second_scan["message"].splitlines())
        after_rule_and_scan_cost = current_cost_adapter.resolve_current_cost(
            product, store_id=IDENTITY["store_id"],
        )
        assert after_rule_and_scan_cost["cost_per_unit_rub"] == "21.00"
        assert after_rule_and_scan_cost["cost_method"] == "LEGACY_EFFECTIVE_DATED"
        assert after_rule_and_scan_cost["cost_revision"] == before_rule_cost["cost_revision"]
        assert after_rule_and_scan_cost["cost_basis"][
            "factual_period_profit_eligible"
        ] is False
        found = runtime.handle_callback(101, next(
            button["callback"] for button in runtime._show_summary("101")["keyboard"]["buttons"]
            if button["text"] == "Проверить найденные"
        ))
        assert "25" in found["message"]
        assert len(source.calls) == 2  # Read-only found-check does not call Ozon.

        refresh_again = next(
            button["callback"] for button in runtime._show_summary("101")["keyboard"]["buttons"]
            if button["text"] == "Обновить поставки"
        )
        failed_refresh = runtime.handle_callback(101, refresh_again)
        assert "предыдущий результат" in failed_refresh["message"].lower()
        assert runtime._sessions["101"]["batch_last_scan"]["supplies"] == 25
        assert runtime._sessions["101"]["batch_refresh_error"] is True
        card_after_failure = runtime._show_summary("101")
        assert "предыдущий результат чтения" in card_after_failure["message"].lower()
    finally:
        reset_current_tenant_user_id(tenant)


def test_fifo_supply_refresh_uses_named_progress_and_safe_unicode_message_splitting():
    assert progress_text("fifo_transition:batch_refresh:0123456789ab") == "⏳ Проверяю поставки Ozon…"
    value = "📦 Проверка поставок 🧾 " * 500
    chunks = split_telegram_text(value)
    assert len(chunks) > 1
    assert "".join(chunks) == value
    for chunk in chunks:
        units = sum(2 if ord(character) > 0xFFFF else 1 for character in chunk)
        assert units <= MAX_TELEGRAM_TEXT_UNITS
