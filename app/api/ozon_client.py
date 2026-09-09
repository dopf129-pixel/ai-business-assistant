from api.base_ozon_client import OzonClient as BaseOzonClient
from services.ozon_credential_provider import OzonCredentialProvider


class OzonClient(BaseOzonClient):
    """Tenant-aware facade over the existing read-only Ozon client.

    Explicit credentials are used only for connection validation. Otherwise
    credentials are resolved on every request from the current Telegram tenant.
    A tenant with no connected account never falls back to process-wide env keys.
    """

    def __init__(self, client_id=None, api_key=None, credential_provider=None):
        self._explicit_client_id = self._text(client_id)
        self._explicit_api_key = self._text(api_key)
        self._credential_provider = credential_provider or OzonCredentialProvider()
        self._legacy_client_id = None
        self._legacy_api_key = None
        super().__init__()

    @property
    def client_id(self):
        if self._explicit_client_id:
            return self._explicit_client_id
        credentials = self._credentials()
        return self._text(credentials.get("client_id"))

    @client_id.setter
    def client_id(self, value):
        self._legacy_client_id = self._text(value)

    @property
    def api_key(self):
        if self._explicit_api_key:
            return self._explicit_api_key
        credentials = self._credentials()
        return self._text(credentials.get("api_key"))

    @api_key.setter
    def api_key(self, value):
        self._legacy_api_key = self._text(value)

    def credential_source(self):
        if self._explicit_client_id or self._explicit_api_key:
            return "EXPLICIT_VALIDATION"
        return str(self._credentials().get("source") or "UNKNOWN")

    def _credentials(self):
        try:
            result = self._credential_provider.get_credentials()
        except Exception:
            return {
                "client_id": None,
                "api_key": None,
                "source": "TENANT_CREDENTIAL_PROVIDER_UNAVAILABLE",
            }
        if not isinstance(result, dict):
            return {
                "client_id": None,
                "api_key": None,
                "source": "TENANT_CREDENTIAL_PROVIDER_INVALID",
            }
        return result

    @staticmethod
    def _text(value):
        text = str(value or "").strip()
        return text or None
