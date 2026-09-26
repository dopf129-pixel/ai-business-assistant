from api.ozon_client import OzonClient
from services.ozon_account_repository import OzonAccountRepository, make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


class OzonAccountService:
    def __init__(self, repository=None, client_factory=None):
        self.repository = repository or OzonAccountRepository()
        self.client_factory = client_factory or (
            lambda client_id, api_key: OzonClient(client_id=client_id, api_key=api_key)
        )

    def connect(self, user_id, client_id, api_key):
        user_key = str(user_id or "").strip()
        client_key = str(client_id or "").strip()
        secret = str(api_key or "").strip()
        if not user_key or not client_key or not secret:
            return self._invalid()
        try:
            client = self.client_factory(client_key, secret)
            probe = client.get_products(limit=1)
        except Exception:
            return self._connection_error()
        if not isinstance(probe, dict) or probe.get("error") is True:
            return self._connection_error()
        display_name = self._load_display_name(client)
        token = set_current_tenant_user_id(make_store_tenant_scope(user_key, client_key))
        try:
            self._initialize_tenant_storage()
        except Exception:
            return self._storage_error()
        finally:
            reset_current_tenant_user_id(token)
        try:
            saved = self.repository.save(
                user_key, client_key, secret, display_name=display_name
            )
        except Exception:
            return self._storage_error()
        if not isinstance(saved, dict) or saved.get("error") is True:
            return self._storage_error()
        try:
            count = len(self.repository.list_accounts(user_key))
        except Exception:
            count = 1
        return {
            "error": False,
            "status": "OZON_ACCOUNT_CONNECTED",
            "message": (
                "Магазин Ozon подключён и выбран. Client ID: "
                + self.repository._mask_client_id(client_key)
                + ". Подключено магазинов: " + str(count)
                + ". Переключение: /stores. API Key сохранён зашифрованно."
            ),
            "client_id_masked": self.repository._mask_client_id(client_key),
            "account_count": count,
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    def status(self, user_id):
        try:
            status = self.repository.status(user_id)
            if not isinstance(status, dict):
                return self._status_storage_error()
            if status.get("error") is True:
                code = str(status.get("code") or "")
                if code in {
                    "OZON_ACCOUNT_MASTER_KEY_UNAVAILABLE",
                    "OZON_ACCOUNT_MASTER_KEY_MISMATCH",
                }:
                    return {
                        "error": True,
                        "code": code,
                        "status": "OZON_ACCOUNT_STORED_CREDENTIALS_UNAVAILABLE",
                        "message": (
                            "Подключение магазина уже сохранено, но бот не может "
                            "расшифровать его текущим OZON_CREDENTIAL_MASTER_KEY. "
                            "Восстановите прежний ключ из .env; не подключайте "
                            "магазин повторно."
                        ),
                        "connected": False,
                        "account_count": status.get("account_count"),
                        "read_only_ozon": True,
                        "executed_ozon": False,
                    }
                return self._status_storage_error()
            if status.get("connected") is True:
                account = self._account_with_display_name(
                    user_id, status.get("client_id")
                )
                display = (
                    account.get("display_name") if isinstance(account, dict) else None
                ) or status.get("client_id_masked") or "***"
                return {
                    "error": False,
                    "status": "OZON_ACCOUNT_CONNECTED",
                    "message": (
                        "Активный магазин Ozon: "
                        + str(display)
                        + ". Подключено магазинов: " + str(status.get("account_count") or 1)
                        + ". Переключение: /stores."
                    ),
                    "connected": True,
                    "client_id_masked": status.get("client_id_masked"),
                    "display_name": (
                        account.get("display_name")
                        if isinstance(account, dict) else None
                    ),
                    "account_count": status.get("account_count"),
                    "read_only_ozon": True,
                    "executed_ozon": False,
                }
            return {
                "error": False,
                "status": "OZON_ACCOUNT_NOT_CONNECTED",
                "message": "Кабинет Ozon не подключён. Используйте /ozon_connect CLIENT_ID API_KEY.",
                "connected": False,
                "read_only_ozon": True,
                "executed_ozon": False,
            }
        except Exception:
            return self._status_storage_error()

    def stores(self, user_id):
        accounts = self.repository.list_accounts(user_id)
        if not accounts:
            return self.status(user_id)
        buttons = []
        for account in accounts:
            account = self._with_display_name(user_id, account)
            prefix = "✓ " if account.get("active") else ""
            buttons.append({
                "text": prefix + str(
                    self._button_label(account.get("display_name"))
                    or "Магазин " + str(account.get("client_id_masked") or "***")
                ),
                "callback": "ozon_store:" + str(account.get("client_id") or ""),
            })
        return {
            "error": False,
            "message": "Выберите магазин. Все SKU, себестоимость и аналитика будут работать только в его контуре:",
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons},
            "account_count": len(accounts),
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    def _account_with_display_name(self, user_id, client_id):
        account = next((
            row for row in self.repository.list_accounts(user_id)
            if str(row.get("client_id") or "") == str(client_id or "")
        ), None)
        return self._with_display_name(user_id, account) if account else None

    def _with_display_name(self, user_id, account):
        if account.get("display_name"):
            return account
        credentials = self.repository.get(user_id, account.get("client_id"))
        if not isinstance(credentials, dict):
            return account
        try:
            client = self.client_factory(
                credentials.get("client_id"), credentials.get("api_key")
            )
            name = self._load_display_name(client)
        except Exception:
            name = None
        if not name:
            return account
        try:
            saved = self.repository.update_display_name(
                user_id, account.get("client_id"), name
            )
        except Exception:
            saved = None
        if not isinstance(saved, dict) or saved.get("updated") is not True:
            return account
        return {**account, "display_name": name}

    @staticmethod
    def _load_display_name(client):
        getter = getattr(client, "get_seller_info", None)
        if not callable(getter):
            return None
        try:
            result = getter()
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("error") is True:
            return None
        company = result.get("company")
        if not isinstance(company, dict):
            return None
        name = " ".join(str(company.get("name") or "").split())
        return name[:120] or None

    @staticmethod
    def _button_label(value):
        name = " ".join(str(value or "").split())
        if len(name) <= 52:
            return name or None
        return name[:49].rstrip() + "…"

    def select(self, user_id, client_id):
        result = self.repository.select(user_id, client_id)
        if not isinstance(result, dict) or result.get("error") is True:
            return self._storage_error()
        if result.get("selected") is not True:
            return {"error": False, "message": "Магазин не найден. Откройте /stores и выберите из списка."}
        masked = self.repository._mask_client_id(client_id)
        account = self._account_with_display_name(user_id, client_id)
        display = (
            account.get("display_name") if isinstance(account, dict) else None
        ) or masked or "***"
        return {
            "error": False,
            "status": "OZON_STORE_SELECTED",
            "message": "Выбран магазин Ozon " + str(display) + ". Данные других магазинов в расчёты не попадут.",
            "client_id_masked": masked,
            "display_name": (
                account.get("display_name") if isinstance(account, dict) else None
            ),
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    def disconnect(self, user_id):
        result = self.repository.delete(user_id)
        if result.get("error") is True:
            return {
                "error": True,
                "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
                "message": "Не удалось отключить активный магазин Ozon.",
                "read_only_ozon": True,
                "executed_ozon": False,
            }
        return {
            "error": False,
            "status": "OZON_ACCOUNT_DISCONNECTED",
            "message": "Активный магазин Ozon отключён. Если подключены другие магазины, один из них выбран автоматически.",
            "connected": False,
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _initialize_tenant_storage():
        from database import create_tables
        from services.cost_service import ProductCostService
        create_tables()
        ProductCostService()

    @staticmethod
    def _storage_error():
        return {
            "error": True,
            "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
            "message": "Не удалось безопасно сохранить подключение. Проверьте OZON_CREDENTIAL_MASTER_KEY и локальное хранилище на сервере.",
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _status_storage_error():
        return {
            "error": True,
            "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
            "status": "OZON_ACCOUNT_STATUS_UNAVAILABLE",
            "message": (
                "Не удалось прочитать сохранённое подключение. Проверьте "
                "AI_ASSISTANT_STORAGE_ROOT и права на каталог данных."
            ),
            "connected": False,
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _invalid():
        return {
            "error": False,
            "status": "OZON_ACCOUNT_INPUT_REQUIRED",
            "message": "Подключение: /ozon_connect CLIENT_ID API_KEY. Создайте read-only Seller API ключ в кабинете Ozon и не пересылайте его другим людям.",
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _connection_error():
        return {
            "error": False,
            "status": "OZON_ACCOUNT_CONNECTION_FAILED",
            "message": "Ozon не подтвердил доступ с этими реквизитами. Проверьте Client ID и API Key. Ничего не сохранено.",
            "read_only_ozon": True,
            "executed_ozon": False,
        }
