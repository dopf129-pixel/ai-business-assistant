from config import OZON_CLIENT_ID, OZON_API_KEY
from services.ozon_account_repository import OzonAccountRepository, split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class OzonCredentialProvider:
    def __init__(self, repository=None):
        self.repository = repository or OzonAccountRepository()

    def get_credentials(self):
        tenant_scope = get_current_tenant_user_id()
        if tenant_scope:
            account = self.repository.get(tenant_scope)
            if not account:
                return {
                    "client_id": None,
                    "api_key": None,
                    "source": "TENANT_ACCOUNT_MISSING",
                    "tenant_user_id": tenant_scope,
                }
            _, scoped_client_id = split_store_tenant_scope(tenant_scope)
            return {
                "client_id": account.get("client_id"),
                "api_key": account.get("api_key"),
                # Preserve the established contract for legacy per-user tenant
                # scopes while exposing the stronger store-scoped provenance.
                "source": "TENANT_STORE_ACCOUNT" if scoped_client_id else "TENANT_ACCOUNT",
                "tenant_user_id": tenant_scope,
            }

        return {
            "client_id": OZON_CLIENT_ID,
            "api_key": OZON_API_KEY,
            "source": "LEGACY_ENV",
            "tenant_user_id": None,
        }
