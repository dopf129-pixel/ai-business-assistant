from copy import deepcopy
from math import isfinite
from time import monotonic


class ProductBusinessDecisionQueryService:

    CODE_SKU_REQUIRED = "SKU_REQUIRED"
    CODE_SKU_NOT_FOUND = "SKU_NOT_FOUND"
    CODE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    CODE_ACTION_PROPOSAL_RESULT_INVALID = (
        "PRODUCT_DECISION_ACTION_PROPOSAL_RESULT_INVALID"
    )
    CODE_DECISION_RESULT_INVALID = "PRODUCT_DECISION_RESULT_INVALID"
    CODE_UNIT_ECONOMICS_RESULT_INVALID = (
        "PRODUCT_DECISION_UNIT_ECONOMICS_RESULT_INVALID"
    )
    CODE_OPERATIONAL_METRICS_RESULT_INVALID = (
        "PRODUCT_DECISION_OPERATIONAL_METRICS_RESULT_INVALID"
    )
    CODE_TASK_DRAFT_LIFECYCLE_RESULT_INVALID = (
        "PRODUCT_DECISION_TASK_DRAFT_LIFECYCLE_RESULT_INVALID"
    )

    DECISION_PRIORITY = {
        "REPLENISH_HIGH_PRIORITY": "CRITICAL",
        "REPLENISH_NORMAL": "HIGH",
        "WATCH_LOW_MARGIN": "NORMAL",
        "INVESTIGATE_LOW_PROFIT": "HIGH",
        "HOLD_STOCK": "LOW",
        "INSUFFICIENT_DATA": "NONE",
    }
    DECISION_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
    DECISION_REASONS = {
        "DAYS_OF_STOCK_CRITICAL",
        "DAYS_OF_STOCK_LOW",
        "HIGH_SALES_VELOCITY",
        "SALES_DECLINING",
        "POSITIVE_UNIT_PROFIT",
        "LOW_UNIT_PROFIT",
        "NEGATIVE_UNIT_PROFIT",
        "LOW_MARGIN",
        "ECONOMICS_INCOMPLETE",
        "IDENTITY_MISMATCH",
    }
    DECISION_RESULT_FIELDS = {
        "product_id",
        "sku",
        "decision_type",
        "priority",
        "reasons",
        "confidence",
        "missing_data",
    }

    DECISION_ACTION_PROPOSAL = {
        "REPLENISH_HIGH_PRIORITY": ("REVIEW_REPLENISHMENT", True),
        "REPLENISH_NORMAL": ("REVIEW_REPLENISHMENT", True),
        "INVESTIGATE_LOW_PROFIT": ("REVIEW_UNIT_ECONOMICS", True),
        "WATCH_LOW_MARGIN": ("REVIEW_MARGIN", True),
        "HOLD_STOCK": ("MONITOR_ONLY", False),
    }

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

    HISTORY_CONTEXT_FIELDS = {
        "decision_history_available",
        "decision_changed",
        "previous_decision_type",
        "previous_priority",
        "decision_recorded_at",
        "decision_history_count",
        "previous_feedback",
        "decision_outcome",
    }
    HISTORY_FEEDBACK_VALUES = {
        None,
        "USEFUL",
        "NOT_RELEVANT",
    }
    HISTORY_OUTCOME_VALUES = {
        None,
        "PRIORITY_DECREASED",
        "PRIORITY_INCREASED",
        "DECISION_CHANGED",
    }
    TASK_DRAFT_LIFECYCLE_FIELDS = {
        "error",
        "stale_count",
        "stale_drafts",
        "executed",
        "execution_allowed",
    }
    TASK_DRAFT_PROPOSAL_TYPES = {
        "REVIEW_REPLENISHMENT",
        "REVIEW_UNIT_ECONOMICS",
        "REVIEW_MARGIN",
    }
    ECONOMICS_NUMERIC_FIELDS = {
        "net_profit_per_unit",
        "margin_percent",
        "risk_adjusted_profit_per_unit",
        "risk_adjusted_margin_percent",
        "returns_cost_per_delivered_unit",
        "estimated_returns_cost_per_unit",
        "estimated_profit_per_unit",
        "estimated_margin_percent",
        "returns_estimate_coverage_percent",
    }
    SALES_TRENDS = {"GROWING", "DECLINING", "STABLE"}
    STOCK_PRIORITIES = {
        "CRITICAL",
        "HIGH",
        "MEDIUM",
        "LOW",
        "NO_SALES",
    }

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

        sales_metrics, sales_invalid = (
            self._query_operational_metrics_source(
                self.sales_metrics_source,
                sku,
                source_name="sales",
            )
        )
        if sales_invalid:
            return self._operational_metrics_result_failure(
                product_id=product_id,
                sku=sku,
                source_name="sales",
            )

        stock_metrics, stock_invalid = (
            self._query_operational_metrics_source(
                self.stock_metrics_source,
                sku,
                source_name="stock",
            )
        )
        if stock_invalid:
            return self._operational_metrics_result_failure(
                product_id=product_id,
                sku=sku,
                source_name="stock",
            )
        try:
            economics_result = self.unit_economics_query_service.query(sku)
        except (OSError, TypeError, ValueError, KeyError, AttributeError):
            return self._unit_economics_result_failure(
                product_id=product_id,
                sku=sku,
            )

        if not self._valid_unit_economics_result(economics_result):
            return self._unit_economics_result_failure(
                product_id=product_id,
                sku=sku,
            )

        economics_metrics = (
            None
            if economics_result["error"] is True
            else self._normalize_economics(
                economics_result,
                product_id=product_id,
                sku=sku,
            )
        )

        prepared = self.decision_input_provider.build(
            sales_metrics=sales_metrics,
            stock_metrics=stock_metrics,
            unit_economics=economics_metrics
        )

        try:
            decision = self.decision_service.decide(deepcopy(prepared))
        except (OSError, TypeError, ValueError, KeyError, AttributeError):
            return self._decision_result_failure(
                product_id=product_id,
                sku=sku,
            )

        if not self._valid_decision_result(
            decision,
            product_id=product_id,
            sku=sku,
        ):
            return self._decision_result_failure(
                product_id=product_id,
                sku=sku,
            )

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

    def _valid_decision_result(self, decision, product_id, sku):
        if not isinstance(decision, dict):
            return False

        if set(decision) != self.DECISION_RESULT_FIELDS:
            return False

        if decision.get("product_id") != product_id:
            return False

        if decision.get("sku") != sku:
            return False

        decision_type = decision.get("decision_type")
        priority = decision.get("priority")
        confidence = decision.get("confidence")
        reasons = decision.get("reasons")
        missing_data = decision.get("missing_data")

        if (
            decision_type not in self.DECISION_PRIORITY
            or priority != self.DECISION_PRIORITY[decision_type]
            or confidence not in self.DECISION_CONFIDENCE
        ):
            return False

        if not isinstance(reasons, list) or not reasons:
            return False
        if any(
            not isinstance(reason, str)
            or not reason.strip()
            or reason not in self.DECISION_REASONS
            for reason in reasons
        ):
            return False
        if len(set(reasons)) != len(reasons):
            return False

        if not isinstance(missing_data, list):
            return False
        if any(
            not isinstance(field, str) or not field.strip()
            for field in missing_data
        ):
            return False
        if len(set(missing_data)) != len(missing_data):
            return False

        if decision_type == self.CODE_INSUFFICIENT_DATA:
            return confidence == "LOW" and bool(missing_data)

        if confidence == "LOW":
            return False

        return True

    def _decision_result_failure(self, product_id, sku):
        return {
            "error": True,
            "code": self.CODE_DECISION_RESULT_INVALID,
            "product_id": product_id,
            "sku": sku,
            "decision_type": self.CODE_INSUFFICIENT_DATA,
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["decision"],
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

            if (
                not isinstance(decision, dict)
                or decision.get("error") is True
            ):
                return {
                    "error": True,
                    "code": (
                        decision.get("code")
                        if isinstance(decision, dict)
                        else self.CODE_ACTION_PROPOSAL_RESULT_INVALID
                    ),
                }

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
            and decision.get("decision_history_error") is not True
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
            context = self.decision_history_service.record(
                deepcopy(result)
            )
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return self._history_context_unavailable(
                result,
                "DECISION_HISTORY_RECORD_FAILED",
            )

        if not self._valid_decision_history_context(context):
            return self._history_context_unavailable(
                result,
                "INVALID_DECISION_HISTORY_CONTEXT",
            )

        for field in self.HISTORY_CONTEXT_FIELDS:
            if field in context:
                result[field] = deepcopy(context[field])

        result["decision_history_error"] = False
        result["decision_history_code"] = None
        return result

    def _valid_decision_history_context(self, context):
        if not isinstance(context, dict):
            return False

        if set(context) - self.HISTORY_CONTEXT_FIELDS:
            return False

        available = context.get("decision_history_available")
        changed = context.get("decision_changed")

        if type(available) is not bool or type(changed) is not bool:
            return False

        if available is False and changed is True:
            return False

        for field in (
            "previous_decision_type",
            "previous_priority",
            "decision_recorded_at",
        ):
            if field not in context or context[field] is None:
                continue
            if (
                not isinstance(context[field], str)
                or not context[field].strip()
            ):
                return False

        if (
            "decision_history_count" in context
            and (
                type(context["decision_history_count"]) is not int
                or context["decision_history_count"] < 0
                or (
                    available is True
                    and context["decision_history_count"] < 1
                )
            )
        ):
            return False

        if (
            context.get("previous_feedback")
            not in self.HISTORY_FEEDBACK_VALUES
        ):
            return False

        if (
            context.get("decision_outcome")
            not in self.HISTORY_OUTCOME_VALUES
        ):
            return False

        if (
            changed is True
            and (
                not isinstance(
                    context.get("previous_decision_type"),
                    str,
                )
                or not context["previous_decision_type"].strip()
            )
        ):
            return False

        return True

    def _history_context_unavailable(self, decision, code):
        result = deepcopy(decision)
        result.update({
            "decision_history_available": False,
            "decision_changed": False,
            "previous_decision_type": None,
            "previous_priority": None,
            "decision_recorded_at": None,
            "decision_history_count": None,
            "previous_feedback": None,
            "decision_outcome": None,
            "decision_history_error": True,
            "decision_history_code": code,
        })
        return result

    def _with_action_proposal(self, decision):
        result = deepcopy(decision)
        if self.action_proposal_service is None or result.get("error"):
            return result

        try:
            proposal = self.action_proposal_service.propose(
                deepcopy(result)
            )
        except (OSError, TypeError, ValueError, KeyError, AttributeError):
            return self._action_proposal_failure(result)

        if not self._valid_action_proposal(proposal, result):
            return self._action_proposal_failure(result)

        result["action_proposal"] = deepcopy(proposal)
        return result

    def _valid_action_proposal(self, proposal, decision):
        if not isinstance(proposal, dict):
            return False

        if (
            type(proposal.get("available")) is not bool
            or type(proposal.get("action_required")) is not bool
            or type(proposal.get("requires_confirmation")) is not bool
            or proposal.get("execution_allowed") is not False
            or proposal.get("automation_status") != "PROHIBITED"
        ):
            return False

        sku = proposal.get("sku")
        priority = proposal.get("priority")
        decision_type = proposal.get("decision_type")
        reasons = proposal.get("reasons")

        if (
            not isinstance(sku, str)
            or not sku.strip()
            or sku != decision.get("sku")
            or priority != decision.get("priority")
            or decision_type != decision.get("decision_type")
            or not isinstance(reasons, list)
            or reasons != decision.get("reasons")
            or any(
                not isinstance(reason, str) or not reason.strip()
                for reason in reasons
            )
        ):
            return False

        expected = self.DECISION_ACTION_PROPOSAL.get(
            decision_type
        )

        if expected is None:
            return (
                proposal.get("available") is False
                and proposal.get("proposal_type") is None
                and proposal.get("action_required") is False
                and proposal.get("requires_confirmation") is False
            )

        expected_type, expected_action_required = expected
        return (
            proposal.get("available") is True
            and proposal.get("proposal_type") == expected_type
            and proposal.get("action_required")
            is expected_action_required
            and proposal.get("requires_confirmation")
            is expected_action_required
        )

    def _action_proposal_failure(self, decision):
        result = deepcopy(decision)
        result["error"] = True
        result["code"] = self.CODE_ACTION_PROPOSAL_RESULT_INVALID
        result["action_proposal"] = None
        return result

    def _with_task_draft_lifecycle(self, decision):
        result = deepcopy(decision)
        service = self.action_task_draft_service
        if (
            service is None
            or result.get("error")
            or result.get("decision_history_error") is True
        ):
            return result

        proposal = result.get("action_proposal") or {}
        current_proposal_type = (
            proposal.get("proposal_type")
            if proposal.get("action_required") is True
            else None
        )
        current_decision_recorded_at = result.get(
            "decision_recorded_at"
        )

        try:
            lifecycle = service.reconcile(
                sku=result.get("sku"),
                current_proposal_type=current_proposal_type,
                current_decision_recorded_at=(
                    current_decision_recorded_at
                ),
            )
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return self._task_draft_lifecycle_failure(result)

        if not self._valid_task_draft_lifecycle(
            lifecycle,
            result,
            current_proposal_type,
            current_decision_recorded_at,
        ):
            return self._task_draft_lifecycle_failure(result)

        result["task_draft_lifecycle"] = deepcopy(lifecycle)
        return result

    def _valid_task_draft_lifecycle(
        self,
        lifecycle,
        decision,
        current_proposal_type,
        current_decision_recorded_at,
    ):
        if not isinstance(lifecycle, dict):
            return False

        if set(lifecycle) != self.TASK_DRAFT_LIFECYCLE_FIELDS:
            return False

        if (
            lifecycle.get("error") is not False
            or lifecycle.get("executed") is not False
            or lifecycle.get("execution_allowed") is not False
        ):
            return False

        stale_count = lifecycle.get("stale_count")
        stale_drafts = lifecycle.get("stale_drafts")
        if (
            type(stale_count) is not int
            or stale_count < 0
            or not isinstance(stale_drafts, list)
            or len(stale_drafts) != stale_count
        ):
            return False

        decision_sku = decision.get("sku")
        current_recorded_at = (
            current_decision_recorded_at
            if isinstance(current_decision_recorded_at, str)
            else ""
        )

        for draft in stale_drafts:
            if not isinstance(draft, dict):
                return False

            draft_sku = draft.get("sku")
            proposal_type = draft.get("proposal_type")
            recorded_at = draft.get("decision_recorded_at")
            if (
                draft_sku != decision_sku
                or proposal_type not in self.TASK_DRAFT_PROPOSAL_TYPES
                or not isinstance(recorded_at, str)
                or not recorded_at.strip()
                or draft.get("status") != "STALE"
                or draft.get("executed") is not False
                or draft.get("execution_allowed") is not False
            ):
                return False

            if (
                proposal_type == current_proposal_type
                and recorded_at == current_recorded_at
            ):
                return False

        return True

    def _task_draft_lifecycle_failure(self, decision):
        result = deepcopy(decision)
        result["error"] = True
        result["code"] = self.CODE_TASK_DRAFT_LIFECYCLE_RESULT_INVALID
        result["task_draft_lifecycle"] = None
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

    def _query_operational_metrics_source(
        self,
        source,
        sku,
        source_name,
    ):
        if source is None:
            return None, False

        try:
            if callable(source):
                result = source(sku)
            else:
                query = getattr(source, "query", None)
                if query is None:
                    return None, False
                result = query(sku)
        except (OSError, TypeError, ValueError, KeyError, AttributeError):
            return None, True

        if result is None:
            return None, False

        if not isinstance(result, dict):
            return None, True

        if "error" in result:
            if type(result.get("error")) is not bool:
                return None, True
            if result["error"] is True:
                return None, False

        if not self._valid_operational_metrics_result(
            result,
            source_name,
        ):
            return None, True

        return dict(result), False

    def _valid_operational_metrics_result(
        self,
        result,
        source_name,
    ):
        missing_data = result.get("missing_data")
        if missing_data is not None and (
            not isinstance(missing_data, list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in missing_data
            )
            or len(missing_data) != len(set(missing_data))
        ):
            return False

        if source_name == "sales":
            velocity = result.get("sales_velocity")
            if (
                velocity is not None
                and not self._valid_non_negative_metric(velocity)
            ):
                return False

            trend = result.get("sales_trend")
            if (
                trend is not None
                and (
                    not isinstance(trend, str)
                    or trend not in self.SALES_TRENDS
                )
            ):
                return False

            for field in (
                "sales_source_recorded_at",
                "sales_observed_at",
            ):
                if not self._valid_optional_evidence_string(
                    result.get(field)
                ):
                    return False
            return True

        if source_name == "stock":
            current_stock = result.get("current_stock")
            days_of_stock = result.get("days_of_stock")
            priority = result.get("priority")
            if (
                current_stock is not None
                and not self._valid_non_negative_metric(current_stock)
            ):
                return False
            if (
                days_of_stock is not None
                and not self._valid_non_negative_metric(days_of_stock)
            ):
                return False
            if (
                priority is not None
                and (
                    not isinstance(priority, str)
                    or priority not in self.STOCK_PRIORITIES
                )
            ):
                return False
            if (
                priority == "NO_SALES"
                and days_of_stock is not None
            ):
                return False
            if (
                priority in {
                    "CRITICAL",
                    "HIGH",
                    "MEDIUM",
                    "LOW",
                }
                and days_of_stock is None
            ):
                return False
            if days_of_stock is not None and priority is None:
                return False

            for field in (
                "stock_source_recorded_at",
                "stock_observed_at",
            ):
                if not self._valid_optional_evidence_string(
                    result.get(field)
                ):
                    return False
            return True

        return False

    @staticmethod
    def _valid_non_negative_metric(value):
        return (
            type(value) in (int, float)
            and isfinite(float(value))
            and float(value) >= 0
        )

    @staticmethod
    def _valid_optional_evidence_string(value):
        return (
            value is None
            or (
                isinstance(value, str)
                and bool(value.strip())
            )
        )

    def _operational_metrics_result_failure(
        self,
        product_id,
        sku,
        source_name,
    ):
        return {
            "error": True,
            "code": self.CODE_OPERATIONAL_METRICS_RESULT_INVALID,
            "product_id": product_id,
            "sku": sku,
            "decision_type": self.CODE_INSUFFICIENT_DATA,
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": [source_name + "_metrics"],
        }

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

    def _valid_unit_economics_result(self, result):
        if not isinstance(result, dict):
            return False

        if type(result.get("error")) is not bool:
            return False

        if result["error"] is True:
            return True

        if type(result.get("available")) is not bool:
            return False

        missing_fields = result.get("missing_fields")
        if (
            not isinstance(missing_fields, list)
            or any(
                not isinstance(field, str) or not field.strip()
                for field in missing_fields
            )
            or len(missing_fields) != len(set(missing_fields))
        ):
            return False

        for field in self.ECONOMICS_NUMERIC_FIELDS:
            value = result.get(field)
            if value is None:
                continue
            if (
                type(value) not in (int, float)
                or not isfinite(float(value))
            ):
                return False

        for field in (
            "returns_finance_complete",
            "returns_estimate_available",
        ):
            if field in result and type(result.get(field)) is not bool:
                return False

        impact = result.get("returns_finance_impact")
        if (
            impact is not None
            and (
                not isinstance(impact, dict)
                or type(impact.get("error")) is not bool
            )
        ):
            return False

        if result["available"] is False:
            if any(
                result.get(field) is not None
                for field in (
                    "net_profit_per_unit",
                    "margin_percent",
                    "risk_adjusted_profit_per_unit",
                    "risk_adjusted_margin_percent",
                    "estimated_profit_per_unit",
                    "estimated_margin_percent",
                )
            ):
                return False
            if result.get("returns_estimate_available") is True:
                return False

        if result.get("risk_adjusted_profit_per_unit") is not None:
            if (
                result.get("returns_finance_complete") is not True
                or result.get("returns_cost_per_delivered_unit") is None
            ):
                return False

        if result.get("returns_estimate_available") is True:
            if any(
                result.get(field) is None
                for field in (
                    "estimated_returns_cost_per_unit",
                    "estimated_profit_per_unit",
                    "returns_estimate_coverage_percent",
                )
            ):
                return False

        return True

    def _unit_economics_result_failure(self, product_id, sku):
        return {
            "error": True,
            "code": self.CODE_UNIT_ECONOMICS_RESULT_INVALID,
            "product_id": product_id,
            "sku": sku,
            "decision_type": self.CODE_INSUFFICIENT_DATA,
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["unit_economics"],
        }

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
