from datetime import date
from threading import Event, Thread

from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.analytics_export_service import AnalyticsExportService
from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_unit_price_calculator_runtime_service import TelegramUnitPriceCalculatorRuntimeService
from services.telegram_unit_price_tariff_profile_runtime_service import TelegramUnitPriceTariffProfileRuntimeService
from services.unit_price_scenario_service import UnitPriceScenarioService
from services.unit_price_tariff_resolver import UnitPriceTariffResolver


class _Products:
    def load_products(self):
        return [{"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627", "name": "Крючок"}]


class _Source:
    product_service = _Products()

    def __init__(self, scheme="FBO"):
        self.scheme = scheme

    def load_snapshot(self, sku, user_id, force_refresh=False):
        return {
            "error": False,
            "snapshot_id": "snap-1",
            "identity": {
                "user_id": user_id, "store_id": "store-1",
                "tenant_scope": f"{user_id}::ozon::store-1",
                "product_id": "p1", "offer_id": "hook-2", "sku": sku,
            },
            "product": {"name": "Крючок", "scheme": self.scheme},
            "suggested_inputs": {
                "price": 100, "cost": 20, "commission_rate": 14,
                "logistics_per_unit": 10, "last_mile_per_unit": 5,
                "acquiring_per_unit": 2, "advertising_rate": 5,
                "discount_points_rate": 0, "tax_mode": "USN_INCOME",
                "tax_rate": 6, "minimum_tax_rate": 1,
            },
            "input_provenance": {"price": "ozon_current_seller_price", "commission_rate": "ozon_current_fbo_rate"},
            "source_periods": {"seller_price_as_of": "2026-10-27T10:00:00+03:00"},
            "source_completeness": {},
        }


def _flow(tmp_path, scheme="FBO"):
    keyboard = AssistantKeyboardService()
    calculator = TelegramUnitPriceCalculatorRuntimeService(
        source=_Source(scheme), scenario_service=UnitPriceScenarioService(TaxService()),
        keyboard_service=keyboard,
    )
    repository = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    tariff = TelegramUnitPriceTariffProfileRuntimeService(repository, calculator, keyboard)
    tariff.analytics_export_service = AnalyticsExportService()
    calculator.tariff_profile_runtime_service = tariff
    handler = AssistantButtonHandlerService(
        assistant=object(), keyboard_service=keyboard,
        unit_price_calculator_runtime_service=calculator,
        unit_price_tariff_profile_runtime_service=tariff,
    )
    adapter = AssistantTelegramAdapter(object(), keyboard, handler)
    return adapter, calculator, tariff, repository


def _scenario(calculator, store="store-1"):
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", store))
    try:
        calculator.begin_catalog_selection("user-1")
        callback = calculator.build_catalog_product_callback("user-1", "hook-2")
        return calculator.handle_callback(callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)


def _button(result, label):
    return next(item for item in result["keyboard"]["buttons"] if item["text"] == label)


def _public_button(adapter, callback, store="store-1"):
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", store))
    try:
        return adapter.handle_button(callback, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)


def _public_text(adapter, text, store="store-1"):
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", store))
    try:
        return adapter.handle_text(text, user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)


def test_public_telegram_flow_previews_and_persists_manual_ranges_idempotently(tmp_path):
    adapter, calculator, tariff, repository = _flow(tmp_path)
    calculator.tariff_profile_runtime_service = tariff
    scenario = _scenario(calculator)
    start_button = _button(scenario, "Указать тариф комиссии")
    assert len(start_button["callback"]) <= 64
    prompt = _public_button(adapter, start_button["callback"])
    preview = _public_text(
        adapter,
        "Действует с: 2026-10-01\n0,01–99,99 ₽ = 12%\n100–199,99 ₽ = 14%",
    )
    assert prompt["status"] == "UNIT_PRICE_TARIFF_INPUT"
    assert preview["status"] == "UNIT_PRICE_TARIFF_PREVIEW"
    assert "вручную введено и подтверждается продавцом" in preview["message"]
    save = _button(preview, "✅ Сохранить для SKU")
    result = _public_button(adapter, save["callback"])
    replay = _public_button(adapter, save["callback"])

    assert result["error"] is False
    assert "Тариф сохранён" in result["message"]
    assert result["price_scenario"]["scenario_id"] == scenario["price_scenario"]["scenario_id"]
    assert result["price_scenario"]["inputs"]["price"]["value"] == 100.0
    assert result["price_scenario"]["inputs"]["cost"]["value"] == 20.0
    assert result["price_scenario"]["tariff_resolution"]["available"] is True
    assert result["price_scenario"]["tariff_resolution"]["commission_rate"] == "14"
    assert replay["error"] is True
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        listed = repository.list_tariff_profiles(identity={"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627"})
        reopened = PlanningWorkspaceRepository(db_path=repository.db_path).get_tariff_profile(listed["items"][0]["profile_id"])
    finally:
        reset_current_tenant_user_id(token)
    assert len(listed["items"]) == 1
    assert reopened["profile"]["bands"][1]["commission_rate"] == "14"


