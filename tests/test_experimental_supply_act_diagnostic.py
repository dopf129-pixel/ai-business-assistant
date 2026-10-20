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


def test_supply_order_list_client_uses_documented_cursor_contract(monkeypatch):
    calls = []

    def post(self, endpoint, payload, **options):
        calls.append((endpoint, payload, options))
        return {"error": False, "order_ids": [123], "last_id": "cursor"}

    monkeypatch.setattr(OzonClient, "_post", post)
    client = OzonClient(
        client_id="client",
        api_key="secret",
        credential_provider=object(),
    )

    result = client.get_supply_orders_list(
        ["COMPLETED"],
        timeout=7,
        max_attempts=1,
        total_timeout=9,
    )

    assert result == {"error": False, "order_ids": [123], "last_id": "cursor"}
    assert calls == [
        (
            "/v3/supply-order/list",
            {
                "filter": {"states": ["COMPLETED"]},
                "limit": 100,
                "sort_by": "ORDER_STATE_UPDATED_AT",
                "sort_dir": "DESC",
            },
            {"timeout": 7, "max_attempts": 1, "total_timeout": 9},
        )
    ]


def test_supply_orders_details_client_batches_up_to_fifty_ids(monkeypatch):
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

    result = client.get_supply_orders_details(
        ["123", 456], timeout=7, max_attempts=1, total_timeout=9
    )

    assert result == {"error": False, "orders": []}
    assert calls == [
        (
            "/v3/supply-order/get",
            {"order_ids": [123, 456]},
            {"timeout": 7, "max_attempts": 1, "total_timeout": 9},
        )
    ]


def test_supply_order_list_client_rejects_invalid_cursor_and_limit(monkeypatch):
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

    for kwargs in (
        {"states": []},
        {"states": ["COMPLETED"], "limit": 101},
        {"states": ["not-completed"]},
        {"states": ["COMPLETED"], "last_id": ""},
    ):
        result = client.get_supply_orders_list(**kwargs)
        assert result["error"] is True
        assert result["code"] == "OZON_SUPPLY_ORDER_LIST_REQUEST_INVALID"

    assert calls == []


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
    def __init__(
        self,
        response=None,
        summary_response=None,
        order_response=None,
        order_list_responses=None,
        order_responses=None,
    ):
        self.response = response or {"error": False, "supply_acts": []}
        self.summary_response = summary_response
        self.order_response = order_response or {"error": False, "orders": []}
        self.order_responses = list(order_responses or [])
        self.order_list_responses = list(
            order_list_responses
            or [{"error": False, "order_ids": [], "last_id": ""}]
        )
        self.calls = []
        self.summary_calls = []
        self.order_calls = []
        self.order_list_calls = []

    def get_supply_act_products(self, supply_id, **kwargs):
        self.calls.append((supply_id, kwargs))
        return self.response

    def get_supply_act_summary(self, order_id, **kwargs):
        self.summary_calls.append((order_id, kwargs))
        return self.summary_response

    def get_supply_orders_list(self, **kwargs):
        self.order_list_calls.append(kwargs)
        if self.order_list_responses:
            return self.order_list_responses.pop(0)
        return {"error": False, "order_ids": [], "last_id": ""}

    def get_supply_orders_details(self, order_ids, **kwargs):
        self.order_calls.append((order_ids, kwargs))
        if self.order_responses:
            return self.order_responses.pop(0)
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
                    "order_id": 987654321,
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
        order_list_responses=[
            {
                "error": False,
                "order_ids": [987654321],
                "last_id": "next-page",
            }
        ],
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
    assert client.order_list_calls == [
        {
            "states": ExperimentalStoreEconomicsRuntimeService.SUPPLY_ORDER_LIST_STATES,
            "last_id": None,
            "limit": 100,
            "sort_by": "ORDER_STATE_UPDATED_AT",
            "sort_dir": "DESC",
            "timeout": 8,
            "max_attempts": 1,
            "total_timeout": 10,
        }
    ]
    assert client.order_calls == [
        (
            [987654321],
            {"timeout": 8, "max_attempts": 1, "total_timeout": 10},
        )
    ]
    assert client.summary_calls == [
        (
            987654321,
            {"timeout": 10, "max_attempts": 1, "total_timeout": 15},
        )
    ]
    assert "ID заявки найден через supply_id: проверено страниц 1, ID заявок 1." in result["message"]
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


def test_supply_order_lookup_uses_cursor_pages_until_nested_supply_matches():
    target_supply_id = 2000070135564
    client = _SupplyActClient(
        {
            "error": False,
            "supply_acts": [{"type": "ACCEPTANCE", "items": []}],
        },
        summary_response={"error": False, "supplies_acts": []},
        order_list_responses=[
            {"error": False, "order_ids": [101], "last_id": "cursor-2"},
            {"error": False, "order_ids": [202], "last_id": ""},
        ],
        order_responses=[
            {
                "error": False,
                "orders": [
                    {"order_id": 101, "supplies": [{"supply_id": 999}]}
                ],
            },
            {
                "error": False,
                "orders": [
                    {
                        "order_id": 202,
                        "state": "COMPLETED",
                        "state_updated_date": "2026-10-16T10:00:00Z",
                        "supplies": [
                            {"supply_id": target_supply_id, "is_crossdock": True}
                        ],
                    }
                ],
            },
        ],
    )
    handler = _handler(client)
    handler.handle("experimental_supply_act_diagnostic", user_id=512)

    result = handler.handle_text(str(target_supply_id), user_id=512)

    assert [call["last_id"] for call in client.order_list_calls] == [None, "cursor-2"]
    assert [call[0] for call in client.order_calls] == [[101], [202]]
    assert client.summary_calls[0][0] == 202
    assert "ID заявки найден через supply_id: проверено страниц 2, ID заявок 2." in result["message"]
    assert "state=COMPLETED" in result["message"]


def test_supply_api_http_status_is_reported_without_echoing_response_body():
    result = ExperimentalStoreEconomicsRuntimeService._render_supply_act_product_diagnostic(
        {"error": False, "supply_acts": []},
        supply_order_response={
            "error": True,
            "code": "OZON_HTTP_ERROR",
            "status_code": 404,
            "message": "Api-Key=private-value",
        },
    )

    assert "Детали заявки недоступны: OZON_HTTP_404." in result["message"]
    assert "private-value" not in result["message"]


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
        order_response={
            "error": False,
            "orders": [
                {
                    "order_id": 987654321,
                    "state": "COMPLETED",
                    "supplies": [{"supply_id": 2000070135564, "is_crossdock": True}],
                }
            ],
        },
        order_list_responses=[
            {"error": False, "order_ids": [987654321], "last_id": ""}
        ],
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
        order_response={
            "error": False,
            "orders": [
                {
                    "order_id": 987654321,
                    "state": "COMPLETED",
                    "supplies": [{"supply_id": 2000070135564}],
                }
            ],
        },
        order_list_responses=[
            {"error": False, "order_ids": [987654321], "last_id": ""}
        ],
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

    assert "точное совпадение заявки и вложенной поставки не найдено" in result["message"]
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
        expected_order_id=supply_id,
        expected_supply_id=supply_id,
    )

    assert len(result["message"]) < 4096
    assert "Показаны первые 4 строк из 50" in result["message"]
    assert "Показаны первые 4 поставки из 50" in result["message"]
    assert "Показаны первые 4 актов из 20" in result["message"]
    assert "Private product name" not in result["message"]

