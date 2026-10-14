from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from telegram_app_layer.telegram_bot_service import TelegramBotService


class _BlockingAdapter:
    def __init__(self, expected_calls=1):
        self.release = Event()
        self.expected_calls = expected_calls
        self.first_started = Event()
        self.started = Event()
        self.lock = Lock()
        self.calls = []

    def handle_button(self, callback, user_id=None):
        with self.lock:
            self.calls.append((str(user_id), str(callback)))
            self.first_started.set()
            if len(self.calls) >= self.expected_calls:
                self.started.set()
        if not self.release.wait(timeout=3):
            raise TimeoutError("test adapter was not released")
        return {
            "error": False,
            "message": "calculated",
            "read_only": True,
            "executed": False,
        }


def test_identical_calculation_callback_is_rejected_while_first_is_running(monkeypatch):
    monkeypatch.setattr(
        TelegramBotService,
        "_resolve_tenant_scope",
        staticmethod(lambda user_id: f"{user_id}::store-a"),
    )
    adapter = _BlockingAdapter()
    bot = TelegramBotService(adapter)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bot.on_callback, "seller-a", "period_profit:28D")
        assert adapter.started.wait(timeout=1)

        duplicate = bot.on_callback("seller-a", "period_profit:28D")
        assert duplicate["code"] == "TELEGRAM_CALCULATION_ALREADY_RUNNING"
        assert len(adapter.calls) == 1

        adapter.release.set()
        assert first.result(timeout=1)["message"] == "calculated"

    # Cleanup is prompt: a later deliberate request can start normally.
    assert bot.on_callback("seller-a", "period_profit:28D")["message"] == "calculated"
    assert len(adapter.calls) == 2


def test_same_callback_for_another_store_is_not_coalesced(monkeypatch):
    active_store = {"value": "store-a"}
    monkeypatch.setattr(
        TelegramBotService,
        "_resolve_tenant_scope",
        staticmethod(lambda user_id: f"{user_id}::{active_store['value']}"),
    )
    adapter = _BlockingAdapter(expected_calls=2)
    bot = TelegramBotService(adapter)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bot.on_callback, "seller-a", "period_profit:28D")
        assert adapter.first_started.wait(timeout=1)
        active_store["value"] = "store-b"
        second = pool.submit(bot.on_callback, "seller-a", "period_profit:28D")
        assert adapter.started.wait(timeout=1)
        assert len(adapter.calls) == 2
        adapter.release.set()
        assert first.result(timeout=1)["message"] == "calculated"
        assert second.result(timeout=1)["message"] == "calculated"


def test_different_period_callbacks_for_same_store_run_independently(monkeypatch):
    monkeypatch.setattr(
        TelegramBotService,
        "_resolve_tenant_scope",
        staticmethod(lambda user_id: f"{user_id}::store-a"),
    )
    adapter = _BlockingAdapter(expected_calls=2)
    bot = TelegramBotService(adapter)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bot.on_callback, "seller-a", "period_profit:7D")
        assert adapter.first_started.wait(timeout=1)
        second = pool.submit(bot.on_callback, "seller-a", "period_profit:28D")
        assert adapter.started.wait(timeout=1)
        assert {callback for _, callback in adapter.calls} == {
            "period_profit:7D",
            "period_profit:28D",
        }
        adapter.release.set()
        assert first.result(timeout=1)["message"] == "calculated"
        assert second.result(timeout=1)["message"] == "calculated"


def test_same_callback_for_another_user_is_not_coalesced(monkeypatch):
    monkeypatch.setattr(
        TelegramBotService,
        "_resolve_tenant_scope",
        staticmethod(lambda user_id: f"{user_id}::store-a"),
    )
    adapter = _BlockingAdapter(expected_calls=2)
    bot = TelegramBotService(adapter)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bot.on_callback, "seller-a", "period_profit:28D")
        assert adapter.first_started.wait(timeout=1)
        second = pool.submit(bot.on_callback, "seller-b", "period_profit:28D")
        assert adapter.started.wait(timeout=1)
        assert {user_id for user_id, _ in adapter.calls} == {
            "seller-a",
            "seller-b",
        }
        adapter.release.set()
        assert first.result(timeout=1)["message"] == "calculated"
        assert second.result(timeout=1)["message"] == "calculated"


def test_calculation_callback_detection_excludes_custom_period_setup():
    assert TelegramBotService._is_calculation_callback("period_profit:28D")
    assert TelegramBotService._is_calculation_callback(
        "period_profit_sku:3921245627:28D"
    )
    assert TelegramBotService._is_calculation_callback(
        "experimental_store_economics:28D"
    )
    assert not TelegramBotService._is_calculation_callback("period_profit:custom")
    assert not TelegramBotService._is_calculation_callback(
        "period_profit_sku:3921245627:custom"
    )
    assert not TelegramBotService._is_calculation_callback(
        "experimental_store_economics:custom"
    )


def test_inflight_key_is_released_when_calculation_raises(monkeypatch):
    monkeypatch.setattr(
        TelegramBotService,
        "_resolve_tenant_scope",
        staticmethod(lambda user_id: f"{user_id}::store-a"),
    )

    class _FailOnceAdapter:
        def __init__(self):
            self.calls = 0

        def handle_button(self, callback, user_id=None):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("expected test failure")
            return {"error": False, "message": "recovered"}

    adapter = _FailOnceAdapter()
    bot = TelegramBotService(adapter)

    try:
        bot.on_callback("seller-a", "period_profit:7D")
    except RuntimeError:
        pass
    else:
        raise AssertionError("the first calculation should fail")

    assert bot.on_callback("seller-a", "period_profit:7D")["message"] == "recovered"
    assert adapter.calls == 2
