from api.ozon_client import OzonClient


class PeriodProfitIdentityOzonClient(OzonClient):
    """Bound the optional FBO identity fallback used only by Period Profit.

    Historical finance identity recovery is secondary evidence. It must never keep
    a Telegram request blocked for the normal 30s x retry budget used by broader
    Ozon reads. All calls remain READ-ONLY and preserve the parent's response
    validation; only the network budget is tightened for this dedicated client.
    """

    IDENTITY_TIMEOUT_SECONDS = 6
    IDENTITY_MAX_ATTEMPTS = 1

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        return super()._post(
            endpoint,
            data,
            timeout=min(float(timeout), float(self.IDENTITY_TIMEOUT_SECONDS)),
            max_attempts=min(int(max_attempts), int(self.IDENTITY_MAX_ATTEMPTS)),
        )
