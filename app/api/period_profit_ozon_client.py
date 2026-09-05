import time

from api.ozon_client import OzonClient


class PeriodProfitOzonClient(OzonClient):
    """Read-only Ozon client with an extra retry layer for transient HTTP failures."""

    TRANSIENT_STATUS_CODES = {408, 500, 502, 503, 504}

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        result = None

        for attempt in range(1, int(max_attempts) + 1):
            result = super()._post(
                endpoint,
                data,
                timeout=timeout,
                max_attempts=max_attempts,
            )

            if not isinstance(result, dict) or result.get("error") is not True:
                return result

            status_code = result.get("status_code")
            if status_code not in self.TRANSIENT_STATUS_CODES:
                return result

            if attempt >= int(max_attempts):
                return result

            time.sleep(2 ** attempt)

        return result
