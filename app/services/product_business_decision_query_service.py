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
        economics_context = self._economics_context(
            economics_metrics
        )

        if decision.get("decision_type") == self.CODE_INSUFFICIENT_DATA:
            return {
                "error": False,
                "code": self.CODE_INSUFFICIENT_DATA,
                **decision,
                **economics_context
            }

        return {
            "error": False,
            "code": None,
            **decision,
            **economics_context
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

            if sku in {
                str(normalized.get("offer_id") or ""),
                str(normalized.get("sku") or ""),
            }:
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

        impact = result.get("returns_finance_impact")
        basis = None
        reserve = None
        coverage = None

        if result.get("risk_adjusted_profit_per_unit") is not None:
            profit = result.get("risk_adjusted_profit_per_unit")
            margin = result.get("risk_adjusted_margin_percent")
            reserve = result.get("returns_cost_per_delivered_unit")
            basis = "CONFIRMED_RETURNS"
        elif (
            result.get("returns_estimate_available")
            and result.get("estimated_profit_per_unit") is not None
        ):
            profit = result.get("estimated_profit_per_unit")
            margin = result.get("estimated_margin_percent")
            reserve = result.get("estimated_returns_cost_per_unit")
            coverage = result.get(
                "returns_estimate_coverage_percent"
            )
            basis = "ESTIMATED_RETURNS"
        elif isinstance(impact, dict):
            profit = None
            margin = None
            if "returns" not in missing_data:
                missing_data.append("returns")
            basis = "RETURNS_UNAVAILABLE"
        else:
            profit = result.get("net_profit_per_unit")
            margin = result.get("margin_percent")

        return {
            "product_id": result.get("product_id", product_id),
            "sku": result.get("sku", sku),
            "net_profit_per_unit": profit,
            "margin_percent": margin,
            "economics_basis": basis,
            "returns_reserve_per_unit": reserve,
            "returns_coverage_percent": coverage,
            "missing_data": missing_data
        }

    def _economics_context(self, economics):
        if not isinstance(economics, dict):
            return {}

        basis = economics.get("economics_basis")
        if basis is None:
            return {}

        return {
            "economics_basis": basis,
            "decision_profit_per_unit": economics.get(
                "net_profit_per_unit"
            ),
            "decision_margin_percent": economics.get(
                "margin_percent"
            ),
            "returns_reserve_per_unit": economics.get(
                "returns_reserve_per_unit"
            ),
            "returns_coverage_percent": economics.get(
                "returns_coverage_percent"
            ),
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
