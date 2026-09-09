from api.ozon_client import OzonClient
from services.ozon_account_repository import OzonAccountRepository


class OzonAccountService:
    def __init__(self, repository=None, client_factory=None):
        self.repository = repository or OzonAccountRepository()
        self.client_factory = client_factory or (
            lambda client_id, api_key: OzonClient(
                client_id=client_id,
                api_key=api_key,
            )
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
                self.repository.delete(user_key)
            except Exception:
                pass
            return self._storage_error()

        return {
            "error": False,
            "status": "OZON_ACCOUNT_CONNECTED",
            "message": (
                "Кабинет Ozon подключён. Client ID: "
                + self.repository._mask_client_id(client_key)
                + ". API Key сохранён в зашифрованном локальном хранилище и не будет показан обратно."
            ),
            "client_id_masked": self.repository._mask_client_id(client_key),
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
                    "Кабинет Ozon подключён. Client ID: "
                    + str(status.get("client_id_masked") or "***")
                    + "."
                ),
                "connected": True,
                "client_id_masked": status.get("client_id_masked"),
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

    def disconnect(self, user_id):
        result = self.repository.delete(user_id)
        if result.get("error") is True:
            return {
                "error": True,
                "code": "OZON_ACCOUNT_STORAGE_UNAVAILABLE",
                "message": "Не удалось отключить кабинет Ozon.",
                "read_only_ozon": True,
                "executed_ozon": False,
            }
        return {
            "error": False,
            "status": "OZON_ACCOUNT_DISCONNECTED",
            "message": "Кабинет Ozon отключён. Локально сохранённый API Key удалён.",
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
            "message": (
                "Не удалось безопасно сохранить подключение. "
                "Проверьте OZON_CREDENTIAL_MASTER_KEY и локальное хранилище на сервере."
            ),
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _invalid():
        return {
            "error": False,
            "status": "OZON_ACCOUNT_INPUT_REQUIRED",
            "message": (
                "Подключение: /ozon_connect CLIENT_ID API_KEY. "
                "Создайте read-only Seller API ключ в кабинете Ozon и не пересылайте его другим людям."
            ),
            "read_only_ozon": True,
            "executed_ozon": False,
        }

    @staticmethod
    def _connection_error():
        return {
            "error": False,
            "status": "OZON_ACCOUNT_CONNECTION_FAILED",
            "message": (
                "Ozon не подтвердил доступ с этими реквизитами. "
                "Проверьте Client ID и API Key. Ничего не сохранено."
            ),
            "read_only_ozon": True,
            "executed_ozon": False,
        }
