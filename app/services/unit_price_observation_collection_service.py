"""Bounded read-only collection for one saved unit-price observation."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.returns_buyout_analytics_service import ReturnsBuyoutAnalyticsService


class UnitPriceObservationCollectionService:
    """Collect selected-window finance and optional CPC evidence via adapters.

    This layer deliberately returns an evidence package instead of calculating
    an observed profit. Q18 owns normalization and comparability decisions.
    """

    MIN_WINDOW_DAYS = 3
    MAX_WINDOW_DAYS = 56
    TIME_BUDGET_SECONDS = 60
    HTTP_ATTEMPT_BUDGET = 64
    MAX_UNKNOWN_FIELDS = 50
    MAX_UNSUPPORTED_TYPES = 50
    FINANCE_FIELDS = (
        "gross_sales", "discount_points", "net_accrual", "commission",
        "logistics", "acquiring", "other_fees",
    )
    FINANCE_SCHEMA_FIELDS = frozenset({
        "error", "date", "sku", "operations", "sales_count",
        "gross_sales", "discount_points", "net_accrual", "commission",
        "logistics", "acquiring", "other_fees", "fee_breakdown",
        "accrual_type_breakdown", "fee_components_included",
        "ancillary_incomplete_count",
    })
    RAW_FINANCE_FIELDS = frozenset({
        "accruals", "last_id", "pages_loaded", "_period_profit_finance_completeness",
        "_period_profit_revenue_diagnostics", "accrual_id", "accrued_category",
        "total_amount", "item_fees", "posting", "non_item_fee", "container_fees",
        "unit_number", "type_id", "accrued", "amount", "currency", "currency_code",
        "fees", "sku", "products", "commission", "sale_amount", "sale_commission",
        "bonus", "delivery", "services", "name", "description", "seller_price",
        "sale_price", "coinvestment", "accrual_type", "operation_id", "operation_type",
        "operation_type_name", "operation_date", "accrual_date", "date", "quantity",
        "posting_number", "order_date", "posting_date", "status", "price",
        "offer_id", "product_id", "marketplace_service_item_fulfillment",
        "marketplace_service_item_pickup", "marketplace_service_item_dropoff",
    })
    SUPPORTED_FEE_TYPE_IDS = frozenset({"1", "29", "32", "69", "98"})
    MAX_RAW_SCHEMA_NODES_PER_DAY = 10_000

    def __init__(
        self, repository, finance_service, advertising_service=None, clock=None,
        returns_buyout_source=None, returns_buyout_analytics_service=None,
    ):
        self.repository = repository
        self.finance_service = finance_service
        self.advertising_service = advertising_service
        self.returns_buyout_source = returns_buyout_source
        self.returns_buyout_analytics_service = (
            returns_buyout_analytics_service or ReturnsBuyoutAnalyticsService()
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect_window(self, observation_id, *, date_from, date_to):
        """Collect one completed local-calendar window for a saved observation.

        The result contains aggregate evidence and schema diagnostics only. It
        never includes API credentials, posting identifiers, raw rows, or item
        names. No observation/result record is modified by this read operation.
        """
        loaded = self.repository.get_unit_price_observation(observation_id)
        if not isinstance(loaded, dict) or loaded.get("error") is not False:
            return self._error("PLANNING_OBSERVATION_NOT_FOUND")
        observation = loaded.get("observation")
        if not isinstance(observation, dict):
            return self._error("PLANNING_OBSERVATION_CORRUPT")
        if observation.get("status") == "ARCHIVED":
            return self._error("PLANNING_OBSERVATION_ARCHIVED")
        identity = self._identity(observation)
        if identity is None:
            return self._error("PLANNING_OBSERVATION_IDENTITY_INVALID")
        if identity["sale_schema"] != "FBO":
            return {
                "error": False,
                "status": "UNSUPPORTED_SCHEME",
                "code": "UNIT_PRICE_OBSERVATION_SCHEME_UNSUPPORTED",
                "read_only": True,
                "executed": False,
            }
        try:
            start = date.fromisoformat(str(date_from))
            end = date.fromisoformat(str(date_to))
            zone = ZoneInfo(observation["window_timezone"])
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None:
                raise ValueError("clock must return a timezone-aware datetime")
            local_today = now.astimezone(zone).date()
            effective = self._aware_datetime(observation.get("effective_from"))
        except (TypeError, ValueError, ZoneInfoNotFoundError, KeyError):
            return self._error("UNIT_PRICE_OBSERVATION_WINDOW_INVALID")
        days = (end - start).days + 1
        if (
            start > end
            or days < self.MIN_WINDOW_DAYS
            or days > self.MAX_WINDOW_DAYS
            or end >= local_today
            or start < effective.astimezone(zone).date()
        ):
            return self._error("UNIT_PRICE_OBSERVATION_WINDOW_NOT_COMPLETED")

        parent = current_period_profit_trace()
        trace = PeriodProfitOperationTrace(
            operation="unit_price_observation_collection",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            parent=parent,
        )
        token = activate_period_profit_trace(trace)
        try:
            return self._collect(
                identity=identity,
                observation=observation,
                start=start,
                end=end,
                timezone_name=observation["window_timezone"],
                trace=trace,
            )
        finally:
            reset_period_profit_trace(token)

    def _collect(self, *, identity, observation, start, end, timezone_name, trace):
        finance_totals = {field: Decimal("0") for field in self.FINANCE_FIELDS}
        successful_days = 0
        finance_rows = 0
        finance_complete = True
        finance_reason = None
        unknown_fields = set()
        unsupported_types = set()

        prepare = getattr(self.finance_service, "prepare_read_session", None)
        begin = getattr(self.finance_service, "begin_read_session", None)
        if callable(prepare) and callable(begin):
            try:
                prepare(start.isoformat(), end.isoformat())
            except Exception:
                finance_complete = False
                finance_reason = "FINANCE_READ_SESSION_UNAVAILABLE"
        if callable(begin):
            if finance_complete:
                try:
                    begin()
                except Exception:
                    finance_complete = False
                    finance_reason = "FINANCE_READ_SESSION_UNAVAILABLE"

        current = start
        while finance_complete and current <= end:
            budget_error = self._budget_error(trace)
            if budget_error:
                finance_complete = False
                finance_reason = budget_error
                break
            try:
                daily = self.finance_service.get_daily_finance(
                    current.isoformat(), sku=identity["sku"],
                )
            except Exception:
                daily = None
            if not isinstance(daily, dict) or daily.get("error") is not False:
                finance_complete = False
                finance_reason = self._safe_reason(
                    daily.get("code") if isinstance(daily, dict) else None,
                    default="FINANCE_SOURCE_UNAVAILABLE",
                )
                break

            normalized = self._daily_finance(daily)
            if normalized is None:
                finance_complete = False
                finance_reason = "FINANCE_RESPONSE_INVALID"
                break
            for field, amount in normalized["amounts"].items():
                finance_totals[field] += amount
            finance_rows += normalized["row_count"]
            successful_days += 1
            if daily.get("fee_components_included") is False:
                finance_complete = False
                finance_reason = "FINANCE_COMPONENTS_INCOMPLETE"
            unknown_fields.update(normalized["unknown_fields"])
            unknown_fields.update(
                self._cached_raw_unknown_fields(current.isoformat())
            )
            unsupported_types.update(normalized["unsupported_types"])
            current += timedelta(days=1)

        finance_status = (
            "COMPLETE" if finance_complete and successful_days == (end - start).days + 1
            else "SOURCE_UNAVAILABLE" if successful_days == 0
            else "PARTIAL"
        )
        sources = [{
            "name": "FINANCE",
            "status": finance_status,
            "complete": finance_status == "COMPLETE",
            "row_count": finance_rows,
            "requested_at": trace.started_at_utc,
            "received_at": self._timestamp(self.clock()),
            "source_date_basis": "OZON_ACCRUAL_DATE",
            "source_window_start": start.isoformat(),
            "source_window_end": end.isoformat(),
            "timezone": timezone_name,
            "unknown_field_count": len({name for name, _ in unknown_fields}),
            "unknown_fields": [
                {"name": name, "type": kind}
                for name, kind in sorted(unknown_fields)[:self.MAX_UNKNOWN_FIELDS]
            ],
            "unsupported_types": sorted(unsupported_types)[:self.MAX_UNSUPPORTED_TYPES],
            **({"reason": finance_reason} if finance_reason else {}),
        }]

        performance = self._load_advertising(
            identity["sku"], start, end, timezone_name, trace,
        )
        performance["source"]["requested_at"] = trace.started_at_utc
        performance["source"]["received_at"] = self._timestamp(self.clock())
        sources.append(performance["source"])
        returns = self._load_returns_buyout(
            identity=identity, start=start, end=end,
            timezone_name=timezone_name, trace=trace,
        )
        observed_at = self._timestamp(self.clock())
        price_effective_local_date = self._aware_datetime(
            observation["effective_from"]
        ).astimezone(ZoneInfo(timezone_name)).date()
        warnings = [
            "PRICE_HISTORY_UNCONFIRMED: manual confirmation does not prove per-sale price history.",
            "Finance amounts use accrual-date basis; CPC is a separate Performance source and is not deducted here.",
        ]
        if start == price_effective_local_date:
            warnings.append(
                "WINDOW_INCLUDES_EFFECTIVE_DATE: a price change during this local day may create mixed-price evidence."
            )
        if not finance_complete:
            warnings.append("FINANCE_WINDOW_PARTIAL: missing days are not filled with zero.")
        if performance["source"]["status"] != "COMPLETE":
            warnings.append("PERFORMANCE_CPC_SCOPE_ONLY: missing CPC does not mean zero advertising spend.")
        if returns["successful_sale_units"] is not None:
            warnings.extend([
                "FBO_DELIVERED_UNITS_ARE_A_POINT_IN_TIME_POSTING_STATUS_SNAPSHOT.",
                "BUYOUT_RATE_USES_DELIVERED_AND_CONFIRMED_NON_BUYOUT_UNITS; IT_IS_NOT_PREMIUM_ANALYTICS.",
                "PERFORMANCE_REPORT_DATE_AND_FBO_POSTING_COHORT_ARE_NOT_IDENTICAL.",
            ])

        metrics = {
            "gross_seller_revenue": self._money(finance_totals["gross_sales"]),
            "discount_points": self._money(finance_totals["discount_points"]),
            "finance_net": self._money(finance_totals["net_accrual"]),
            "acquiring": self._money(finance_totals["acquiring"]),
            "commission": self._money(finance_totals["commission"]),
            "logistics": self._money(finance_totals["logistics"]),
            "other_fees": self._money(finance_totals["other_fees"]),
            "source_row_count": finance_rows,
            "sample_days": successful_days,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "date_basis": "OZON_ACCRUAL_DATE",
            "price_evidence_status": "PRICE_HISTORY_UNCONFIRMED",
            "advertising_status": performance["source"]["status"],
            "successful_sale_units": returns["successful_sale_units"],
            "successful_unit_denominator": returns["successful_sale_units"],
            "ordered_units": returns["ordered_units"],
            "delivered_units": returns["delivered_units"],
            "cancelled_units": returns["cancelled_units"],
            "returned_units": returns["returned_units"],
            "buyout_rate_percent": returns["buyout_rate_percent"],
            "buyout_sample_size": returns["buyout_sample_size"],
            "cpc_spend": performance["expense"],
        }
        status = (
            "SOURCE_UNAVAILABLE" if finance_status == "SOURCE_UNAVAILABLE"
            else "INSUFFICIENT_DATA"
        )
        reasons = [finance_reason] if finance_reason else []
        diagnostics = trace.public_summary()
        diagnostics.update({
            "collection_http_attempts": trace.ozon_requests_reserved,
            "collection_http_attempt_limit": self.HTTP_ATTEMPT_BUDGET,
            "collection_time_budget_seconds": self.TIME_BUDGET_SECONDS,
        })
        return {
            "error": False,
            "status": status,
            "identity": identity,
            "seller_price_cents": observation["seller_price_cents"],
            "window": {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "timezone": timezone_name,
                "date_basis": "SOURCE_CALENDAR_DATE",
            },
            "sources": sources + [{
                "name": "OWNER_DECLARED_PRICE",
                "status": "COMPLETE",
                "complete": True,
                "as_of": observation.get("recorded_at"),
                "source_date_basis": "OWNER_DECLARED_EFFECTIVE_TIME",
                "timezone": timezone_name,
                "reason": "This is the saved owner-confirmed price assumption, not historical API evidence.",
            }, {
                "name": "SELLER_PRICE",
                "status": "SOURCE_UNAVAILABLE",
                "complete": False,
                "reason": "No per-sale seller-price history is exposed by the reused finance adapter.",
            }, {
                "name": "ANALYTICS",
                "status": "NOT_REQUESTED",
                "complete": False,
                "reason": "This collection does not require a Premium Analytics subscription; unit counts are not inferred.",
            }, {
                **returns["source"],
            }, {
                "name": "TARIFF",
                "status": "NOT_REQUESTED",
                "complete": False,
                "reason": "The collector does not resolve commission for observed historical sale prices.",
            }, {
                "name": "COST",
                "status": "NOT_REQUESTED",
                "complete": False,
                "reason": "The collector records financial evidence only; saved-plan cost remains a separate assumption.",
            }, {
                "name": "TAX",
                "status": "NOT_REQUESTED",
                "complete": False,
                "reason": "Tax is not recomputed from the collected accrual aggregates.",
            }],
            "metrics": metrics,
            "completeness": {
                "price_history": "PRICE_HISTORY_UNCONFIRMED",
                "successful_units": "CONFIRMED" if returns["successful_sale_units"] is not None else "UNKNOWN",
                "finance": "CONFIRMED" if finance_status == "COMPLETE" else "PARTIAL",
                "advertising": "CONFIRMED" if performance["source"]["complete"] else "UNKNOWN",
                "tariff": "UNKNOWN",
                "tax": "UNKNOWN",
                "unit_cost": "UNKNOWN",
                "returns": "CONFIRMED" if returns["source"]["complete"] else (
                    "SOURCE_UNAVAILABLE" if returns["source"]["status"] == "SOURCE_UNAVAILABLE"
                    else "UNKNOWN" if returns["source"]["status"] == "NOT_REQUESTED"
                    else "PARTIAL"
                ),
                "analytics": "UNKNOWN",
                "window": "CONFIRMED",
                "deduplication": "UNKNOWN",
            },
            "reasons": reasons,
            "warnings": warnings,
            "collected_at": observed_at,
            "diagnostics": diagnostics,
            "read_only": True,
            "executed": False,
        }

    def _load_returns_buyout(self, *, identity, start, end, timezone_name, trace):
        source = {
            "name": "RETURNS",
            "status": "NOT_REQUESTED",
            "complete": False,
            "source_date_basis": "FBO_POSTING_AND_RETURN_CHANGE_WINDOW",
            "source_window_start": start.isoformat(),
            "source_window_end": end.isoformat(),
            "timezone": timezone_name,
        }
        empty = {
            "source": source,
            "successful_sale_units": None,
            "ordered_units": None,
            "delivered_units": None,
            "cancelled_units": None,
            "returned_units": None,
            "buyout_rate_percent": None,
            "buyout_sample_size": None,
        }
        if self.returns_buyout_source is None:
            source["reason"] = "RETURNS_BUYOUT_SOURCE_NOT_CONFIGURED"
            return empty

        budget_error = self._budget_error(trace)
        if budget_error:
            source.update({
                "status": "RATE_LIMITED" if "BUDGET" in budget_error else "SOURCE_UNAVAILABLE",
                "reason": self._safe_reason(budget_error, default="RETURNS_BUYOUT_SOURCE_UNAVAILABLE"),
            })
            return empty
        try:
            facts = self.returns_buyout_source.get(
                identity["offer_id"], start.isoformat(), end.isoformat(),
            )
        except Exception:
            facts = None
        received_at = self._timestamp(self.clock())
        if not isinstance(facts, dict) or facts.get("error") is True:
            code = self._safe_reason(
                facts.get("code") if isinstance(facts, dict) else None,
                default="RETURNS_BUYOUT_SOURCE_UNAVAILABLE",
            )
            source.update({
                "status": "RATE_LIMITED" if "RATE_LIMIT" in code or "BUDGET" in code else "SOURCE_UNAVAILABLE",
                "reason": code,
                "requested_at": trace.started_at_utc,
                "received_at": received_at,
            })
            return empty

        analysis = self.returns_buyout_analytics_service.analyze(facts)
        if not isinstance(analysis, dict) or analysis.get("error") is True:
            source.update({
                "status": "PARTIAL",
                "reason": "RETURNS_BUYOUT_ANALYSIS_INVALID",
                "requested_at": trace.started_at_utc,
                "received_at": received_at,
            })
            return empty

        def count(name):
            value = facts.get(name)
            return value if type(value) is int and 0 <= value <= 1_000_000_000 else None

        total_units = count("total_units")
        delivered_units = count("delivered_units")
        cancelled_units = count("cancelled_units")
        returned_units = count("customer_return_units")
        buyout_rate = analysis.get("observed_buyout_rate")
        sample_size = analysis.get("buyout_sample_size")
        postings = facts.get("postings")
        terminal_statuses = {"delivered", "cancelled"}
        terminal_postings = (
            isinstance(postings, list)
            and all(
                isinstance(item, dict)
                and str(item.get("status") or "").lower() in terminal_statuses
                for item in postings
            )
        )
        no_ambiguous_cancellations = count("ambiguous_cancelled_units") == 0
        units_reconcile = (
            total_units is not None
            and delivered_units is not None
            and cancelled_units is not None
            and delivered_units + cancelled_units == total_units
        )
        complete = bool(
            analysis.get("complete") is True
            and facts.get("postings_complete") is True
            and facts.get("returns_complete") is True
            and no_ambiguous_cancellations
            and terminal_postings
            and units_reconcile
        )
        if complete:
            source.update({
                "status": "COMPLETE",
                "complete": True,
                "row_count": count("posting_count") or 0,
                "requested_at": trace.started_at_utc,
                "received_at": received_at,
            })
        else:
            source.update({
                "status": "PARTIAL",
                "reason": "FBO_BUYOUT_SAMPLE_NOT_FINAL_OR_CLASSIFIED",
                "requested_at": trace.started_at_utc,
                "received_at": received_at,
                "row_count": count("posting_count") or 0,
            })

        usable = complete and delivered_units is not None and delivered_units > 0
        return {
            "source": source,
            "successful_sale_units": delivered_units if usable else None,
            "ordered_units": total_units,
            "delivered_units": delivered_units,
            "cancelled_units": cancelled_units,
            "returned_units": returned_units,
            "buyout_rate_percent": buyout_rate if complete else None,
            "buyout_sample_size": sample_size if complete else None,
        }

    def _load_advertising(self, sku, start, end, timezone_name, trace):
        if self.advertising_service is None:
            return self._performance_unavailable(
                "PERFORMANCE_ADAPTER_NOT_CONFIGURED", start=start, end=end,
                timezone_name=timezone_name,
            )
        budget_error = self._budget_error(trace)
        if budget_error:
            status = "RATE_LIMITED" if "RATE_LIMIT" in budget_error else "SOURCE_UNAVAILABLE"
            return self._performance_unavailable(
                budget_error, status=status, start=start, end=end,
                timezone_name=timezone_name,
            )
        try:
            result = self.advertising_service.load(
                start.isoformat(), end.isoformat(), {sku},
            )
        except Exception:
            result = None
        if not isinstance(result, dict) or result.get("error") is True:
            code = self._safe_reason(
                result.get("code") if isinstance(result, dict) else None,
                default="PERFORMANCE_SOURCE_UNAVAILABLE",
            )
            status = "RATE_LIMITED" if "RATE_LIMIT" in code or "BUDGET" in code else "SOURCE_UNAVAILABLE"
            return self._performance_unavailable(
                code, status=status, start=start, end=end,
                timezone_name=timezone_name,
            )
        if result.get("configured") is False:
            return {
                "expense": None,
                "source": {
                    "name": "PERFORMANCE", "status": "NOT_REQUESTED",
                    "complete": False, "reason": "PERFORMANCE_CREDENTIALS_NOT_CONFIGURED",
                    "source_date_basis": "PERFORMANCE_REPORT_DATE",
                    "source_window_start": start.isoformat(),
                    "source_window_end": end.isoformat(),
                    "timezone": timezone_name,
                },
            }
        if result.get("complete") is not True:
            return self._performance_unavailable(
                "PERFORMANCE_EVIDENCE_INCOMPLETE", start=start, end=end,
                timezone_name=timezone_name,
            )
        amount = self._decimal(result.get("expense"))
        if amount is None or amount < 0:
            return self._performance_unavailable(
                "PERFORMANCE_RESPONSE_INVALID", start=start, end=end,
                timezone_name=timezone_name,
            )
        return {
            "expense": self._money(amount),
            "source": {
                "name": "PERFORMANCE", "status": "COMPLETE", "complete": True,
                "row_count": self._nonnegative_int(result.get("matched_row_count"), default=0),
                "source_date_basis": "PERFORMANCE_REPORT_DATE",
                "source_window_start": start.isoformat(),
                "source_window_end": end.isoformat(),
                "timezone": timezone_name,
                "unsupported_types": [],
            },
        }

    @staticmethod
    def _performance_unavailable(
        reason, status="SOURCE_UNAVAILABLE", *, start=None, end=None,
        timezone_name=None,
    ):
        source = {
            "name": "PERFORMANCE", "status": status,
            "complete": False, "reason": reason,
            "source_date_basis": "PERFORMANCE_REPORT_DATE",
        }
        if start is not None and end is not None:
            source.update({
                "source_window_start": start.isoformat(),
                "source_window_end": end.isoformat(),
            })
        if isinstance(timezone_name, str) and timezone_name:
            source["timezone"] = timezone_name
        return {
            "expense": None,
            "source": source,
        }

    @classmethod
    def _daily_finance(cls, daily):
        amounts = {}
        for field in cls.FINANCE_FIELDS:
            amount = cls._decimal(daily.get(field))
            if amount is None:
                return None
            amounts[field] = amount
        row_count = cls._nonnegative_int(daily.get("operations"), default=0)
        unknown = set()
        for key, value in daily.items():
            if key not in cls.FINANCE_SCHEMA_FIELDS:
                normalized_key = cls._safe_field_name(key)
                if normalized_key:
                    unknown.add((normalized_key, cls._value_type(value)))
        type_breakdown = daily.get("accrual_type_breakdown") or {}
        if not isinstance(type_breakdown, dict):
            return None
        unsupported = set()
        for type_id, item in type_breakdown.items():
            normalized_id = str(type_id).strip()
            if normalized_id in cls.SUPPORTED_FEE_TYPE_IDS:
                continue
            if isinstance(item, dict):
                label = item.get("name") or item.get("description")
            else:
                label = None
            normalized_label = cls._safe_type_label(label)
            unsupported.add(normalized_label or "type_id:" + cls._safe_type_id(normalized_id))
        return {
            "amounts": amounts,
            "row_count": row_count,
            "unknown_fields": unknown,
            "unsupported_types": unsupported,
        }

    def _cached_raw_unknown_fields(self, accrual_date):
        """Inspect cached raw response shape without retaining any values."""
        getter = getattr(self.finance_service, "get_cached_daily_accruals", None)
        if not callable(getter):
            return set()
        try:
            cached = getter(accrual_date, accrual_date)
        except Exception:
            return set()
        response = cached.get(accrual_date) if isinstance(cached, dict) else None
        if not isinstance(response, dict):
            return set()

        found = set()
        nodes = [0]

        def visit(value, path="", depth=0):
            if depth > 8 or nodes[0] >= self.MAX_RAW_SCHEMA_NODES_PER_DAY:
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    nodes[0] += 1
                    if nodes[0] > self.MAX_RAW_SCHEMA_NODES_PER_DAY:
                        return
                    if not isinstance(key, str):
                        continue
                    raw_name = key.strip()
                    normalized_name = self._safe_field_name(raw_name)
                    if not normalized_name or raw_name.lower() in {
                        "token", "apikey", "api_key", "client_secret",
                        "authorization", "password", "secret",
                    }:
                        continue
                    child_path = (
                        path + "." + normalized_name if path else normalized_name
                    )
                    if raw_name not in self.RAW_FINANCE_FIELDS:
                        found.add((child_path[:80], self._value_type(item)))
                    visit(item, child_path, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    nodes[0] += 1
                    if nodes[0] > self.MAX_RAW_SCHEMA_NODES_PER_DAY:
                        return
                    visit(item, path + "[]", depth + 1)

        visit(response)
        return found

    @staticmethod
    def _identity(observation):
        nested = observation.get("identity")
        nested = nested if isinstance(nested, dict) else {}
        fields = {}
        for key in ("store_id", "product_id", "offer_id", "sku", "sale_schema"):
            outer_value = observation.get(key)
            nested_value = nested.get(key)
            if (outer_value is not None and nested_value is not None
                    and str(outer_value).strip() != str(nested_value).strip()):
                return None
            fields[key] = outer_value if outer_value is not None else nested_value
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            return None
        return {key: value.strip() for key, value in fields.items()}

    @staticmethod
    def _aware_datetime(value):
        if not isinstance(value, str):
            raise ValueError("timestamp required")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (
            not amount.is_finite()
            or len(amount.as_tuple().digits) > 15
            or amount.adjusted() > 12
            or amount.adjusted() < -12
        ):
            return None
        return amount

    @staticmethod
    def _money(value):
        return format(value.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _nonnegative_int(value, default=None):
        if type(value) is int and value >= 0:
            return value
        if default is not None:
            return default
        return None

    @staticmethod
    def _safe_field_name(value):
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text[:80] if text and text.isascii() and re.fullmatch(r"[A-Za-z0-9_.\[\]-]+", text) else None

    @staticmethod
    def _value_type(value):
        if value is None:
            return "null"
        if type(value) is bool:
            return "bool"
        if type(value) is int:
            return "int"
        if isinstance(value, Decimal):
            return "decimal"
        if type(value) is float:
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        return "unknown"

    @staticmethod
    def _safe_type_id(value):
        return value[:20] if value.isascii() and value.isdecimal() else "unknown"

    @staticmethod
    def _safe_type_label(value):
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        return normalized[:80] or None

    @staticmethod
    def _safe_reason(value, default):
        text = str(value or "").strip().upper()
        return text[:120] if text and re.fullmatch(r"[A-Z0-9_]+", text) else default

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, datetime) or value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _budget_error(trace):
        if trace.is_cancelled():
            return "OZON_OPERATION_CANCELLED"
        if trace.remaining_seconds() <= 0:
            return "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
        if trace.is_budget_exhausted():
            return "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED"
        return None

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "read_only": True,
            "executed": False,
        }
