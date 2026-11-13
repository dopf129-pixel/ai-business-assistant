"""Regression coverage for the automatic FIFO batch rule flow (B01/B02)."""

from datetime import datetime, timezone

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


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
        runtime = TelegramFifoCostTransitionRuntimeService(
            transitions, history, now_provider=now,
        )
        started = runtime.start_new_case(
            101, IDENTITY, "Synthetic item", 0, "TOTAL_LANDED",
        )
        assert "старую итоговую себестоимость" in started["message"].lower()

        for value in ("21", "14.65", "05.11.2026", "0", "0"):
            response = _confirm_text(runtime, value)
            assert response["error"] is False, response

        # The accepted shortcut displays a preview; it must not itself confirm
        # a batch rule or apply a FIFO rate.
        preview = runtime.handle_text(101, "не знаю")
        assert preview["error"] is False, preview
        assert "провер" in preview["message"].lower()
        assert any(
            "подтверд" in button["text"].lower()
            for button in preview["keyboard"]["buttons"]
        )

        saved = transitions.list_cases(
            store_id=IDENTITY["store_id"], sku=IDENTITY["sku"],
        )["cases"][0]
        assert saved["case"]["declared_shipped_units"] is None
        assert saved["case_revision"] == 6
        assert saved["state"] == "DRAFT"
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False
    finally:
        reset_current_tenant_user_id(tenant)
