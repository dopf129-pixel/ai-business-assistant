from copy import deepcopy
from time import monotonic


class ProductBusinessDecisionQueryService:

    CODE_SKU_REQUIRED = "SKU_REQUIRED"
    CODE_SKU_NOT_FOUND = "SKU_NOT_FOUND"
    CODE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

    PRIORITY_ORDER = {
        "CRITICAL": 0,
        "HIGH": 1,
        "NORMAL": 2,
        "LOW": 3,
        "NONE": 4,
    }

    EVIDENCE_FIELDS = (
        "sales_source_recorded_at",
        "stock_source_recorded_at",
        "unit_economics_source_recorded_at",
        "sales_observed_at",
        "stock_observed_at",
        "unit_economics_observed_at",
    )

    def __init__(
        self,
        product_service,
        sales_metrics_source,
        stock_metrics_source,
        unit_economics_query_service,
        decision_input_provider,
        decision_service,
        decision_history_service=None,
        action_proposal_service=None,
        action_proposal_confirmation_service=None,
        cache_ttl_seconds=600,
        clock=None
    ):
        self.product_service = product_service
        self.sales_metrics_source = sales_metrics_source
        self.stock_metrics_source = stock_metrics_source
        self.unit_economics_query_service = unit_economics_query_service
        self.decision_input_provider = decision_input_provider
        self.decision_service = decision_service
        self.decision_history_service = decision_history_service
        self.action_proposal_service = action_proposal_service
        self.action_proposal_confirmation_service = (
            action_proposal_confirmation_service
        )
        self.action_task_draft_service = getattr(
            action_proposal_confirmation_service,
            "task_draft_service",
            None,
        )
        self.task_draft_review_queue_service = None
        self.task_draft_readiness_service = None
        self.cache_ttl_seconds = max(0, float(cache_ttl_seconds))
        self.clock = clock or monotonic
        self._decision_cache = {}

    def query(self, request):
        sku = self._extract_sku(request)

        if not sku:
            return self._error_result(
                code=self.CODE_SKU_REQUIRED,
                sku=None,
                missing_data=["sku"]
            )

        cached = self._cached_decision(sku)
        if cached is not None:
            return cached

        product = self._find_product(sku)

        if product is None:
            return self._error_result(
                code=self.CODE_SKU_NOT_FOUND,
                sku=sku,
                missing_data=["sku"]
            )

        result = self._with_task_draft_lifecycle(
            self._with_action_proposal(
                self._with_decision_history(
                    self._query_product(sku, product)
                )
            )
        )
        self._store_decision(sku, result)
        return deepcopy(result)

    def _query_product(self, sku, product):
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
        metrics_context = self._metrics_context(prepared)
        evidence_context = self._evidence_context(prepared)

        if decision.get("decision_type") == self.CODE_INSUFFICIENT_DATA:
            return {
                "error": False,
                "code": self.CODE_INSUFFICIENT_DATA,
                **decision,
                **metrics_context,
                **economics_context,
                **evidence_context,
            }

        return {
            "error": False,
            "code": None,
            **decision,
            **metrics_context,
            **economics_context,
            **evidence_context,
        }

    def query_all(self):
        decisions = []
        seen_skus = set()

        for product in self.product_service.load_products() or []:
            normalized = self._normalize_product(product)
            if normalized is None:
                continue

            sku = normalized.get("offer_id") or normalized.get("sku")
            if sku is None:
                continue

            sku = str(sku).strip()
            if not sku or sku in seen_skus:
                continue

            seen_skus.add(sku)
            decision = self._cached_decision(sku)
            if decision is None:
                decision = self._with_task_draft_lifecycle(
                    self._with_action_proposal(
                        self._with_decision_history(
                            self._query_product(sku, normalized)
                        )
                    )
                )
                self._store_decision(sku, decision)
            decisions.append(deepcopy(decision))

        decisions.sort(key=self._portfolio_sort_key)

        return {
            "error": False,
            "code": None,
            "total": len(decisions),
            "counts": self._decision_counts(decisions),
            "proposal_counts": self._proposal_counts(decisions),
            "actionable_proposals_count": sum(
                1
                for decision in decisions
                if (decision.get("action_proposal") or {}).get(
                    "action_required"
                )
            ),
            "decisions": decisions,
        }

    def _portfolio_sort_key(self, decision):
        priority = str(decision.get("priority") or "NONE").upper()
        days_of_stock = decision.get("days_of_stock")
        try:
            stock_key = float(days_of_stock)
        except (TypeError, ValueError):
            stock_key = float("inf")
        return (
            self.PRIORITY_ORDER.get(priority, 5),
            stock_key,
            str(decision.get("sku") or ""),
        )

    def _decision_counts(self, decisions):
        counts = {}
        for decision in decisions:
            decision_type = str(
                decision.get("decision_type")
                or self.CODE_INSUFFICIENT_DATA
            )
            counts[decision_type] = counts.get(decision_type, 0) + 1
        return counts

    def _proposal_counts(self, decisions):
        counts = {}
        for decision in decisions:
            proposal_type = (decision.get("action_proposal") or {}).get(
                "proposal_type"
            )
            if proposal_type is None:
                continue
            counts[proposal_type] = counts.get(proposal_type, 0) + 1
        return counts

    def _cached_decision(self, sku):
        entry = self._decision_cache.get(str(sku))
        if entry is None:
            return None
        if self.clock() >= entry["expires_at"]:
            self._decision_cache.pop(str(sku), None)
            return None
        return deepcopy(entry["decision"])

    def _store_decision(self, sku, decision):
        if not self._is_cacheable_decision(decision):
            return
        self._decision_cache[str(sku)] = {
            "expires_at": self.clock() + self.cache_ttl_seconds,
            "decision": deepcopy(decision),
        }

    def _is_cacheable_decision(self, decision):
        return (
            isinstance(decision, dict)
            and not decision.get("error")
            and decision.get("decision_type")
            != self.CODE_INSUFFICIENT_DATA
        )

    def _with_decision_history(self, decision):
        result = deepcopy(decision)
        if (
            self.decision_history_service is None
            or result.get("error")
            or result.get("decision_type")
            == self.CODE_INSUFFICIENT_DATA
        ):
            return result
        try:
            context = self.decision_history_service.record(result)
        except (OSError, ValueError, TypeError):
            context = {
                "decision_history_available": False,
                "decision_changed": False,
            }
        result.update(context or {})
        return result

    def _with_action_proposal(self, decision):
        result = deepcopy(decision)
        if self.action_proposal_service is None:
            return result
        result["action_proposal"] = (
            self.action_proposal_service.propose(result)
        )
        return result

    def _with_task_draft_lifecycle(self, decision):
        result = deepcopy(decision)
        service = self.action_task_draft_service
        if service is None or result.get("error"):
            return result
        proposal = result.get("action_proposal") or {}
        current_proposal_type = (
            proposal.get("proposal_type")
            if proposal.get("action_required")
            else None
        )
        try:
            lifecycle = service.reconcile(
                sku=result.get("sku"),
                current_proposal_type=current_proposal_type,
                current_decision_recorded_at=(
                    result.get("decision_recorded_at")
                ),
            )
        except (OSError, ValueError, TypeError):
            lifecycle = None
        if lifecycle:
            result["task_draft_lifecycle"] = lifecycle
        return result

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

        normalized = {
            "product_id": result.get("product_id", product_id),
            "sku": result.get("sku", sku),
            "net_profit_per_unit": profit,
            "margin_percent": margin,
            "economics_basis": basis,
            "returns_reserve_per_unit": reserve,
            "returns_coverage_percent": coverage,
            "missing_data": missing_data
        }

        source_recorded_at = result.get(
            "unit_economics_source_recorded_at"
        )
        if source_recorded_at is not None:
            normalized["unit_economics_source_recorded_at"] = (
                source_recorded_at
            )

        observed_at = result.get("unit_economics_observed_at")
        if observed_at is None:
            observed_at = result.get("as_of")
        if observed_at is not None:
            normalized["unit_economics_observed_at"] = observed_at

        return normalized

    def _metrics_context(self, prepared):
        metrics = dict(prepared or {})
        return {
            "sales_velocity": metrics.get("sales_velocity"),
            "sales_trend": metrics.get("sales_trend"),
            "current_stock": metrics.get("current_stock"),
            "days_of_stock": metrics.get("days_of_stock"),
            "stock_priority": metrics.get("stock_priority"),
            "decision_profit_per_unit": metrics.get(
                "profit_per_unit"
            ),
            "decision_margin_percent": metrics.get(
                "margin_percent"
            ),
        }

    def _evidence_context(self, prepared):
        metrics = dict(prepared or {})
        return {
            field: metrics.get(field)
            for field in self.EVIDENCE_FIELDS
            if metrics.get(field) is not None
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
