from api.ozon_client import OzonClient
from services.ozon_account_repository import OzonAccountRepository


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
        saved = self.repository.save(user_key, client_key, secret)
        if not isinstance(saved, dict) or saved.get("error") is True:
            return self._storage_error()
        try:
            self._initialize_tenant_storage()
        except Exception:
            try:
                self.repository.delete(user_key, client_key)
            except Exception:
                pass
            return self._storage_error()
        count = len(self.repository.list_accounts(user_key))
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
        status = self.repository.status(user_id)
        if status.get("connected") is True:
            return {
                "error": False,
                "status": "OZON_ACCOUNT_CONNECTED",
                "message": (
                    "Активный магазин Ozon: "
                    + str(status.get("client_id_masked") or "***")
                    + ". Подключено магазинов: " + str(status.get("account_count") or 1)
                    + ". Переключение: /stores."
                ),
                "connected": True,
                "client_id_masked": status.get("client_id_masked"),
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

    def stores(self, user_id):
        accounts = self.repository.list_accounts(user_id)
        if not accounts:
            return self.status(user_id)
        buttons = []
        for account in accounts:
            prefix = "✓ " if account.get("active") else ""
            buttons.append({
                "text": prefix + "Магазин " + str(account.get("client_id_masked") or "***"),
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

    def select(self, user_id, client_id):
        result = self.repository.select(user_id, client_id)
        if not isinstance(result, dict) or result.get("error") is True:
            return self._storage_error()
        if result.get("selected") is not True:
            return {"error": False, "message": "Магазин не найден. Откройте /stores и выберите из списка."}
        masked = self.repository._mask_client_id(client_id)
        return {
            "error": False,
            "status": "OZON_STORE_SELECTED",
            "message": "Выбран магазин Ozon " + str(masked or "***") + ". Данные других магазинов в расчёты не попадут.",
            "client_id_masked": masked,
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
