import os
import sys
import unittest
from datetime import date


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
            result = flow.handle_button("user", flow.CONFIRM_DATE_CALLBACK)
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
        flow.handle_text("user", "430")
        cancelled = flow.handle_button("user", flow.CANCEL_CALLBACK)
        self.assertFalse(cancelled["error"])
        self.assertEqual(costs.recorded, [])
        stale = flow.handle_button("user", flow.CONFIRM_DATE_CALLBACK)
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

        selected = adapter.handle_button(
            flow.TABLE_SELECT_ALL_HISTORY_CALLBACK, user_id="user"
        )
        self.assertFalse(selected["error"])
        self.assertIn("ко всей истории продаж", selected["message"])
        self.assertEqual(costs.bulk_recorded, [])

        saved = adapter.handle_button(
            flow.TABLE_CONFIRM_ALL_HISTORY_CALLBACK, user_id="user"
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
        saved = adapter.handle_button(flow.TABLE_CONFIRM_CALLBACK, user_id="user")
        self.assertFalse(saved["error"])
        self.assertEqual(costs.bulk_recorded[0][0]["effective_from"], "2026-09-20")


if __name__ == "__main__":
    unittest.main()
