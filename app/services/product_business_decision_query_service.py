class ProductBusinessDecisionQueryService:

    CODE_SKU_REQUIRED = "SKU_REQUIRED"
    CODE_SKU_NOT_FOUND = "SKU_NOT_FOUND"
    CODE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    def __init__(
        self,
        product_service,
        sales_metrics_source,
        stock_metrics_source,
        unit_economics_query_service,
        decision_input_provider,
        decision_service
    ):
        self.product_service = product_service
        self.sales_metrics_source = sales_metrics_source
        self.stock_metrics_source = stock_metrics_source
        self.unit_economics_query_service = unit_economics_query_service
        self.decision_input_provider = decision_input_provider
        self.decision_service = decision_service

    def query(self, request):
        sku = self._extract_sku(request)

        if not sku:
            return self._error_result(
                code=self.CODE_SKU_REQUIRED,
                sku=None,
                missing_data=["sku"]
            )

        product = self._find_product(sku)

        if product is None:
            return self._error_result(
                code=self.CODE_SKU_NOT_FOUND,
                sku=sku,
                missing_data=["sku"]
            )

        product_id = product.get("product_id")

        sales_metrics = self._query_prepared_source(
            self.sales_metrics_source,
            sku
        )
        stock_metrics = self._query_prepared_source(
            self.stock_metrics_source,
            sku
        )
        economics_result = self.unit_economics_query_service.query(sku)
        economics_metrics = self._normalize_economics(
            economics_result,
            product_id=product_id,
            sku=sku
        )

        prepared = self.decision_input_provider.build(
            sales_metrics=sales_metrics,
            stock_metrics=stock_metrics,
            unit_economics=economics_metrics
        )

        decision = self.decision_service.decide(prepared)

        if decision.get("decision_type") == self.CODE_INSUFFICIENT_DATA:
            return {
                "error": False,
                "code": self.CODE_INSUFFICIENT_DATA,
                **decision
            }

        return {
            "error": False,
            "code": None,
            **decision
        }

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

            if str(normalized.get("sku")) == sku:
                return normalized

        return None

    def _normalize_product(self, product):
        if isinstance(product, dict):
            if product.get("sku") is None:
                return None
            return dict(product)

        try:
            return {
                "product_id": product[0],
                "offer_id": product[1],
                "sku": product[2]
            }
        except (TypeError, IndexError):
            return None

    def _query_prepared_source(self, source, sku):
        if source is None:
            return None

        if callable(source):
            result = source(sku)
        else:
            query = getattr(source, "query", None)
            if query is None:
                return None
            result = query(sku)

        if not isinstance(result, dict):
            return None

        if result.get("error"):
            return None

        return dict(result)

    def _normalize_economics(self, result, product_id, sku):
        if not isinstance(result, dict):
            return None

        if result.get("error"):
            return None

        missing_data = list(
            result.get("missing_data")
            or result.get("missing_fields")
            or []
        )

        return {
            "product_id": result.get("product_id", product_id),
            "sku": result.get("sku", sku),
            "net_profit_per_unit": result.get("net_profit_per_unit"),
            "margin_percent": result.get("margin_percent"),
            "missing_data": missing_data
        }

    def _error_result(self, code, sku, missing_data):
        return {
            "error": True,
            "code": code,
            "product_id": None,
            "sku": sku,
            "decision_type": self.CODE_INSUFFICIENT_DATA,
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": list(missing_data)
        }
