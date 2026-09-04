from api.ozon_client import OzonClient
from database import save_product, get_products


class ProductService:

    def __init__(self):
        self.ozon = OzonClient()

    def update_products(self):

        result = self.refresh_products_for_period_profit()

        if result.get("error"):
            return 0

        return int(result.get("count") or 0)

    def refresh_products_for_period_profit(
        self,
        limit=100,
        max_pages=200,
    ):
        """Refresh the complete read-only Ozon product catalog with cursor pagination."""

        try:
            limit = int(limit)
            max_pages = int(max_pages)
        except (TypeError, ValueError):
            return self._refresh_error(
                "PERIOD_PROFIT_PRODUCT_CATALOG_PAGINATION_INVALID"
            )

        if limit <= 0 or limit > 1000 or max_pages <= 0:
            return self._refresh_error(
                "PERIOD_PROFIT_PRODUCT_CATALOG_PAGINATION_INVALID"
            )

        post = getattr(self.ozon, "_post", None)
        if not callable(post):
            return self._refresh_error(
                "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"
            )

        last_id = ""
        seen_last_ids = set()
        count = 0

        for page_number in range(1, max_pages + 1):
            payload = {
                "filter": {},
                "limit": limit,
            }
            if last_id:
                payload["last_id"] = last_id

            try:
                response = post(
                    "/v3/product/list",
                    payload,
                )
            except Exception:
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"
                )

            if not isinstance(response, dict):
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_RESPONSE_INVALID"
                )
            if response.get("error") is True:
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_API_UNAVAILABLE"
                )

            result = response.get("result")
            if not isinstance(result, dict):
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_RESPONSE_INVALID"
                )

            items = result.get("items")
            if not isinstance(items, list):
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_RESPONSE_INVALID"
                )

            for product in items:
                if not isinstance(product, dict) or product.get("product_id") is None:
                    return self._refresh_error(
                        "PERIOD_PROFIT_PRODUCT_CATALOG_RESPONSE_INVALID"
                    )
                try:
                    save_product(product)
                except Exception:
                    return self._refresh_error(
                        "PERIOD_PROFIT_PRODUCT_CATALOG_STORAGE_UNAVAILABLE"
                    )
                count += 1

            next_last_id = str(
                result.get("last_id")
                or ""
            ).strip()

            if not next_last_id or len(items) < limit:
                return {
                    "error": False,
                    "status": "PERIOD_PROFIT_PRODUCT_CATALOG_REFRESHED",
                    "count": count,
                    "pages_loaded": page_number,
                    "complete": True,
                    "read_only": True,
                    "executed": False,
                }

            if next_last_id == last_id or next_last_id in seen_last_ids:
                return self._refresh_error(
                    "PERIOD_PROFIT_PRODUCT_CATALOG_CURSOR_INVALID"
                )

            seen_last_ids.add(next_last_id)
            last_id = next_last_id

        return self._refresh_error(
            "PERIOD_PROFIT_PRODUCT_CATALOG_PAGE_LIMIT_REACHED"
        )

    def load_products(self):

        return get_products()

    @staticmethod
    def _refresh_error(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_PRODUCT_CATALOG_UNAVAILABLE",
            "complete": False,
            "count": None,
            "read_only": True,
            "executed": False,
        }
