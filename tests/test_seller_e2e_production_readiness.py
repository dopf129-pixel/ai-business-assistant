from cryptography.fernet import Fernet

from services.ozon_account_repository import OzonAccountRepository
from services.ozon_account_service import OzonAccountService
from services.tenant_context import get_current_tenant_user_id
from telegram_app_layer.telegram_bot_service import TelegramBotService
from telegram_app_layer.telegram_command_service import TelegramCommandService
from telegram_app_layer.telegram_runner import TelegramRunner


class _RecordingHistory:
    def __init__(self):
        self.entries = []

    def add(self, user_id, text):
        self.entries.append((user_id, text))


class _RecordingContext:
    def __init__(self):
        self.updates = []

    def update(self, user_id, key, value):
        self.updates.append((user_id, key, value))


class _Adapter:
    def __init__(self):
        self.text_calls = []

    def get_start_response(self, user_id=None):
        return {"error": False, "message": "start"}

    def handle_text(self, text, user_id=None):
        self.text_calls.append((user_id, text))
        return {"error": False, "message": str(text)}

    def handle_button(self, callback, user_id=None):
        return {"error": False, "message": str(callback)}


class _ReadOnlyOzonClient:
    def __init__(self, probe_calls):
        self.probe_calls = probe_calls

    def get_products(self, limit=1):
        self.probe_calls.append(("get_products", limit))
        return {"error": False, "items": []}


def _build_runner(ozon_account_service=None):
    adapter = _Adapter()
    command_service = TelegramCommandService(
        adapter,
        ozon_account_service=ozon_account_service,
    )
    bot_service = TelegramBotService(
        adapter,
        command_service,
    )
    runner = TelegramRunner(bot_service)
    runner.history_service = _RecordingHistory()
    runner.context_service = _RecordingContext()
    return runner, adapter


def test_ozon_connect_command_redacts_credentials_from_assistant_state_and_survives_restart(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    master_key = Fernet.generate_key().decode("utf-8")
    account_db = tmp_path / "accounts.db"
    credentials_seen = []
    probe_calls = []

    def client_factory(client_id, api_key):
        credentials_seen.append((client_id, api_key))
        return _ReadOnlyOzonClient(probe_calls)

    repository = OzonAccountRepository(
        master_key=master_key,
        db_name=account_db,
    )
    service = OzonAccountService(
        repository=repository,
        client_factory=client_factory,
    )
    runner, _adapter = _build_runner(service)

    result = runner.receive_message(
        "seller-a",
        "  /OZON_CONNECT client-123 api-secret-value  ",
    )

    assert result["error"] is False
    assert result["status"] == "OZON_ACCOUNT_CONNECTED"
    assert result["read_only_ozon"] is True
    assert result["executed_ozon"] is False
    assert credentials_seen == [("client-123", "api-secret-value")]
    assert probe_calls == [("get_products", 1)]
    assert runner.history_service.entries == [
        ("seller-a", "Сообщение: /ozon_connect [REDACTED]")
    ]
    assert runner.context_service.updates == [
        ("seller-a", "last_message", "/ozon_connect [REDACTED]"),
        ("seller-a", "current_task", "/ozon_connect [REDACTED]"),
    ]
    assert "api-secret-value" not in str(runner.history_service.entries)
    assert "api-secret-value" not in str(runner.context_service.updates)
    assert "client-123" not in str(runner.history_service.entries)
    assert "client-123" not in str(runner.context_service.updates)
    assert b"api-secret-value" not in account_db.read_bytes()
    assert get_current_tenant_user_id() is None

    restarted_repository = OzonAccountRepository(
        master_key=master_key,
        db_name=account_db,
    )
    restarted_service = OzonAccountService(
        repository=restarted_repository,
        client_factory=client_factory,
    )
    status = restarted_service.status("seller-a")

    assert status["error"] is False
    assert status["status"] == "OZON_ACCOUNT_CONNECTED"
    assert status["connected"] is True
    assert status["client_id_masked"] == "cli***"
    assert "api-secret-value" not in str(status)
    assert probe_calls == [("get_products", 1)]


def test_normal_seller_message_is_stored_unchanged_and_dispatched_in_tenant():
    runner, adapter = _build_runner()
    text = "Прибыль за период"

    result = runner.receive_message("seller-a", text)

    assert result == {"error": False, "message": text}
    assert runner.history_service.entries == [
        ("seller-a", "Сообщение: Прибыль за период")
    ]
    assert runner.context_service.updates == [
        ("seller-a", "last_message", text),
        ("seller-a", "current_task", text),
    ]
    assert adapter.text_calls == [("seller-a", text)]
    assert get_current_tenant_user_id() is None


def test_ozon_connect_redaction_only_applies_to_leading_command_token():
    assert TelegramRunner._safe_message_for_storage(
        "/ozon_connect client secret"
    ) == "/ozon_connect [REDACTED]"
    assert TelegramRunner._safe_message_for_storage(
        "  /OZON_CONNECT client secret  "
    ) == "/ozon_connect [REDACTED]"
    assert TelegramRunner._safe_message_for_storage(
        "/ozon_connect"
    ) == "/ozon_connect [REDACTED]"

    ordinary = "Покажи подсказку: /ozon_connect CLIENT_ID API_KEY"
    assert TelegramRunner._safe_message_for_storage(ordinary) == ordinary