def test_public_edit_rotates_preview_ticket_and_cancel_never_persists(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    prompt = _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    preview = _public_text(adapter, "100=14%")
    old_save = _button(preview, "✅ Сохранить для SKU")["callback"]
    edit = _public_button(adapter, _button(preview, "Изменить")["callback"])
    revised = _public_text(adapter, "100=12%")
    assert edit["status"] == "UNIT_PRICE_TARIFF_INPUT"
    assert _public_button(adapter, old_save)["error"] is True
    cancel = _public_button(adapter, _button(revised, "Отмена")["callback"])
    assert cancel["error"] is False
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        assert repository.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_public_session_only_profile_is_scoped_to_current_scenario_and_not_persisted(tmp_path):
    adapter, calculator, tariff, repository = _flow(tmp_path)
    calculator.tariff_profile_runtime_service = tariff
    scenario = _scenario(calculator)
    start = _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    preview = _public_text(adapter, "100=14%")
    result = _public_button(adapter, _button(preview, "Только для этой сессии")["callback"])

    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        profile = tariff.get_session_profile(scenario["price_scenario"]["scenario_id"], user_id="user-1")
        persisted = repository.list_tariff_profiles()
    finally:
        reset_current_tenant_user_id(token)
    assert result["error"] is False
    assert profile["bands"][0]["commission_rate"] == "14"
    assert profile["origin"] == "MANUAL_SELLER_ASSUMPTION"
    assert persisted["items"] == []
    assert result["price_scenario"]["tariff_resolution"]["available"] is True
    assert result["price_scenario"]["tariff_resolution"]["commission_rate"] == "14"
    resolved = UnitPriceTariffResolver().resolve(
        seller_price_cents=10000,
        identity={
            "owner_id": "user-1", "store_id": "store-1",
            "product_id": "p1", "offer_id": "hook-2", "sku": "3921245627",
        },
        sale_schema="FBO", effective_date=date.today().isoformat(), profiles=[profile],
    )
    assert resolved["error"] is False
    assert resolved["available"] is True
    assert resolved["commission_rate"] == "14"


def test_public_stale_version_and_replayed_old_ticket_cannot_save(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    start = _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    preview = _public_text(adapter, "100=14%")
    save_callback = _button(preview, "✅ Сохранить для SKU")["callback"]
    scenario_id = scenario["price_scenario"]["scenario_id"]
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        calculator.handle_callback(f"upc:z:{scenario_id}:1", user_id="user-1")
    finally:
        reset_current_tenant_user_id(token)
    stale = _public_button(adapter, save_callback)
    assert stale["error"] is True
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        assert repository.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_public_old_draft_button_cannot_confirm_replacement_draft(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    start_callback = _button(scenario, "Указать тариф комиссии")["callback"]
    first = _public_button(adapter, start_callback)
    first_preview = _public_text(adapter, "100=14%")
    old_save = _button(first_preview, "✅ Сохранить для SKU")["callback"]
    second = _public_button(adapter, start_callback)
    second_preview = _public_text(adapter, "100=12%")
    stale = _public_button(adapter, old_save)
    assert second["error"] is False
    assert stale["error"] is True
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        assert repository.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)


def test_public_manual_tariff_is_fbo_only(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path, scheme="FBS")
    scenario = _scenario(calculator)
    assert not any(item["text"] == "Указать тариф комиссии" for item in scenario["keyboard"]["buttons"])
    callback = f"upt:start:{scenario['price_scenario']['scenario_id']}:1"
    result = _public_button(adapter, callback)
    assert result["error"] is True
    assert result["code"] == "UNIT_PRICE_TARIFF_FBO_ONLY"


def test_public_invalid_input_keeps_draft_without_writing(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    invalid = _public_text(adapter, "цена 100, комиссия высокая")
    assert invalid["status"] == "UNIT_PRICE_TARIFF_INPUT"
    assert "Не удалось разобрать" in invalid["message"]
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        assert repository.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)
    assert _public_text(adapter, "100=14%")["status"] == "UNIT_PRICE_TARIFF_PREVIEW"


def test_public_second_confirmation_updates_same_profile_revision(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    first_prompt = _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    first_preview = _public_text(adapter, "100=14%")
    first_saved = _public_button(adapter, _button(first_preview, "✅ Сохранить для SKU")["callback"])
    second_prompt = _public_button(adapter, _button(first_saved, "Указать тариф комиссии")["callback"])
    second_preview = _public_text(adapter, "100=12%")
    _public_button(adapter, _button(second_preview, "✅ Сохранить для SKU")["callback"])
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        listed = repository.list_tariff_profiles(identity={"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627"})
        profile = repository.get_tariff_profile(listed["items"][0]["profile_id"])
    finally:
        reset_current_tenant_user_id(token)
    assert first_prompt["status"] == second_prompt["status"] == "UNIT_PRICE_TARIFF_INPUT"
    assert len(listed["items"]) == 1
    assert profile["revision"] == 2
    assert profile["profile"]["bands"][0]["commission_rate"] == "12"


def test_tariff_profile_screen_and_files_use_same_frozen_scenario_snapshot(tmp_path):
    adapter, calculator, tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    start = _public_button(
        adapter, _button(scenario, "Указать тариф комиссии")["callback"],
    )
    preview = _public_text(
        adapter, "Действует с: 2026-10-01\n0,01–99,99 ₽ = 12%\n100–199,99 ₽ = 14%",
    )
    saved = _public_button(adapter, _button(preview, "✅ Сохранить для SKU")["callback"])
    scenario_id = saved["price_scenario"]["scenario_id"]
    version = saved["price_scenario"]["scenario_version"]
    assumptions = _public_button(adapter, f"upc:a:{scenario_id}:{version}")
    profile_button = _button(assumptions, "Профиль комиссии")
    assert len(profile_button["callback"].encode("utf-8")) <= 64

    screen = _public_button(adapter, profile_button["callback"])
    assert screen["status"] == "UNIT_PRICE_TARIFF_SNAPSHOT_READY"
    assert "99.99 ₽" in screen["message"]
    assert "100.00–199.99 ₽: 14%" in screen["message"]
    assert "Непокрытые диапазоны остаются неизвестными" in screen["message"]
    json_callback = _button(screen, "Скачать JSON")["callback"]
    csv_callback = _button(screen, "Скачать CSV")["callback"]
    assert len(json_callback.encode("utf-8")) <= 64
    json_result = _public_button(adapter, json_callback)
    csv_result = _public_button(adapter, csv_callback)
    assert json_result["document_kind"] == csv_result["document_kind"] == "analytics_export"
    assert json_result["export_kind"] == csv_result["export_kind"] == "unit_price_tariff_profile"
    assert b"internal-profile" not in json_result["file_content"]
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        listed = repository.list_tariff_profiles(
            identity={"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627"},
            owner_id="user-1", store_id="store-1",
        )
    finally:
        reset_current_tenant_user_id(token)
    assert listed["error"] is False
    assert listed["items"]


def test_parallel_tariff_save_callback_has_one_writer_and_keeps_retry_safe(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    preview = _public_text(adapter, "100=14%")
    save_callback = _button(preview, "✅ Сохранить для SKU")["callback"]
    original_create = repository.create_tariff_profile
    entered, release = Event(), Event()
    call_count = []

    def blocked_create(*args, **kwargs):
        call_count.append(1)
        entered.set()
        assert release.wait(5)
        return original_create(*args, **kwargs)

    repository.create_tariff_profile = blocked_create
    first_result = {}

    def save_in_worker():
        token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
        try:
            first_result["value"] = adapter.handle_button(save_callback, user_id="user-1")
        finally:
            reset_current_tenant_user_id(token)

    worker = Thread(target=save_in_worker)
    worker.start()
    try:
        assert entered.wait(5)
        replay = _public_button(adapter, save_callback)
        assert replay["error"] is True
    finally:
        release.set()
        worker.join(5)

    assert not worker.is_alive()
    assert first_result["value"]["error"] is False
    assert call_count == [1]
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-1"))
    try:
        listed = repository.list_tariff_profiles(
            identity={"product_id": "p1", "offer_id": "hook-2", "sku": "3921245627"},
            owner_id="user-1", store_id="store-1",
        )
    finally:
        reset_current_tenant_user_id(token)
    assert listed["error"] is False
    assert len(listed["items"]) == 1


def test_public_callback_from_previous_store_cannot_save(tmp_path):
    adapter, calculator, _tariff, repository = _flow(tmp_path)
    scenario = _scenario(calculator)
    start = _public_button(adapter, _button(scenario, "Указать тариф комиссии")["callback"])
    preview = _public_text(adapter, "100=14%")
    old_save = _button(preview, "✅ Сохранить для SKU")["callback"]
    stale = _public_button(adapter, old_save, store="store-2")
    assert start["status"] == "UNIT_PRICE_TARIFF_INPUT"
    assert stale["error"] is True
    token = set_current_tenant_user_id(make_store_tenant_scope("user-1", "store-2"))
    try:
        assert repository.list_tariff_profiles()["items"] == []
    finally:
        reset_current_tenant_user_id(token)
