from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.period_profit_sku_runtime_service import PeriodProfitSkuRuntimeService
from services.tenant_context import get_current_tenant_user_id
from telegram_app_layer.assistant_telegram_adapter import AssistantTelegramAdapter
from telegram_app_layer.telegram_bot_service import TelegramBotService


def _row(sku, product_id="p1", catalog_sku=None, revenue=100, net=80, cost=20, units=2):
    return {
        "sku": sku,
        "catalog_sku": catalog_sku,
        "product_id": product_id,
        "units_sold": units,
        "revenue": revenue,
        "net_accrual": net,
        "commission": 10,
        "logistics": 5,
        "acquiring": 1,
        "other_fees": 4,
        "product_cost": cost,
        "tax": 6,
        "profit": net - cost - 6,
    }


def _summary(rows, date_from="2026-09-01", date_to="2026-09-07"):
    return {
        "products": rows,
        "date_from": date_from,
        "date_to": date_to,
        "tax_mode": "USN_INCOME",
        "tax_rate_percent": 6.0,
        "minimum_tax_rate_percent": 1.0,
    }


class Query:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def product_provider(self):
        return [("p1", "hook-2", "3921245627"), ("p2", "other", "999")]

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_selected_sku_aggregates_proven_legacy_and_current_identity():
    current = _row("3921245627", revenue=100, net=80, cost=20, units=2)
    legacy = _row("3398133813", catalog_sku="3921245627", revenue=50, net=40, cost=10, units=1)
    other = _row("999", product_id="p2", revenue=1000, net=900, cost=100)
    query = Query({
        "error": False,
        "summary": _summary([current, legacy, other]),
        "previous_summary": _summary([], "2026-08-25", "2026-08-31"),
    })
    service = PeriodProfitSkuRuntimeService(query)

    result = service.handle_callback("period_profit_sku:3921245627:7D")

    assert result["error"] is False
    assert result["summary"]["revenue"] == 150.0
    assert result["summary"]["net_accrual"] == 120.0
    assert result["summary"]["product_cost"] == 30.0
    assert result["summary"]["tax"] == 9.0
    assert result["summary"]["profit"] == 81.0
    assert result["summary"]["units_sold"] == 3
    assert result["account_level_expenses_included"] is False
    assert result["return_cogs_included"] is False
    assert query.calls == [{"period_code": "7D", "compare_previous": True, "today": None}]


def test_unknown_or_forged_sku_fails_before_finance_query():
    query = Query({"error": False})
    result = PeriodProfitSkuRuntimeService(query).handle_callback(
        "period_profit_sku:forged:7D"
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SKU_NOT_FOUND"
    assert query.calls == []


def test_unknown_money_is_not_normalized_to_zero():
    bad = _row("3921245627")
    bad["net_accrual"] = None
    query = Query({"error": False, "summary": _summary([bad]), "previous_summary": None})
    result = PeriodProfitSkuRuntimeService(query).handle_callback(
        "period_profit_sku:3921245627:7D"
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SKU_AMOUNT_INVALID"


def test_conflicting_product_identity_fails_closed():
    conflict = _row("3921245627", product_id="different")
    query = Query({"error": False, "summary": _summary([conflict]), "previous_summary": None})
    result = PeriodProfitSkuRuntimeService(query).handle_callback(
        "period_profit_sku:3921245627:7D"
    )
    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_SKU_IDENTITY_CONFLICT"


def test_production_button_wiring_opens_sku_and_period_menus():
    query = Query({"error": False})
    runtime = PeriodProfitSkuRuntimeService(query)
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=object(),
        period_profit_sku_runtime_service=runtime,
    )
    sku_menu = handler.handle("period_profit_sku", "seller-a")
    callbacks = [button["callback"] for button in sku_menu["keyboard"]["buttons"]]
    assert "period_profit_sku:3921245627" in callbacks
    period_menu = handler.handle("period_profit_sku:3921245627", "seller-a")
    assert period_menu["keyboard"]["buttons"][1]["callback"] == (
        "period_profit_sku:3921245627:7D"
    )


def test_production_factory_exposes_sku_runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    from telegram_assistant_factory import create_telegram_assistant
    runner = create_telegram_assistant()
    assert isinstance(runner.period_profit_sku_runtime_service, PeriodProfitSkuRuntimeService)


def test_production_telegram_callback_keeps_tenant_context_for_sku_query():
    class TenantQuery(Query):
        def query(self, **kwargs):
            assert get_current_tenant_user_id() == "seller-a"
            return super().query(**kwargs)

    class Profiles:
        def create_user(self, user_id):
            return {"error": False, "user": {"user_id": str(user_id)}}

    current = _row("3921245627")
    query = TenantQuery({
        "error": False,
        "summary": _summary([current]),
        "previous_summary": None,
    })
    handler = AssistantButtonHandlerService(
        object(),
        keyboard_service=AssistantKeyboardService(),
        period_profit_runtime_service=object(),
        period_profit_sku_runtime_service=PeriodProfitSkuRuntimeService(query),
    )
    adapter = AssistantTelegramAdapter(
        object(), AssistantKeyboardService(), handler, Profiles()
    )
    result = TelegramBotService(adapter).on_callback(
        "seller-a", "period_profit_sku:3921245627:7D"
    )
    assert result["error"] is False
    assert get_current_tenant_user_id() is None


def test_identity_candidates_are_presented_as_explicit_confirmation_buttons():
    query = Query({
        "error": True,
        "code": "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_CONFIRMATION_REQUIRED",
        "identity_candidates": [
            {"finance_sku": "111", "historical_offer_id": "old-white"},
            {"finance_sku": "222", "historical_offer_id": "old-gray"},
        ],
    })
    runtime = PeriodProfitSkuRuntimeService(query)

    result = runtime.handle_callback("period_profit_sku:3921245627:7D")

    assert result["error"] is False
    assert result["status"] == (
        "PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_REQUIRED"
    )
    assert [button["callback"] for button in result["keyboard"]["buttons"]] == [
        "period_profit_sku:3921245627:7D:map:111",
        "period_profit_sku:3921245627:7D:map:222",
    ]


def test_confirmed_candidate_is_reverified_saved_and_calculated():
    ready = {
        "error": False,
        "summary": _summary([_row("111", catalog_sku="3921245627")]),
        "previous_summary": None,
    }

    class ConfirmingQuery(Query):
        def __init__(self):
            super().__init__(None)
            self.confirmed = False

        def query(self, **kwargs):
            self.calls.append(kwargs)
            if self.confirmed:
                return ready
            return {
                "error": True,
                "code": "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_CONFIRMATION_REQUIRED",
                "identity_candidates": [{
                    "finance_sku": "111",
                    "historical_offer_id": "old-white",
                }],
            }

    class Repository:
        def __init__(self, query):
            self.query = query
            self.calls = []

        def record_mapping(self, **kwargs):
            self.calls.append(kwargs)
            self.query.confirmed = True
            return {"error": False, "status": "RECORDED"}

    query = ConfirmingQuery()
    repository = Repository(query)
    runtime = PeriodProfitSkuRuntimeService(
        query,
        identity_repository=repository,
    )

    pending = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:map:111"
    )
    result = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:map:111:confirm"
    )

    assert pending["status"] == (
        "PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_PENDING"
    )
    assert result["error"] is False
    assert result["status"] == "PERIOD_PROFIT_SKU_READY"
    assert result["keyboard"]["buttons"] == [{
        "text": "↩️ Отменить связь SKU",
        "callback": "period_profit_sku:3921245627:7D:unmap:111",
    }]
    assert repository.calls == [{
        "finance_sku": "111",
        "current_product_id": "p1",
        "current_sku": "3921245627",
        "current_offer_id": "hook-2",
        "source": "SELLER_CONFIRMED_TELEGRAM_BUTTON",
    }]
    assert len(query.calls) == 2


