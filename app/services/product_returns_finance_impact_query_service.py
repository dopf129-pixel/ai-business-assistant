from datetime import datetime, timedelta, timezone


class ProductReturnsFinanceImpactQueryService:
    """Resolve product identity into observed returns finance impact."""

    DEFAULT_PERIOD_DAYS = 30

    def __init__(
        self,
        product_service,
        attribution_query_service,
        period_days=DEFAULT_PERIOD_DAYS,
        now_provider=None,
    ):
        self.product_service = product_service
        self.attribution_query_service = attribution_query_service
        self.period_days = max(1, int(period_days))
        self.now_provider = (
            now_provider
            or (lambda: datetime.now(timezone.utc))
        )

    def query(self, request):
        requested_sku = self._extract_sku(request)
        if not requested_sku:
            return self._error(
                "SKU_REQUIRED",
                None,
                "SKU не указан",
                ["sku"],
            )

        product = self._find_product(requested_sku)
        if product is None:
            return self._error(
                "SKU_NOT_FOUND",
                requested_sku,
                "SKU не найден",
                ["sku"],
            )

        offer_id = product.get("offer_id")
        finance_sku = product.get("sku")
        if offer_id is None:
            return self._error(
                "OFFER_ID_MISSING",
                requested_sku,
                "offer_id товара не найден",
                ["offer_id"],
                product,
            )
        if finance_sku is None:
            return self._error(
                "FINANCE_SKU_MISSING",
                requested_sku,
                "Внутренний Ozon SKU не найден",
                ["finance_sku"],
                product,
            )

        since, to = self._period()
        result = self.attribution_query_service.query(
            sku=str(offer_id),
            finance_sku=str(finance_sku),
            since=since,
            to=to,
        )
        if not isinstance(result, dict):
            return self._error(
                "RETURNS_FINANCE_UNAVAILABLE",
                requested_sku,
                "Финансовое влияние возвратов недоступно",
                ["returns_finance"],
                product,
            )

        output = dict(result)
        output.update({
            "product_id": product.get("product_id"),
            "sku": str(offer_id),
            "finance_sku": str(finance_sku),
            "requested_sku": requested_sku,
            "period_days": self.period_days,
            "period_complete_days": True,
        })
        return output

    def _period(self):
        now = self.now_provider()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        end = datetime(
            now.year,
            now.month,
            now.day,
            tzinfo=timezone.utc,
        )
        start = end - timedelta(days=self.period_days)
        return (
            start.isoformat().replace("+00:00", "Z"),
            end.isoformat().replace("+00:00", "Z"),
        )

    def _extract_sku(self, request):
        if isinstance(request, dict):
            value = request.get("sku")
        else:
            value = request
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _find_product(self, sku):
        products = self.product_service.load_products()
        for product in products or []:
            normalized = self._normalize_product(product)
            if normalized is None:
                continue
            if sku in {
                str(normalized.get("offer_id") or ""),
                str(normalized.get("sku") or ""),
            }:
                return normalized
        return None

    def _normalize_product(self, product):
        if isinstance(product, dict):
            if (
                product.get("offer_id") is None
                and product.get("sku") is None
            ):
                return None
            return dict(product)

        try:
            return {
                "product_id": product[0],
                "offer_id": product[1],
                "sku": product[2],
            }
        except (TypeError, IndexError):
            return None

    def _error(
        self,
        code,
        sku,
        message,
        missing_data,
        product=None,
    ):
        product = product or {}
        return {
            "error": True,
            "code": code,
            "product_id": product.get("product_id"),
            "sku": sku,
            "message": message,
            "complete": False,
            "missing_data": list(missing_data),
        }
