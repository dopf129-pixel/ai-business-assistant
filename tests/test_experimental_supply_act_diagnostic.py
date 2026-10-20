from api.ozon_client import OzonClient
from services.assistant_button_handler_service import AssistantButtonHandlerService
from services.assistant_keyboard_service import AssistantKeyboardService
from services.experimental_store_economics_runtime_service import (
    ExperimentalStoreEconomicsRuntimeService,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def test_supply_act_products_client_uses_documented_read_only_contract(monkeypatch):
    calls = []

    def post(self, endpoint, payload, **options):
        calls.append((endpoint, payload, options))
        return {"error": False, "supply_acts": []}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    result = client.get_supply_act_products(
        "2000070135564",
        timeout=7,
        max_attempts=1,
        total_timeout=9,
    )

    assert result == {"error": False, "supply_acts": []}
    assert calls == [
        (
            "/v1/supply-order/act/product/get",
            {"supply_id": 2000070135564},
            {"timeout": 7, "max_attempts": 1, "total_timeout": 9},
        )
    ]


def test_supply_act_summary_client_uses_documented_read_only_contract(monkeypatch):
    calls = []

    def post(self, endpoint, payload, **options):
        calls.append((endpoint, payload, options))
        return {"error": False, "supplies_acts": []}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    result = client.get_supply_act_summary(
        "2000070135564",
        timeout=7,
        max_attempts=1,
        total_timeout=9,
    )

    assert result == {"error": False, "supplies_acts": []}
    assert calls == [
        (
            "/v1/supply-order/act/summary/get",
            {"order_id": 2000070135564},
            {"timeout": 7, "max_attempts": 1, "total_timeout": 9},
        )
    ]


def test_supply_act_summary_client_rejects_invalid_ids_without_request(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return {"error": False}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    for value in (None, "", "abc", "1.2", True, 0, -1, 2**63):
        result = client.get_supply_act_summary(value)
        assert result["error"] is True
        assert result["code"] == "OZON_SUPPLY_ACT_REQUEST_INVALID"

    assert calls == []


def test_supply_order_details_client_uses_documented_read_only_contract(monkeypatch):
    calls = []

    def post(self, endpoint, payload, **options):
        calls.append((endpoint, payload, options))
        return {"error": False, "orders": []}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    result = client.get_supply_order_details(
        "2000070135564",
        timeout=7,
        max_attempts=1,
        total_timeout=9,
    )

    assert result == {"error": False, "orders": []}
    assert calls == [
        (
            "/v3/supply-order/get",
            {"order_ids": [2000070135564]},
            {"timeout": 7, "max_attempts": 1, "total_timeout": 9},
        )
    ]


def test_supply_order_details_client_rejects_invalid_ids_without_request(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return {"error": False}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    for value in (None, "", "abc", "1.2", True, 0, -1, 2**63):
        result = client.get_supply_order_details(value)
        assert result["error"] is True
        assert result["code"] == "OZON_SUPPLY_ORDER_REQUEST_INVALID"

    assert calls == []


def test_supply_act_products_client_rejects_invalid_ids_without_request(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return {"error": False}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    for value in (None, "", "abc", "1.2", True, 0, -1, 2**63):
        result = client.get_supply_act_products(value)
        assert result["error"] is True
        assert result["code"] == "OZON_SUPPLY_ACT_REQUEST_INVALID"

    assert calls == []


class _SupplyActClient:
    def __init__(self, response=None, summary_response=None, order_response=None):
        self.response = response or {"error": False, "supply_acts": []}
        self.summary_response = summary_response
        self.order_response = order_response or {"error": False, "orders": []}
        self.calls = []
        self.summary_calls = []
        self.order_calls = []

    def get_supply_act_products(self, supply_id, **kwargs):
        self.calls.append((supply_id, kwargs))
        return self.response

    def get_supply_act_summary(self, order_id, **kwargs):
        self.summary_calls.append((order_id, kwargs))
        return self.summary_response

    def get_supply_order_details(self, order_id, **kwargs):
        self.order_calls.append((order_id, kwargs))
        return self.order_response


def _handler(client):
    keyboard = AssistantKeyboardService()
    runtime = ExperimentalStoreEconomicsRuntimeService(
        query_service=None,
        analytics_client=client,
    )
    return AssistantButtonHandlerService(
        assistant=None,
        keyboard_service=keyboard,
        experimental_store_economics_runtime_service=runtime,
    )


def test_bot_diagnostic_waits_for_user_and_returns_only_redacted_quantities():
    client = _SupplyActClient(
        {
            "error": False,
            "skus_defects": [{"sku": 8900000001}],
            "supply_acts": [
                {
                    "act_id": 7800000001,
                    "type": "UNSPECIFIED",
                    "items": [
                        {
                            "sku_info": {
                                "sku": 8900000001,
                                "name": "Secret product name",
                                "barcode": "9876543210000",
                            },
                            "declared_quantity": 500,
                            "approved_quantity": 499,
                            "fact_quantity": 499,
                            "unidentified_quantity": 1,
                        }
                    ],
                }
            ],
        },
        summary_response={
            "error": False,
            "supplies_acts": [
                {
                    "supply_id": 2000070135564,
                    "is_agreement_completed": True,
                    "supply_acts": [
                        {
                            "act_id": 7800000001,
                            "act_state": "ACCEPTED",
                            "created_date": "2026-10-16T08:30:00Z",
                            "type": "ACCEPTANCE",
                            "summary": {
                                "approved_quantity": 500,
                                "fact_quantity": 500,
                            },
                        }
                    ],
                }
            ],
        },
        order_response={
            "error": False,
            "orders": [
                {
                    "order_id": 2000070135564,
                    "state": "COMPLETED",
                    "state_updated_date": "2026-10-16T10:00:00Z",
                    "supplies": [
                        {
                            "supply_id": 2000070135564,
                            "state": "COMPLETED",
                            "is_crossdock": True,
                            "storage_warehouse": {
                                "arrival_date": "2026-10-13T00:00:00Z",
                                "name": "Private warehouse name",
                            },
                        }
                    ],
                }
            ],
        },
    )
    handler = _handler(client)

    menu = handler.handle("experimental_calculations", user_id=505)
    diagnostic_button = next(
        button
        for button in menu["keyboard"]["buttons"]
        if button["callback"] == "experimental_supply_act_diagnostic"
    )
    prompt = handler.handle(diagnostic_button["callback"], user_id=505)

    assert client.calls == []
    assert prompt["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_INPUT_REQUIRED"
    assert prompt["keyboard"]["buttons"]

    result = handler.handle_text("2000070135564", user_id=505)

    assert client.calls == [
        (
            2000070135564,
            {"timeout": 15, "max_attempts": 2, "total_timeout": 25},
        )
    ]
    assert client.summary_calls == [
        (
            2000070135564,
            {"timeout": 10, "max_attempts": 1, "total_timeout": 15},
        )
    ]
    assert client.order_calls == [
        (
            2000070135564,
            {"timeout": 10, "max_attempts": 1, "total_timeout": 15},
        )
    ]
    assert result["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_READY"
    assert "declared_quantity=500" in result["message"]
    assert "approved_quantity=499" in result["message"]
    assert "fact_quantity=499" in result["message"]
    assert "sku_info.sku=int" in result["message"]
    assert "Secret product name" not in result["message"]
    assert "9876543210000" not in result["message"]
    assert "8900000001" not in result["message"]
    assert "7800000001" not in result["message"]
    assert "состояние=ACCEPTED" in result["message"]
    assert "created_date=2026-10-16T08:30:00Z" in result["message"]
    assert "summary approved_quantity=500, fact_quantity=500" in result["message"]
    assert "есть совпадающий supply_id: да" in result["message"]
    assert "state=COMPLETED; state_updated_date=2026-10-16T10:00:00Z" in result["message"]
    assert "is_crossdock=да" in result["message"]
    assert "arrival_date=2026-10-13T00:00:00Z" in result["message"]
    assert "supplies[0].is_crossdock=bool" in result["message"]
    assert "Private warehouse name" not in result["message"]
    assert "сама по себе не доказывает дату фактической приёмки" in result["message"]
    assert "2000070135564" not in result["message"]
    assert result["read_only"] is True
    assert result["executed"] is False


def test_invalid_supply_act_id_does_not_call_api_and_keeps_prompt_active():
    client = _SupplyActClient()
    handler = _handler(client)
    handler.handle("experimental_supply_act_diagnostic", user_id=506)

    invalid = handler.handle_text("2000 0701", user_id=506)

    assert invalid["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_ID_INVALID"
    assert invalid["keyboard"]["buttons"]
    assert client.calls == []

    cancelled = handler.handle_text("Отмена", user_id=506)
    assert cancelled["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_CANCELLED"
    assert client.calls == []
    assert client.summary_calls == []
    assert client.order_calls == []


def test_supply_act_diagnostic_input_is_bound_to_current_tenant():
    client = _SupplyActClient()
    handler = _handler(client)
    token = set_current_tenant_user_id("store-a")
    try:
        handler.handle("experimental_supply_act_diagnostic", user_id=507)
    finally:
        reset_current_tenant_user_id(token)

    token = set_current_tenant_user_id("store-b")
    try:
        result = handler.handle_text("2000070135564", user_id=507)
    finally:
        reset_current_tenant_user_id(token)

    assert result["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_SCOPE_CHANGED"
    assert client.calls == []
    assert client.summary_calls == []
    assert client.order_calls == []


def test_supply_act_api_error_code_is_safe_and_response_values_are_not_echoed():
    client = _SupplyActClient(
        {
            "error": True,
            "code": "OZON_CREDENTIALS_UNAVAILABLE",
            "message": "Api-Key=super-secret",
        }
    )
    handler = _handler(client)
    handler.handle("experimental_supply_act_diagnostic", user_id=508)

    result = handler.handle_text("2000070135564", user_id=508)

    assert result["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_UNAVAILABLE"
    assert "OZON_CREDENTIALS_UNAVAILABLE" in result["message"]
    assert "super-secret" not in result["message"]


def test_summary_error_is_reported_without_discarding_product_quantities():
    client = _SupplyActClient(
        {
            "error": False,
            "supply_acts": [
                {
                    "type": "ACCEPTANCE",
                    "items": [{"fact_quantity": 500}],
                }
            ],
        },
        summary_response={
            "error": True,
            "code": "OZON_SUPPLY_ACT_SUMMARY_NOT_FOUND",
            "message": "Api-Key=secret",
        },
    )
    handler = _handler(client)
    handler.handle("experimental_supply_act_diagnostic", user_id=509)

    result = handler.handle_text("2000070135564", user_id=509)

    assert result["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_READY"
    assert "fact_quantity=500" in result["message"]
    assert "Сводка акта недоступна: OZON_SUPPLY_ACT_SUMMARY_NOT_FOUND." in result["message"]
    assert "Api-Key" not in result["message"]


def test_unmatched_summary_does_not_present_another_supply_act_as_selected():
    client = _SupplyActClient(
        {
            "error": False,
            "supply_acts": [
                {
                    "type": "ACCEPTANCE",
                    "items": [{"fact_quantity": 500}],
                }
            ],
        },
        summary_response={
            "error": False,
            "supplies_acts": [
                {
                    "supply_id": "999999999999",
                    "is_agreement_completed": True,
                    "supply_acts": [
                        {
                            "act_state": "OTHER_SUPPLY_STATE",
                            "created_date": "2026-10-16T08:30:00Z",
                            "type": "OTHER_SUPPLY_ACT",
                            "summary": {"fact_quantity": 100},
                        }
                    ],
                }
            ],
        },
    )
    handler = _handler(client)
    handler.handle("experimental_supply_act_diagnostic", user_id=510)

    result = handler.handle_text("2000070135564", user_id=510)

    assert result["status"] == "EXPERIMENTAL_SUPPLY_ACT_DIAGNOSTIC_READY"
    assert "fact_quantity=500" in result["message"]
    assert "совпадающий supply_id: нет" in result["message"]
    assert "Детали актов не показаны" in result["message"]
    assert "OTHER_SUPPLY_STATE" not in result["message"]
    assert "2026-10-16T08:30:00Z" not in result["message"]
    assert "999999999999" not in result["message"]


def test_unmatched_supply_order_does_not_expose_another_orders_details():
    result = ExperimentalStoreEconomicsRuntimeService._render_supply_act_product_diagnostic(
        {"error": False, "supply_acts": []},
        supply_order_response={
            "error": False,
            "orders": [
                {
                    "order_id": 999999999999,
                    "state": "FOREIGN_ORDER_STATE",
                    "state_updated_date": "2026-10-17T10:00:00Z",
                    "supplies": [
                        {
                            "supply_id": 888888888888,
                            "state": "FOREIGN_SUPPLY_STATE",
                            "is_crossdock": True,
                            "storage_warehouse": {
                                "arrival_date": "2026-10-17T00:00:00Z",
                                "name": "Private warehouse name",
                            },
                        }
                    ],
                }
            ],
        },
        expected_supply_id=2000070135564,
    )

    assert "совпадение по ID не найдено" in result["message"]
    assert "999999999999" not in result["message"]
    assert "888888888888" not in result["message"]
    assert "FOREIGN_ORDER_STATE" not in result["message"]
    assert "FOREIGN_SUPPLY_STATE" not in result["message"]
    assert "2026-10-17" not in result["message"]
    assert "Private warehouse name" not in result["message"]


def test_large_supply_act_diagnostic_stays_below_telegram_message_limit():
    supply_id = 2000070135564
    quantity = 9_223_372_036_854_775_807
    product_items = [
        {
            "sku_info": {"sku": index, "name": "Private product name"},
            "declared_quantity": quantity,
            "approved_quantity": quantity,
            "fact_quantity": quantity,
            "unidentified_quantity": quantity,
        }
        for index in range(50)
    ]
    summary_acts = [
        {
            "act_state": "ACCEPTED",
            "created_date": "2026-10-16T08:30:00Z",
            "type": "ACCEPTANCE",
            "summary": {
                "declared_quantity": quantity,
                "approved_quantity": quantity,
                "fact_quantity": quantity,
                "sku_quantity": quantity,
                "unidentified_quantity": quantity,
            },
        }
        for _ in range(50)
    ]
    result = ExperimentalStoreEconomicsRuntimeService._render_supply_act_product_diagnostic(
        {"error": False, "supply_acts": [{"type": "ACCEPTANCE", "items": product_items}]},
        summary_response={
            "error": False,
            "supplies_acts": [
                {
                    "supply_id": supply_id,
                    "is_agreement_completed": True,
                    "supply_acts": summary_acts,
                }
            ],
        },
        supply_order_response={
            "error": False,
            "orders": [
                {
                    "order_id": supply_id,
                    "state": "COMPLETED",
                    "state_updated_date": "2026-10-16T10:00:00Z",
                    "supplies": [
                        {
                            "supply_id": supply_id + index,
                            "state": "COMPLETED",
                            "is_crossdock": True,
                        }
                        for index in range(50)
                    ],
                }
            ],
        },
        expected_supply_id=supply_id,
    )

    assert len(result["message"]) < 4096
    assert "Показаны первые 4 строк из 50" in result["message"]
    assert "Показаны первые 4 поставки из 50" in result["message"]
    assert "Показаны первые 4 актов из 20" in result["message"]
    assert "Private product name" not in result["message"]

