import time
from threading import Lock

import requests


class OzonPerformanceClient:
    BASE_URL = "https://api-performance.ozon.ru"

    def __init__(self, client_id, client_secret, session=None):
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.session = session or requests
        self._token = None
        self._token_expires_at = 0.0
        self._token_lock = Lock()

    def test_connection(self):
        return self._access_token(force=True)

    def get_sku_expenses(self, date_from, date_to):
        token = self._access_token()
        if token.get("error") is True:
            return token
        response = self._request(
            "post",
            "/api/client/statistics/products/sku",
            token["access_token"],
            json={"campaignIds": [], "dateFrom": str(date_from), "dateTo": str(date_to)},
        )
        if response.get("status_code") == 401:
            token = self._access_token(force=True)
            if token.get("error") is True:
                return token
            response = self._request(
                "post",
                "/api/client/statistics/products/sku",
                token["access_token"],
                json={"campaignIds": [], "dateFrom": str(date_from), "dateTo": str(date_to)},
            )
        return response

    def _access_token(self, force=False):
        if not force and self._token and time.monotonic() < self._token_expires_at:
            return {"error": False, "access_token": self._token, "cache_hit": True}
        with self._token_lock:
            return self._access_token_locked(force=force)

    def _access_token_locked(self, force=False):
        if not force and self._token and time.monotonic() < self._token_expires_at:
            return {"error": False, "access_token": self._token, "cache_hit": True}
        if not self.client_id or not self.client_secret:
            return {"error": True, "code": "OZON_PERFORMANCE_CREDENTIALS_MISSING"}
        result = self._request(
            "post",
            "/api/client/token",
            None,
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        token = str(result.get("access_token") or "").strip() if isinstance(result, dict) else ""
        if result.get("error") is True or not token:
            return {"error": True, "code": "OZON_PERFORMANCE_AUTH_UNAVAILABLE"}
        try:
            lifetime = max(60.0, float(result.get("expires_in") or 1800.0) - 30.0)
        except (TypeError, ValueError, OverflowError):
            lifetime = 1770.0
        self._token = token
        self._token_expires_at = time.monotonic() + lifetime
        return {"error": False, "access_token": token, "cache_hit": False}

    def _request(self, method, endpoint, token, **kwargs):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            response = getattr(self.session, method)(
                self.BASE_URL + endpoint,
                headers=headers,
                timeout=30,
                **kwargs,
            )
        except requests.exceptions.RequestException:
            return {"error": True, "code": "OZON_PERFORMANCE_DEPENDENCY_UNAVAILABLE"}
        if response.status_code >= 400:
            return {
                "error": True,
                "code": "OZON_PERFORMANCE_HTTP_" + str(response.status_code),
                "status_code": response.status_code,
            }
        try:
            result = response.json()
        except (TypeError, ValueError):
            return {"error": True, "code": "OZON_PERFORMANCE_RESPONSE_INVALID"}
        if not isinstance(result, dict):
            return {"error": True, "code": "OZON_PERFORMANCE_RESPONSE_INVALID"}
        return result