def test_confirmed_mapping_can_be_revoked_from_visible_result_button():
    query = Query({
        "error": False,
        "summary": _summary([_row("111", catalog_sku="3921245627")]),
        "previous_summary": None,
    })

    class Repository:
        def __init__(self):
            self.calls = []

        def get_mapping(self, finance_sku):
            assert finance_sku == "111"
            return {
                "error": False,
                "mapping_confirmed": True,
                "current_product_id": "p1",
                "current_sku": "3921245627",
            }

        def revoke_mapping(self, **kwargs):
            self.calls.append(kwargs)
            return {"error": False, "status": "REVOKED"}

    repository = Repository()
    runtime = PeriodProfitSkuRuntimeService(
        query, identity_repository=repository
    )

    pending = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:unmap:111"
    )
    revoked = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:unmap:111:confirm"
    )

    assert pending["status"] == (
        "PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_PENDING"
    )
    assert "недействительным" in pending["message"]
    assert revoked["status"] == "PERIOD_PROFIT_SKU_IDENTITY_REVOKED"
    assert repository.calls == [{
        "finance_sku": "111",
        "current_sku": "3921245627",
        "source": "SELLER_REVOKED_TELEGRAM_BUTTON",
    }]
    assert revoked["keyboard"]["buttons"][0]["callback"] == (
        "period_profit_sku:3921245627:7D"
    )


def test_forged_revocation_callback_is_rejected_before_storage():
    query = Query({"error": True, "code": "unused"})

    class Repository:
        def get_mapping(self, _finance_sku):
            return {
                "error": False,
                "mapping_confirmed": True,
                "current_product_id": "different-product",
                "current_sku": "3921245627",
            }

        def revoke_mapping(self, **_kwargs):
            raise AssertionError("unverified mapping must not be revoked")

    runtime = PeriodProfitSkuRuntimeService(
        query, identity_repository=Repository()
    )
    result = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:unmap:111:confirm"
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_NOT_VERIFIED"
    )


def test_forged_identity_candidate_is_rejected_before_storage():
    query = Query({
        "error": True,
        "code": "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_CONFIRMATION_REQUIRED",
        "identity_candidates": [{
            "finance_sku": "111",
            "historical_offer_id": "old-white",
        }],
    })

    class Repository:
        def record_mapping(self, **_kwargs):
            raise AssertionError("unverified candidate must not be stored")

    runtime = PeriodProfitSkuRuntimeService(
        query,
        identity_repository=Repository(),
    )
    result = runtime.handle_callback(
        "period_profit_sku:3921245627:7D:map:999:confirm"
    )

    assert result["error"] is True
    assert result["code"] == (
        "PERIOD_PROFIT_SKU_IDENTITY_CANDIDATE_NOT_VERIFIED"
    )
