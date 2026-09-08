import unittest
from datetime import date

from services.telegram_return_inventory_confirmation_service import (
    TelegramReturnInventoryConfirmationService,
)


class RecordingRepository:
    def __init__(self):
        self.calls = []

    def record_recovery(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "error": False,
            "status": "RETURN_INVENTORY_RECOVERY_RECORDED",
            "history_id": len(self.calls),
        }


class TelegramReturnInventoryConfirmationServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = RecordingRepository()
        self.service = TelegramReturnInventoryConfirmationService(
            self.repository,
            date_provider=lambda: date(2026, 9, 8),
        )
        self.user_id = 42

    def _enter_identity(self):
        opened = self.service.open_menu(self.user_id)
        self.assertFalse(opened["error"])
        result = self.service.handle_text(
            self.user_id,
            "1001736969 | 0239984545-0031-1 | 3921245627 | 1",
        )
        self.assertFalse(result["error"])
        self.assertTrue(result["handled"])
        return result

    def test_saleable_recovery_requires_explicit_final_confirmation(self):
        identity = self._enter_identity()
        callbacks = [
            button["callback"]
            for button in identity["keyboard"]["buttons"]
        ]
        self.assertIn(
            "return_inventory_state:SALEABLE_RESTORED",
            callbacks,
        )
        self.assertEqual([], self.repository.calls)

        selected = self.service.select_state(
            self.user_id,
            "SALEABLE_RESTORED",
        )
        self.assertFalse(selected["error"])
        self.assertEqual([], self.repository.calls)

        confirmed = self.service.confirm(self.user_id)
        self.assertFalse(confirmed["error"])
        self.assertEqual(1, len(self.repository.calls))
        self.assertEqual(
            {
                "return_id": "1001736969",
                "posting_number": "0239984545-0031-1",
                "sku": "3921245627",
                "quantity": 1,
                "recovery_state": "SALEABLE_RESTORED",
                "confirmed_on": "2026-09-08",
                "source": "SELLER_CONFIRMED_BOT",
            },
            self.repository.calls[0],
        )
        self.assertTrue(confirmed["read_only_ozon"])
        self.assertFalse(confirmed["executed"])
        self.assertIn("само по себе не меняет прибыль", confirmed["message"])

    def test_non_saleable_is_recorded_as_explicit_local_fact(self):
        self._enter_identity()
        selected = self.service.select_state(
            self.user_id,
            "NON_SALEABLE",
        )
        self.assertFalse(selected["error"])
        confirmed = self.service.confirm(self.user_id)
        self.assertFalse(confirmed["error"])
        self.assertEqual("NON_SALEABLE", self.repository.calls[0]["recovery_state"])
        self.assertTrue(confirmed["read_only_ozon"])

    def test_status_cannot_be_inferred_without_seller_selection(self):
        self._enter_identity()
        result = self.service.confirm(self.user_id)
        self.assertTrue(result["error"])
        self.assertEqual(
            "RETURN_INVENTORY_CONFIRMATION_INVALID",
            result["code"],
        )
        self.assertEqual([], self.repository.calls)

    def test_invalid_identity_fails_closed_without_record(self):
        self.service.open_menu(self.user_id)
        result = self.service.handle_text(
            self.user_id,
            "1001736969 | 0239984545-0031-1 | hook-2",
        )
        self.assertFalse(result["error"])
        self.assertTrue(result["handled"])
        self.assertEqual([], self.repository.calls)

    def test_cancel_never_records_inventory_evidence(self):
        self._enter_identity()
        self.service.select_state(self.user_id, "SALEABLE_RESTORED")
        result = self.service.cancel(self.user_id)
        self.assertFalse(result["error"])
        self.assertEqual([], self.repository.calls)
        follow_up = self.service.confirm(self.user_id)
        self.assertTrue(follow_up["error"])
        self.assertEqual([], self.repository.calls)

    def test_unknown_state_fails_closed(self):
        self._enter_identity()
        result = self.service.select_state(
            self.user_id,
            "ReturnedToOzon",
        )
        self.assertTrue(result["error"])
        self.assertEqual([], self.repository.calls)


if __name__ == "__main__":
    unittest.main()
