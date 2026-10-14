import os
import sys
import unittest
from datetime import date
from threading import Event, Thread


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.telegram_seller_cost_update_service import (  # noqa: E402
    TelegramSellerCostUpdateService,
)
from services.tenant_context import (  # noqa: E402
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from telegram_app_layer.seller_cost_telegram_adapter import (  # noqa: E402
    SellerCostTelegramAdapter,
)


class Products:
    def load_products(self):
        return [("p1", "Offer 1", "sku-1")]


class TwoProducts:
    def load_products(self):
        return [
            ("p1", "Offer 1", "sku-1"),
            ("p2", "Offer 2", "sku-2"),
        ]


class Costs:
    def __init__(self):
        self.current = []
        self.recorded = []
        self.bulk_recorded = []

    def get_all_costs(self):
        return list(self.current)

    def record_cost_switch(self, **kwargs):
        self.recorded.append(kwargs)
        return {"error": False, "status": "PRODUCT_COST_SWITCH_RECORDED"}

    def record_cost_switches(self, rows):
        self.bulk_recorded.append(rows)
        self.current.extend(
            (
                row["product_id"],
                row["sku"],
                row["offer_id"],
                row["cost_price"],
                "RUB",
                "now",
            )
            for row in rows
        )
        return {"error": False, "inserted": len(rows), "unchanged": 0}


class _ButtonHandler:
    def handle(self, *args):
        raise AssertionError("seller-cost callback must be handled by the cost flow")


def _store_name():
    from services.tenant_context import get_current_tenant_user_id

    return str(get_current_tenant_user_id()).rsplit("::ozon::", 1)[-1]


class SellerCostConfirmationFlowTests(unittest.TestCase):
    def test_text_during_whole_history_confirmation_keeps_valid_draft_buttons(self):
        for table in (False, True):
            for cancel in (False, True):
                with self.subTest(table=table, cancel=cancel):
                    costs = Costs()
                    flow = TelegramSellerCostUpdateService(
                        Products(), costs, date_provider=lambda: date(2026, 9, 15)
                    )
                    if table:
                        preview = flow.import_table_for_user(
                            "user",
                            "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
                            "Offer 1;sku-1;430;\n",
                        )
                        select_action = flow.TABLE_SELECT_ALL_HISTORY_CALLBACK
                        confirm_action = flow.TABLE_CONFIRM_ALL_HISTORY_CALLBACK
                    else:
                        flow.select_sku("user", "sku-1")
                        preview = flow.handle_text("user", "430")
                        select_action = flow.SELECT_ALL_HISTORY_CALLBACK
                        confirm_action = flow.CONFIRM_ALL_HISTORY_CALLBACK
                    select_callback = next(
                        button["callback"] for button in preview["keyboard"]["buttons"]
                        if button["callback"].startswith(select_action + ":")
                    )
                    original = flow.handle_button("user", select_callback)
                    refreshed = flow.handle_text("user", "Покажи подтверждение ещё раз")

                    self.assertEqual(refreshed["message"], original["message"])
                    self.assertEqual(refreshed["keyboard"], original["keyboard"])
                    self.assertEqual(costs.recorded, [])
                    self.assertEqual(costs.bulk_recorded, [])
                    self.assertTrue(
                        refreshed["keyboard"]["buttons"][0]["callback"].startswith(
                            confirm_action + ":"
                        )
                    )
                    callback = refreshed["keyboard"]["buttons"][-1 if cancel else 0]["callback"]
                    result = flow.handle_button("user", callback)
                    self.assertFalse(result["error"])
                    if cancel:
                        self.assertEqual(costs.recorded, [])
                        self.assertEqual(costs.bulk_recorded, [])
                    elif table:
                        self.assertEqual(costs.bulk_recorded[0][0]["effective_from"], "0001-01-01")
                    else:
                        self.assertEqual(costs.recorded[0]["effective_from"], "0001-01-01")

    def test_old_product_preview_actions_cannot_change_a_new_draft(self):
        costs = Costs()
        flow = TelegramSellerCostUpdateService(
            TwoProducts(), costs, date_provider=lambda: date(2026, 9, 15)
        )
        flow.select_sku("user", "sku-1")
        first_preview = flow.handle_text("user", "10")
        old_callbacks = [
            button["callback"] for button in first_preview["keyboard"]["buttons"]
        ]

        flow.select_sku("user", "sku-1")
        second_preview = flow.handle_text("user", "20")
        new_callback = second_preview["keyboard"]["buttons"][0]["callback"]

        for old_callback in old_callbacks:
            stale = flow.handle_button("user", old_callback)
            self.assertTrue(stale["error"])
            self.assertEqual(
                stale["code"], "SELLER_COST_CONFIRMATION_UNAVAILABLE"
            )
        self.assertEqual(costs.recorded, [])

        saved = flow.handle_button("user", new_callback)
        self.assertFalse(saved["error"])
        self.assertEqual(costs.recorded[0]["sku"], "sku-1")
        self.assertEqual(costs.recorded[0]["cost_price"], 20.0)

        flow.select_sku("user", "sku-2")
        other_sku_preview = flow.handle_text("user", "30")
        stale = flow.handle_button("user", new_callback)
        self.assertTrue(stale["error"])
        self.assertEqual(len(costs.recorded), 1)
        saved = flow.handle_button(
            "user", other_sku_preview["keyboard"]["buttons"][0]["callback"]
        )
        self.assertFalse(saved["error"])
        self.assertEqual(costs.recorded[1]["sku"], "sku-2")
        self.assertEqual(costs.recorded[1]["cost_price"], 30.0)

    def test_parallel_replay_of_one_confirmation_writes_once(self):
        entered_save = Event()
        release_save = Event()

        class BlockingCosts(Costs):
            def record_cost_switch(self, **kwargs):
                entered_save.set()
                if not release_save.wait(3):
                    raise AssertionError("test did not release save")
                return super().record_cost_switch(**kwargs)

        costs = BlockingCosts()
        flow = TelegramSellerCostUpdateService(
            Products(), costs, date_provider=lambda: date(2026, 9, 15)
        )
        flow.select_sku("user", "sku-1")
        preview = flow.handle_text("user", "10")
        callback = preview["keyboard"]["buttons"][0]["callback"]
        results = []
        second_started = Event()

        first = Thread(
            target=lambda: results.append(flow.handle_button("user", callback))
        )
        first.start()
        self.assertTrue(entered_save.wait(2))

        def replay():
            second_started.set()
            results.append(flow.handle_button("user", callback))

        second = Thread(target=replay)
        second.start()
        self.assertTrue(second_started.wait(2))
        release_save.set()
        first.join(3)
        second.join(3)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(costs.recorded), 1)
        self.assertEqual(sum(result.get("error") is False for result in results), 1)

    def test_stale_store_confirmation_is_rejected_without_write(self):
        costs = Costs()
        flow = TelegramSellerCostUpdateService(
            Products(),
            costs,
            date_provider=lambda: date(2026, 9, 15),
            store_name_provider=_store_name,
        )
        token = set_current_tenant_user_id("user::ozon::store-a")
        try:
            flow.select_sku("user", "sku-1")
            preview = flow.handle_text("user", "430")
            self.assertTrue(preview["seller_cost_confirmation_pending"])
            self.assertIn("Магазин: store-a", preview["message"])
        finally:
            reset_current_tenant_user_id(token)

        token = set_current_tenant_user_id("user::ozon::store-b")
        try:
            result = flow.handle_button(
                "user", preview["keyboard"]["buttons"][0]["callback"]
            )
        finally:
            reset_current_tenant_user_id(token)

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "SELLER_COST_PENDING_STORE_STALE")
        self.assertEqual(costs.recorded, [])

    def test_cancel_and_replayed_confirmation_never_write_twice(self):
        costs = Costs()
        flow = TelegramSellerCostUpdateService(
            Products(), costs, date_provider=lambda: date(2026, 9, 15)
        )
        flow.select_sku("user", "sku-1")
        preview = flow.handle_text("user", "430")
        callbacks = [
            button["callback"] for button in preview["keyboard"]["buttons"]
        ]
        cancelled = flow.handle_button("user", callbacks[-1])
        self.assertFalse(cancelled["error"])
        self.assertEqual(costs.recorded, [])
        stale = flow.handle_button("user", callbacks[0])
        self.assertTrue(stale["error"])
        self.assertEqual(costs.recorded, [])

    def test_csv_import_is_previewed_and_whole_history_gets_second_confirmation(self):
        costs = Costs()
        flow = TelegramSellerCostUpdateService(
            Products(),
            costs,
            date_provider=lambda: date(2026, 9, 15),
            store_name_provider=lambda: "Store A",
        )
        adapter = SellerCostTelegramAdapter(
            assistant=object(),
            keyboard_service=object(),
            button_handler=_ButtonHandler(),
            seller_cost_service=flow,
        )
        content = (
            "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
            "Offer 1;sku-1;430;\n"
        )

        preview = adapter.handle_document(content, user_id="user", filename="cost.csv")
        self.assertFalse(preview["error"])
        self.assertTrue(preview["seller_cost_confirmation_pending"])
        self.assertIn("Магазин: Store A", preview["message"])
        self.assertEqual(costs.bulk_recorded, [])

        select_history = next(
            button["callback"] for button in preview["keyboard"]["buttons"]
            if button["callback"].startswith(
                flow.TABLE_SELECT_ALL_HISTORY_CALLBACK + ":"
            )
        )
        selected = adapter.handle_button(select_history, user_id="user")
        self.assertFalse(selected["error"])
        self.assertIn("ко всей истории продаж", selected["message"])
        self.assertEqual(costs.bulk_recorded, [])

        saved = adapter.handle_button(
            selected["keyboard"]["buttons"][0]["callback"], user_id="user"
        )
        self.assertFalse(saved["error"])
        self.assertEqual(costs.bulk_recorded[0][0]["effective_from"], "0001-01-01")
        self.assertEqual(
            costs.bulk_recorded[0][0]["source"],
            "SELLER_CONFIRMED_INITIAL_HISTORY_TABLE",
        )

    def test_csv_import_uses_explicit_date_and_confirmation_callback(self):
        costs = Costs()
        flow = TelegramSellerCostUpdateService(
            Products(),
            costs,
            date_provider=lambda: date(2026, 9, 15),
            store_name_provider=lambda: "Store A",
        )
        adapter = SellerCostTelegramAdapter(
            assistant=object(),
            keyboard_service=object(),
            button_handler=_ButtonHandler(),
            seller_cost_service=flow,
        )
        content = (
            "Артикул;Ozon SKU;Себестоимость, ₽;Действует с (ГГГГ-ММ-ДД)\n"
            "Offer 1;sku-1;430;2026-09-20\n"
        )
        preview = adapter.handle_document(content, user_id="user", filename="cost.csv")
        self.assertIn("с 2026-09-20", preview["message"])
        old_save = preview["keyboard"]["buttons"][0]["callback"]
        old_select_history = next(
            button["callback"] for button in preview["keyboard"]["buttons"]
            if button["callback"].startswith(
                flow.TABLE_SELECT_ALL_HISTORY_CALLBACK + ":"
            )
        )
        old_all_history_prompt = adapter.handle_button(
            old_select_history, user_id="user"
        )
        old_all_history_confirm = old_all_history_prompt["keyboard"]["buttons"][0]["callback"]
        old_cancel = old_all_history_prompt["keyboard"]["buttons"][1]["callback"]

        replacement = content.replace("430;2026-09-20", "500;2026-09-22")
        new_preview = adapter.handle_document(
            replacement, user_id="user", filename="replacement.csv"
        )
        for old_callback in (old_save, old_all_history_confirm, old_cancel):
            stale = adapter.handle_button(old_callback, user_id="user")
            self.assertTrue(stale["error"])
        self.assertEqual(costs.bulk_recorded, [])

        saved = adapter.handle_button(
            new_preview["keyboard"]["buttons"][0]["callback"], user_id="user"
        )
        self.assertFalse(saved["error"])
        self.assertEqual(costs.bulk_recorded[0][0]["cost_price"], 500.0)
        self.assertEqual(costs.bulk_recorded[0][0]["effective_from"], "2026-09-22")


if __name__ == "__main__":
    unittest.main()
