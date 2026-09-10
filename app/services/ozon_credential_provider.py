from config import OZON_CLIENT_ID, OZON_API_KEY
from services.ozon_account_repository import OzonAccountRepository
from services.tenant_context import get_current_tenant_user_id


class OzonCredentialProvider:
    def __init__(self, repository=None):
        self.repository = repository or OzonAccountRepository()

    def get_credentials(self):
        user_id = get_current_tenant_user_id()
        if user_id:
            account = self.repository.get(user_id)
            if not account:
                return {
                    "client_id": None,
                    "api_key": None,
                    "source": "TENANT_ACCOUNT_MISSING",
                    "tenant_user_id": user_id,
                }
            return {
                "client_id": account.get("client_id"),
                "api_key": account.get("api_key"),
                "source": "TENANT_ACCOUNT",
                "tenant_user_id": user_id,
            }

        return {
            "client_id": OZON_CLIENT_ID,
            "api_key": OZON_API_KEY,
            "source": "LEGACY_ENV",
            "tenant_user_id": None,
        }
