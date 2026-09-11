from api.base_ozon_client import OzonClient as BaseOzonClient
from services.ozon_credential_provider import OzonCredentialProvider


class OzonClient(BaseOzonClient):
    """Tenant-aware facade over the existing read-only Ozon client.

    Explicit credentials are used only for connection validation or deliberate
    instance overrides. Otherwise credentials are resolved on every request from
    the current Telegram tenant. A tenant with no connected account never falls
    back to process-wide env keys.
    """

    FBO_POSTINGS_V3_PAGE_SIZE = 100
    FBO_POSTINGS_V3_MAX_PAGES = 200

    def __init__(self, client_id=None, api_key=None, credential_provider=None):
        self._explicit_client_id = self._text(client_id)
        self._explicit_api_key = self._text(api_key)
        self._credential_provider = credential_provider or OzonCredentialProvider()
        self._legacy_client_id = None
        self._legacy_api_key = None
        self._initializing_base = True
        super().__init__()
        self._initializing_base = False

    @property
    def client_id(self):
        if self._explicit_client_id:
            return self._explicit_client_id
        credentials = self._credentials()
        return self._text(credentials.get("client_id"))

    @client_id.setter
    def client_id(self, value):
        value = self._text(value)
        if getattr(self, "_initializing_base", False):
            self._legacy_client_id = value
        else:
            self._explicit_client_id = value

    @property
    def api_key(self):
        if self._explicit_api_key:
            return self._explicit_api_key
        credentials = self._credentials()
        return self._text(credentials.get("api_key"))

    @api_key.setter
    def api_key(self, value):
        value = self._text(value)
        if getattr(self, "_initializing_base", False):
            self._legacy_api_key = value
        else:
            self._explicit_api_key = value

    def credential_source(self):
        if self._explicit_client_id or self._explicit_api_key:
            return "EXPLICIT_VALIDATION"
        return str(self._credentials().get("source") or "UNKNOWN")

    def get_fbo_postings(
        self,
        since,
        to,
        limit=1000,
        offset=0,
        direction="DESC",
        status="",
    ):
        """Read FBO postings through Ozon v3 while preserving the old caller contract.

        Ozon's v3 list endpoint is cursor-paginated and returns ``postings`` at
        the top level. Existing analytics callers still request offset windows
        and expect ``result.postings``. This adapter reads enough cursor pages to
        satisfy that window and normalizes the response without any Ozon writes.
        """
        try:
            requested_limit = int(limit)
            requested_offset = int(offset)
        except (TypeError, ValueError):
            return self._fbo_postings_error("OZON_FBO_POSTINGS_PAGINATION_INVALID")

        if requested_limit <= 0 or requested_offset < 0:
            return self._fbo_postings_error("OZON_FBO_POSTINGS_PAGINATION_INVALID")

        target_count = requested_offset + requested_limit
        cursor = ""
        seen_cursors = set()
        all_postings = []
        has_next = False

        filter_data = {
            "since": str(since),
            "to": str(to),
        }
        status_text = str(status or "").strip()
        if status_text:
            filter_data["status"] = [status_text]

        sort_dir = str(direction or "DESC").strip().lower()
        if sort_dir not in {"asc", "desc"}:
            return self._fbo_postings_error("OZON_FBO_POSTINGS_SORT_INVALID")

        for _ in range(self.FBO_POSTINGS_V3_MAX_PAGES):
            remaining = max(1, target_count - len(all_postings))
            page_limit = min(self.FBO_POSTINGS_V3_PAGE_SIZE, remaining)
            response = self._post(
                "/v3/posting/fbo/list",
                {
                    "cursor": cursor,
                    "filter": filter_data,
                    "limit": page_limit,
                    "sort_dir": sort_dir,
                    "translit": False,
                    "with": {
                        "analytics_data": False,
                        "financial_data": False,
                        "legal_info": False,
                    },
                },
                timeout=30,
                max_attempts=3,
            )

            if not isinstance(response, dict):
                return self._fbo_postings_error("OZON_FBO_POSTINGS_RESPONSE_INVALID")
            if response.get("error"):
                return response

            postings = response.get("postings")
            if not isinstance(postings, list):
                return self._fbo_postings_error("OZON_FBO_POSTINGS_RESPONSE_INVALID")
            all_postings.extend(postings)

            has_next = response.get("has_next") is True
            if len(all_postings) >= target_count or not has_next:
                break

            next_cursor = str(response.get("cursor") or "").strip()
            if not next_cursor or next_cursor == cursor or next_cursor in seen_cursors:
                return self._fbo_postings_error("OZON_FBO_POSTINGS_CURSOR_INVALID")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            return self._fbo_postings_error("OZON_FBO_POSTINGS_PAGE_LIMIT_REACHED")

        window = all_postings[requested_offset:target_count]
        return {
            "error": False,
            "result": {"postings": window},
            "has_next": has_next or len(all_postings) > target_count,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _fbo_postings_error(code):
        return {
            "error": True,
            "code": code,
            "message": "FBO postings недоступны",
            "read_only": True,
            "executed": False,
        }

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
