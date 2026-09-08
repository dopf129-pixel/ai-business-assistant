import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from services.telegram_seller_cost_update_service import (  # noqa: E402
    TelegramSellerCostUpdateService,
)


class FakeProducts:
    def load_products(self):
        return [("p1", "hook-2", "3921245627")]


class FakeCostService:
    pass


class SellerCostDisplayOfferIdTests(unittest.TestCase):
    def test_menu_displays_offer_id_but_callback_keeps_sku(self):
        flow = TelegramSellerCostUpdateService(FakeProducts(), FakeCostService())

        result = flow.open_menu()

        self.assertFalse(result["error"])
        self.assertEqual(
            result["message"],
            "Выберите артикул товара, для которого приехала новая партия:",
        )
        self.assertEqual(
            result["keyboard"]["buttons"],
            [{"text": "hook-2", "callback": "seller_cost:3921245627"}],
        )

    def test_selection_confirms_offer_id_and_preserves_sku_identity(self):
        flow = TelegramSellerCostUpdateService(FakeProducts(), FakeCostService())

        result = flow.select_sku(123, "3921245627")

        self.assertFalse(result["error"])
        self.assertIn("Артикул hook-2 выбран (SKU 3921245627).", result["message"])
        self.assertEqual(
            flow._pending["123"],
            {
                "product_id": "p1",
                "sku": "3921245627",
                "offer_id": "hook-2",
            },
        )


if __name__ == "__main__":
    unittest.main()
