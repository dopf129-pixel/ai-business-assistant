from api.ozon_performance_client import OzonPerformanceClient
from services.ozon_account_repository import make_store_tenant_scope
from services.ozon_performance_account_repository import OzonPerformanceAccountRepository


class OzonPerformanceAccountService:
    def __init__(self, repository=None, client_factory=None):
        self.repository = repository or OzonPerformanceAccountRepository()
        self.client_factory = client_factory or OzonPerformanceClient

    def connect(self, user_id, client_id, client_secret):
        seller_client = self.repository.active_client_id(user_id)
        if not seller_client:
            return {"error": False, "message": "Сначала подключите магазин командой /ozon_connect."}
        client_id = str(client_id or "").strip()
        client_secret = str(client_secret or "").strip()
        if not client_id or not client_secret:
            return self.usage()
        probe = self.client_factory(client_id, client_secret).test_connection()
        if not isinstance(probe, dict) or probe.get("error") is True:
            return {"error": False, "status": "OZON_PERFORMANCE_CONNECTION_FAILED", "message": "Ozon не подтвердил Performance API доступ. Проверьте Client ID и Client Secret; ничего не сохранено."}
        saved = self.repository.save_performance(
            make_store_tenant_scope(user_id, seller_client), client_id, client_secret
        )
        if saved.get("error") is True:
            return {"error": True, "code": saved.get("code"), "message": "Не удалось безопасно сохранить рекламный доступ."}
        return {"error": False, "status": "OZON_PERFORMANCE_CONNECTED", "message": "Performance API подключён к активному магазину. Реклама по SKU будет учитываться в расчёте прибыли."}

    @staticmethod
    def usage():
        return {
            "error": False,
            "status": "OZON_PERFORMANCE_INPUT_REQUIRED",
            "message": "Подключение рекламы: /ozon_ads_connect PERFORMANCE_CLIENT_ID CLIENT_SECRET. Реквизиты создаются в Ozon → Настройки → API-ключи → Performance API.",
        }
