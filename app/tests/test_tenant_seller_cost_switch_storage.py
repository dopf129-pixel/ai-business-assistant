import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.period_profit_effective_cost_service import (  # noqa: E402
    PeriodProfitEffectiveCostService,
)
from services.telegram_seller_cost_update_service import (  # noqa: E402
    TelegramSellerCostUpdateService,
)
from services.tenant_context import (  # noqa: E402
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.tenant_storage import tenant_storage_path  # noqa: E402


class Hook2Products:
    def load_products(self):
        return [("product-hook-2", "hook-2", "3921245627")]


class TenantSellerCostSwitchStorageTests(unittest.TestCase):
    def test_hook2_cost_21_is_saved_in_request_tenant_after_startup(self):
        previous_root = os.environ.get("AI_ASSISTANT_STORAGE_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AI_ASSISTANT_STORAGE_ROOT"] = tmp
            try:
                # Production factory constructs this service before a Telegram
                # request binds a tenant. The regression is specifically that
                # the later tenant-local database must initialize switch schema.
                costs = PeriodProfitEffectiveCostService()
                token = set_current_tenant_user_id("telegram-live-user")
                try:
                    flow = TelegramSellerCostUpdateService(
                        product_service=Hook2Products(),
                        cost_service=costs,
                        date_provider=lambda: date(2026, 9, 11),
                    )

                    selected = flow.select_sku("telegram-live-user", "3921245627")
                    self.assertFalse(selected["error"])
                    self.assertTrue(selected["read_only_ozon"])

                    result = flow.handle_text("telegram-live-user", "21")
                    self.assertFalse(result["error"])
                    self.assertTrue(result["handled"])
                    self.assertEqual(result["sku"], "3921245627")
                    self.assertEqual(result["offer_id"], "hook-2")
                    self.assertEqual(result["cost_price"], 21.0)
                    self.assertEqual(result["effective_from"], "2026-09-12")
                    self.assertTrue(result["read_only_ozon"])

                    tenant_db = tenant_storage_path("ozon_assistant.db")
                    conn = sqlite3.connect(tenant_db)
                    try:
                        row = conn.execute(
                            """
                            SELECT product_id, sku, offer_id, cost_price, effective_from
                            FROM product_cost_switch_history
                            WHERE sku = ?
                            """,
                            ("3921245627",),
                        ).fetchone()
                    finally:
                        conn.close()

                    self.assertEqual(
                        row,
                        (
                            "product-hook-2",
                            "3921245627",
                            "hook-2",
                            21.0,
                            "2026-09-12",
                        ),
                    )
                finally:
                    reset_current_tenant_user_id(token)
            finally:
                if previous_root is None:
                    os.environ.pop("AI_ASSISTANT_STORAGE_ROOT", None)
                else:
                    os.environ["AI_ASSISTANT_STORAGE_ROOT"] = previous_root


if __name__ == "__main__":
    unittest.main()
