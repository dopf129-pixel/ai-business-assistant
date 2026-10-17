from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from threading import Event, RLock
from time import monotonic
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_context import get_current_tenant_user_id


class _OperationAborted(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class UnitPriceScenarioSource:
    """Build bounded read-only source snapshots for the price calculator."""

    # Keep source normalization aligned with UnitPriceScenarioService's money
    # input contract so unsupported source values are reported as unknown.
    MAX_SCENARIO_MONEY_DIGITS = 15
    MAX_SCENARIO_MONEY_ADJUSTED_EXPONENT = 12
    MIN_SCENARIO_MONEY_ADJUSTED_EXPONENT = -12
    TIME_BUDGET_SECONDS = 60
    HTTP_ATTEMPT_BUDGET = 64
    DISCOUNT_POINTS_DAYS = 28
    CACHE_TTL_SECONDS = 600
    MAX_CACHE_ENTRIES = 128

    def __init__(
        self,
        product_service,
        current_economics_source,
        finance_service,
        cost_service,
        tax_configuration_service,
        clock=None,
        cache_clock=None,
        cache_ttl_seconds=CACHE_TTL_SECONDS,
        max_cache_entries=MAX_CACHE_ENTRIES,
    ):
        self.product_service = product_service
        self.current_economics_source = current_economics_source
        self.finance_service = finance_service
        self.cost_service = cost_service
        self.tax_configuration_service = tax_configuration_service
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.cache_clock = cache_clock or monotonic
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.max_cache_entries = max(1, int(max_cache_entries))
        self._cache = {}
        self._cache_order = []
        self._inflight = {}
        self._lock = RLock()

    def load_snapshot(
        self,
        sku,
        user_id,
        force_refresh=False,
        operation_trace=None,
    ):
        target_sku = str(sku or "").strip()
        target_user = str(user_id or "").strip()
        if not target_sku or not target_user:
            return self._error("UNIT_PRICE_SCENARIO_IDENTITY_REQUIRED")
        if operation_trace is not None and not isinstance(
            operation_trace, PeriodProfitOperationTrace
        ):
            return self._error("UNIT_PRICE_SCENARIO_OPERATION_CONTEXT_INVALID")
        operation_error = self._operation_error(operation_trace)
        if operation_error is not None:
            return self._error(operation_error)

        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        scoped_user, store_id = split_store_tenant_scope(tenant_scope)
        if not tenant_scope or scoped_user != target_user:
            return self._error("UNIT_PRICE_SCENARIO_TENANT_MISMATCH")
        key = (tenant_scope, target_user, target_sku)
        waited_for_refresh = False

        while True:
            operation_error = self._operation_error(operation_trace)
            if operation_error is not None:
                return self._error(operation_error)
            with self._lock:
                cached = self._cache.get(key)
                age = (
                    self.cache_clock() - cached["stored_at"]
                    if cached is not None
                    else None
                )
                if (
                    cached is not None
                    and age < self.cache_ttl_seconds
                    and (not force_refresh or waited_for_refresh)
                ):
                    self._touch(key)
                    result = deepcopy(cached["result"])
                    result["cache"] = {
                        "status": "hit",
                        "age_seconds": round(max(0.0, age), 2),
                        "ttl_seconds": self.cache_ttl_seconds,
                    }
                    return result
                pending = self._inflight.get(key)
                if pending is None:
                    pending = Event()
                    self._inflight[key] = pending
                    leader = True
                else:
                    leader = False

            if leader:
                break
            wait_timeout = self.TIME_BUDGET_SECONDS + 1
            if operation_trace is not None:
                wait_timeout = min(
                    float(wait_timeout),
                    operation_trace.remaining_seconds(),
                )
            if wait_timeout <= 0:
                return self._error("OZON_OPERATION_TIME_BUDGET_EXHAUSTED")
            if not pending.wait(timeout=wait_timeout):
                operation_error = self._operation_error(operation_trace)
                if operation_error is not None:
                    return self._error(operation_error)
                return self._error("UNIT_PRICE_SCENARIO_REFRESH_IN_PROGRESS")
            waited_for_refresh = True

        try:
            result = self._load_snapshot(
                target_sku,
                target_user,
                store_id,
                tenant_scope,
                parent_trace=operation_trace,
            )
            operation_error = self._operation_error(operation_trace)
            if operation_error is not None:
                return self._error(operation_error)
            if result.get("error") is not True:
                with self._lock:
                    self._cache[key] = {
                        "stored_at": self.cache_clock(),
                        "result": deepcopy(result),
                    }
                    self._touch(key)
                    self._evict()
            result = deepcopy(result)
            result["cache"] = {
                "status": "miss",
                "age_seconds": 0,
                "ttl_seconds": self.cache_ttl_seconds,
            }
            return result
        finally:
            with self._lock:
                event = self._inflight.pop(key, None)
                if event is not None:
                    event.set()

    def _load_snapshot(
        self,
        sku,
        user_id,
        store_id,
        tenant_scope,
        parent_trace=None,
    ):
        trace = PeriodProfitOperationTrace(
            operation="unit_price_scenario_source",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            parent=parent_trace,
        )
        trace_token = activate_period_profit_trace(trace)
        try:
            self._ensure_operation_active(trace)
            try:
                products = self.product_service.load_products()
            except Exception:
                return self._error("UNIT_PRICE_SCENARIO_CATALOG_UNAVAILABLE")
            matches = [
                item for item in (products or [])
                if self._product_sku(item) == sku
            ]
            if len(matches) != 1:
                return self._error(
                    "UNIT_PRICE_SCENARIO_SKU_AMBIGUOUS"
                    if matches
                    else "UNIT_PRICE_SCENARIO_SKU_NOT_FOUND"
                )
            product = self._normalize_product(matches[0])
            if not product or not product.get("product_id") or not product.get("offer_id"):
                return self._error("UNIT_PRICE_SCENARIO_PRODUCT_IDENTITY_INCOMPLETE")

            self._ensure_operation_active(trace)
            current_facts = self._load_current_facts(product)
            self._ensure_operation_active(trace)
            cost, cost_updated_at = self._load_cost(product)
            self._ensure_operation_active(trace)
            policy = self._load_tax_policy()
            self._ensure_operation_active(trace)
            start_date, end_date = self._discount_points_period()
            points = self._load_discount_points(
                sku,
                start_date,
                end_date,
                operation_trace=trace,
            )
            self._ensure_operation_active(trace)

            suggested = {
                "price": current_facts.get("seller_price"),
                "cost": cost,
                "commission_rate": current_facts.get("commission_rate"),
                "logistics_per_unit": None,
                "last_mile_per_unit": None,
                "acquiring_per_unit": None,
                "advertising_rate": None,
                "discount_points_rate": points.get("rate"),
                "tax_mode": policy.get("mode"),
                "tax_rate": policy.get("tax_rate"),
                "minimum_tax_rate": policy.get("minimum_tax_rate"),
            }
            provenance = {
                "price": "ozon_current_seller_price" if suggested["price"] is not None else "unknown",
                "cost": "confirmed_store_cost" if cost is not None else "unknown",
                "commission_rate": "ozon_current_fbo_rate" if suggested["commission_rate"] is not None else "unknown",
                "logistics_per_unit": "manual_required",
                "last_mile_per_unit": "manual_required",
                "acquiring_per_unit": "manual_required",
                "advertising_rate": "manual_required",
                "discount_points_rate": points.get("provenance", "unknown"),
                "tax_mode": "active_store_tax_policy" if policy.get("mode") else "unknown",
                "tax_rate": "active_store_tax_policy" if policy.get("mode") else "unknown",
                "minimum_tax_rate": "active_store_tax_policy" if policy.get("mode") else "unknown",
            }
            missing = [key for key, value in suggested.items() if value is None]
            as_of = self._now().isoformat()
            return {
                "error": False,
                "status": "UNIT_PRICE_SCENARIO_SNAPSHOT_READY",
                "snapshot_id": uuid4().hex[:16],
                "identity": {
                    "user_id": user_id,
                    "store_id": store_id,
                    "tenant_scope": tenant_scope,
                    "product_id": str(product["product_id"]),
                    "offer_id": str(product["offer_id"]),
                    "sku": str(product["sku"]),
                },
                "product": {
                    "name": str(
                        product.get("name") or product.get("title") or product["offer_id"]
                    )[:160],
                    "scheme": "FBO",
                },
                "suggested_inputs": suggested,
                "input_provenance": provenance,
                "source_periods": {
                    "discount_points": {
                        "from": start_date,
                        "to": end_date,
                        "calendar_days": self.DISCOUNT_POINTS_DAYS,
                    },
                    "cost_as_of": cost_updated_at,
                    "seller_price_as_of": as_of,
                    "commission_rate_as_of": as_of,
                    "tax_policy_as_of": as_of,
                },
                "source_completeness": {
                    "catalog_identity": {"complete": True},
                    "seller_price": {"complete": suggested["price"] is not None},
                    "commission_rate": {"complete": suggested["commission_rate"] is not None},
                    "cost": {"complete": cost is not None},
                    "tax_policy": {"complete": policy.get("mode") is not None},
                    "discount_points": points["completeness"],
                    "fixed_fees": {"complete": False, "reason": "MANUAL_PER_UNIT_INPUT_REQUIRED"},
                    "advertising": {"complete": False, "reason": "MANUAL_RATE_INPUT_REQUIRED"},
                },
                "source_diagnostics": {
                    "discount_points_sales_observations": points.get("sales_observations", 0),
                    "discount_points_rate": points.get("rate"),
                    "http_attempts_reserved": trace.ozon_requests_reserved,
                    "http_attempt_limit": self.HTTP_ATTEMPT_BUDGET,
                    "time_budget_seconds": self.TIME_BUDGET_SECONDS,
                },
                "missing_inputs": missing,
                "read_only": True,
                "executed": False,
            }
        except _OperationAborted as exc:
            return self._error(exc.code)
        except Exception:
            return self._error("UNIT_PRICE_SCENARIO_SOURCE_UNAVAILABLE")
        finally:
            reset_period_profit_trace(trace_token)

    def _load_current_facts(self, product):
        try:
            result = self.current_economics_source.get(
                sku=str(product["offer_id"]),
                product_id=product["product_id"],
                finance_sku=product["sku"],
                accrual_dates=[],
            )
        except Exception:
            return {}
        if not isinstance(result, dict) or result.get("error") is True:
            return {}
        return {
            "seller_price": self._nonnegative_number(result.get("seller_price"), positive=True),
            "commission_rate": self._rate(result.get("commission_rate")),
        }

    def _load_cost(self, product):
        try:
            row = self.cost_service.get_cost(product["product_id"])
        except Exception:
            return None, None
        if isinstance(row, dict):
            product_id = row.get("product_id")
            amount = row.get("cost_price")
            currency = row.get("currency") or "RUB"
            updated_at = row.get("updated_at")
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            product_id, _, _, amount, currency = row[:5]
            updated_at = row[5] if len(row) > 5 else None
        else:
            return None, None
        if str(product_id) != str(product["product_id"]) or str(currency).upper() != "RUB":
            return None, None
        value = self._nonnegative_number(amount)
        if value is None:
            return None, None
        return value, str(updated_at) if updated_at is not None else None

    def _load_tax_policy(self):
        try:
            result = self.tax_configuration_service.get_policy()
        except Exception:
            return {}
        if (
            not isinstance(result, dict)
            or result.get("error") is True
            or result.get("configured") is not True
            or not isinstance(result.get("policy"), dict)
        ):
            return {}
        policy = result["policy"]
        mode = str(policy.get("mode") or "").upper()
        if mode not in ("NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"):
            return {}
        return {
            "mode": mode,
            "tax_rate": self._rate(policy.get("tax_rate")),
            "minimum_tax_rate": self._rate(policy.get("minimum_tax_rate")),
        }

    def _load_discount_points(
        self,
        sku,
        start_date,
        end_date,
        operation_trace=None,
    ):
        prepare = getattr(self.finance_service, "prepare_read_session", None)
        begin = getattr(self.finance_service, "begin_read_session", None)
        if callable(prepare) and callable(begin):
            try:
                prepare(start_date, end_date)
                begin()
            except Exception:
                return self._points_unavailable("FINANCE_READ_SESSION_INCOMPLETE")

        target_day = datetime.fromisoformat(start_date).date()
        end_day = datetime.fromisoformat(end_date).date()
        records_by_identity = {}
        days_complete = 0
        while target_day <= end_day:
            self._ensure_operation_active(operation_trace)
            day = target_day.isoformat()
            try:
                evidence = self.finance_service.get_daily_discount_points_evidence(day, sku)
            except Exception:
                evidence = None
            if (
                not isinstance(evidence, dict)
                or evidence.get("error") is True
                or evidence.get("complete") is not True
                or not isinstance(evidence.get("records"), list)
            ):
                return self._points_unavailable(
                    "FINANCE_DISCOUNT_POINTS_PERIOD_INCOMPLETE",
                    days_complete=days_complete,
                )
            days_complete += 1
            for record in evidence["records"]:
                if not isinstance(record, dict) or str(record.get("sku") or "") != str(sku):
                    return self._points_unavailable(
                        "FINANCE_DISCOUNT_POINTS_IDENTITY_UNRESOLVED",
                        days_complete=days_complete,
                    )
                posting = str(record.get("posting_number") or "").strip()
                sale = self._decimal(record.get("sale_amount"))
                bonus = self._decimal(record.get("discount_points"))
                if not posting or sale is None or bonus is None or sale <= 0 or bonus < 0 or bonus > sale:
                    return self._points_unavailable(
                        "FINANCE_DISCOUNT_POINTS_RECORD_INVALID",
                        days_complete=days_complete,
                    )
                key = (posting, str(sku))
                pair = (sale, bonus)
                previous = records_by_identity.get(key)
                if previous is not None and previous != pair:
                    return self._points_unavailable(
                        "FINANCE_DISCOUNT_POINTS_DUPLICATE_CONFLICT",
                        days_complete=days_complete,
                    )
                records_by_identity[key] = pair
            target_day += timedelta(days=1)

        total_sales = sum((sale for sale, _ in records_by_identity.values()), Decimal("0"))
        total_points = sum((bonus for _, bonus in records_by_identity.values()), Decimal("0"))
        if days_complete != self.DISCOUNT_POINTS_DAYS or total_sales <= 0 or total_points > total_sales:
            return self._points_unavailable(
                "FINANCE_DISCOUNT_POINTS_NO_VALID_SALES",
                days_complete=days_complete,
                sales_observations=len(records_by_identity),
            )
        rate = (total_points * Decimal("100") / total_sales).normalize()
        return {
            "rate": format(rate, "f"),
            "provenance": "weighted_exact_sku_finance_average_28_completed_days",
            "sales_observations": len(records_by_identity),
            "completeness": {
                "complete": True,
                "days_loaded": days_complete,
                "calendar_days": self.DISCOUNT_POINTS_DAYS,
                "positive_sale_observations": len(records_by_identity),
                "deduplicated_by": "posting_number+finance_sku",
            },
        }

    def _discount_points_period(self):
        now = self._now()
        end = now.date() - timedelta(days=1)
        start = end - timedelta(days=self.DISCOUNT_POINTS_DAYS - 1)
        return start.isoformat(), end.isoformat()

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime):
            raise ValueError("clock must return datetime")
        if value.tzinfo is None:
            value = value.astimezone()
        return value.astimezone()

    def _normalize_product(self, item):
        if isinstance(item, dict):
            return dict(item)
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            return {"product_id": item[0], "offer_id": item[1], "sku": item[2]}
        return None

    def _product_sku(self, item):
        product = self._normalize_product(item)
        return str(product.get("sku") or "").strip() if product else ""

    def _nonnegative_number(self, value, positive=False):
        number = self._decimal(value)
        if number is None or number < 0 or (positive and number == 0):
            return None
        if not number.is_zero() and (
            len(number.as_tuple().digits) > self.MAX_SCENARIO_MONEY_DIGITS
            or number.adjusted() > self.MAX_SCENARIO_MONEY_ADJUSTED_EXPONENT
            or number.adjusted() < self.MIN_SCENARIO_MONEY_ADJUSTED_EXPONENT
        ):
            return None
        return float(number)

    def _rate(self, value):
        number = self._decimal(value)
        if number is None or number < 0 or number > 100:
            return None
        return float(number)

    def _decimal(self, value):
        if isinstance(value, bool) or value in (None, ""):
            return None
        try:
            number = Decimal(str(value).strip().replace(" ", "").replace("\u00a0", ""))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number.is_finite() else None

    def _points_unavailable(self, reason, days_complete=0, sales_observations=0):
        return {
            "rate": None,
            "provenance": "unknown",
            "sales_observations": sales_observations,
            "completeness": {
                "complete": False,
                "days_loaded": days_complete,
                "calendar_days": self.DISCOUNT_POINTS_DAYS,
                "reason": reason,
            },
        }

    def _touch(self, key):
        try:
            self._cache_order.remove(key)
        except ValueError:
            pass
        self._cache_order.append(key)

    def _evict(self):
        while len(self._cache_order) > self.max_cache_entries:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)

    def _error(self, code):
        return {
            "error": True,
            "code": code,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _operation_error(trace):
        if trace is None:
            return None
        if trace.is_cancelled():
            return "OZON_OPERATION_CANCELLED"
        if trace.remaining_seconds() <= 0:
            return "OZON_OPERATION_TIME_BUDGET_EXHAUSTED"
        return None

    @classmethod
    def _ensure_operation_active(cls, trace):
        error = cls._operation_error(trace)
        if error is not None:
            raise _OperationAborted(error)
