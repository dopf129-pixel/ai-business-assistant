from api.period_profit_ozon_client import PeriodProfitOzonClient


class PeriodProfitRelatedSkuOzonClient(PeriodProfitOzonClient):
    """Period Profit READ-ONLY client with old/current SKU identity lookup."""

    RELATED_SKU_ENDPOINT = "/v1/product/related-sku/get"
    RELATED_SKU_BATCH_SIZE = 200

    def get_related_skus(self, skus):
        normalized = []
        seen = set()
        for value in skus or []:
            sku = str(value or "").strip()
            if not sku or sku in seen:
                continue
            seen.add(sku)
            normalized.append(sku)

        if not normalized or len(normalized) > self.RELATED_SKU_BATCH_SIZE:
            return self._related_sku_error("OZON_RELATED_SKU_INPUT_INVALID")

        response = self._post(
            self.RELATED_SKU_ENDPOINT,
            {"sku": normalized},
            timeout=10,
            max_attempts=1,
        )
        if not isinstance(response, dict):
            return self._related_sku_error("OZON_RELATED_SKU_RESPONSE_INVALID")
        if response.get("error") is True:
            return response

        items = response.get("items")
        errors = response.get("errors")
        if not isinstance(items, list):
            return self._related_sku_error("OZON_RELATED_SKU_RESPONSE_INVALID")
        if errors is not None and not isinstance(errors, list):
            return self._related_sku_error("OZON_RELATED_SKU_RESPONSE_INVALID")

        return {
            "error": False,
            "status": "OZON_RELATED_SKU_READY",
            "items": items,
            "errors": errors or [],
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _related_sku_error(code):
        return {
            "error": True,
            "code": code,
            "status": "OZON_RELATED_SKU_UNAVAILABLE",
            "items": [],
            "read_only": True,
            "executed": False,
        }
