import asyncio

from telegram_app_layer.telegram_api_bot import _run_sync_with_stall_notice


class _Progress:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, reply_markup=None):
        self.edits.append(text)


def test_stall_watchdog_marks_slow_callback_and_keeps_result():
    progress = _Progress()

    def slow():
        import time
        time.sleep(0.03)
        return {"error": False, "text": "done"}

    result = asyncio.run(
        _run_sync_with_stall_notice(
            slow,
            progress_message=progress,
            stall_seconds=0.005,
        )
    )

    assert result["text"] == "done"
    assert len(progress.edits) == 1
    assert "задерживается дольше обычного" in progress.edits[0]


def test_stall_watchdog_does_not_warn_for_fast_callback():
    progress = _Progress()

    result = asyncio.run(
        _run_sync_with_stall_notice(
            lambda: {"error": False, "text": "done"},
            progress_message=progress,
            stall_seconds=0.2,
        )
    )

    assert result["text"] == "done"
    assert progress.edits == []


def test_stall_watchdog_returns_controlled_timeout_instead_of_waiting_forever():
    progress = _Progress()

    def stuck():
        import time
        time.sleep(0.08)
        return {"error": False, "text": "too late"}

    result = asyncio.run(
        _run_sync_with_stall_notice(
            stuck,
            progress_message=progress,
            stall_seconds=0.005,
            give_up_seconds=0.015,
        )
    )

    assert result["error"] is True
    assert result["code"] == "TELEGRAM_CALLBACK_TIMEOUT"
    assert "остановил ожидание" in result["message"]
    assert len(progress.edits) == 1
