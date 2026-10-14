import re
from collections import OrderedDict
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from threading import RLock
from time import monotonic
from uuid import uuid4

from period_profit_request import build_period_profit_request
from services.period_profit_cost_exclusion_context import (
    activate_cost_exclusion,
    reset_cost_exclusion,
)
from services.tenant_context import get_current_tenant_user_id


class ExperimentalStoreEconomicsRuntimeService:
    """Read-only experimental store economics based on existing Ozon services."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}
    ANALYTICS_METRICS = ("ordered_units", "cancellations", "returns")
    ANALYTICS_DIMENSIONS = ("day",)
    ANALYTICS_PAGE_SIZE = 1000
    ANALYTICS_MAX_PAGES = 20
    ACCRUAL_POSTING_BATCH_SIZE = 100
    ACCRUAL_POSTING_WORKERS = 4
    OPERATIONAL_POSTING_MAX_PAGES = 20
    OPERATIONAL_RETURN_MAX_PAGES = 20
    RETURNS_DIAGNOSTIC_MAX_PAGES_PER_SCHEMA = 2
    RETURNS_DIAGNOSTIC_MAX_HTTP_ATTEMPTS = 10
    RETURNS_DIAGNOSTIC_TIME_BUDGET_SECONDS = 120
    ANALYTICS_DIAGNOSTIC_MAX_HTTP_ATTEMPTS = 2
    ANALYTICS_DIAGNOSTIC_TIME_BUDGET_SECONDS = 30
    REPORT_CACHE_MAX_SCOPES = 64
    FEE_LABEL_MATCHERS = {
        "last_mile": (
            "последняя миля",
            "последней мили",
            "доставка до места выдачи",
            "доставка к месту выдачи",
            "выдача товара",
            "last mile",
            "last-mile",
            "lastmile",
        ),
        "cross_docking": (
            "кросс-док",
            "кросс док",
            "cross-dock",
            "cross dock",
            "crossdock",
        ),
        "paid_storage": (
            "платное хран",
            "плата за хранение",
            "платное размещение",
            "плата за размещение",
            "стоимость размещения",
            "размещение на складе",
            "вынужденное размещение",
            "paid storage",
            "paidstorage",
            "storage fee",
        ),
        "reverse_logistics": (
            "обратная логист",
            "возвратная логист",
            "логистика возврата",
            "return flow logistic",
            "returnflowlogistic",
            "reverse logistics",
        ),
    }
    ADVERTISING_FEE_MATCHERS = (
        "реклам",
        "продвиж",
        "оплата за клик",
        "оплата за заказ",
        "оплата за показ",
        "payperclick",
        "pay per click",
        "advertising",
        "marketplacemarketing",
        "marketing action",
        "promotion",
        "cpc",
        "cpo",
        "cpm",
    )
    COMMISSION_FEE_LABELS = frozenset(
        {
            "вознаграждение за продажу",
            "возврат вознаграждения",
            "sale commission",
            "commission for sale",
            "commission refund",
            "refund of commission",
        }
    )
    ACCRUAL_POSTING_FAILURE_CODES = frozenset(
        {
            "OZON_API_TOTAL_TIMEOUT",
            "OZON_API_TIMEOUT",
            "OZON_CREDENTIALS_UNAVAILABLE",
            "OZON_NETWORK_ERROR",
            "OZON_RATE_LIMITED",
            "OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE",
            "OZON_FINANCE_POSTING_CLIENT_EXCEPTION",
            "OZON_FINANCE_POSTING_DATE_RANGE_INVALID",
            "OZON_FINANCE_POSTING_NUMBERS_UNAVAILABLE",
            "OZON_FINANCE_POSTING_NUMBERS_INVALID",
            "OZON_FINANCE_POSTING_NUMBERS_EMPTY",
            "OZON_FINANCE_ACCRUAL_TYPES_UNAVAILABLE",
            "OZON_FINANCE_ACCRUAL_POSTINGS_RESPONSE_INVALID",
            "OZON_FINANCE_ACCRUAL_POSTINGS_SCOPE_INVALID",
        }
    )
    REALIZATION_FAILURE_CODES = frozenset(
        {
            "OZON_FINANCE_REALIZATION_DATE_RANGE_INVALID",
            "OZON_FINANCE_REALIZATION_PERIOD_NOT_FULL_MONTHS",
            "OZON_FINANCE_REALIZATION_CLIENT_UNAVAILABLE",
            "OZON_FINANCE_REALIZATION_REQUEST_FAILED",
            "OZON_FINANCE_REALIZATION_RESPONSE_UNAVAILABLE",
            "OZON_FINANCE_REALIZATION_ROWS_UNAVAILABLE",
            "OZON_FINANCE_REALIZATION_ROW_INVALID",
            "OZON_FINANCE_REALIZATION_COMMISSION_MISSING",
            "OZON_FINANCE_REALIZATION_COMMISSION_INVALID",
            "OZON_FINANCE_REALIZATION_COMMISSION_ZERO",
        }
    )
    OZON_REQUEST_FAILURE_CODES = frozenset(
        {
            "OZON_API_TOTAL_TIMEOUT",
            "OZON_API_TIMEOUT",
            "OZON_API_REQUEST_FAILED",
            "OZON_CREDENTIALS_UNAVAILABLE",
            "OZON_NETWORK_ERROR",
            "OZON_RATE_LIMITED",
        }
    )

    def __init__(
        self,
        query_service,
        advertising_service=None,
        analytics_client=None,
        finance_transaction_client=None,
    ):
        self.query_service = query_service
        self.advertising_service = advertising_service
        self.analytics_client = analytics_client
        self.finance_transaction_client = finance_transaction_client
        self._pending_custom_period_users = {}
        self._pending_lock = RLock()
        self._calculation_inflight = set()
        self._report_views = OrderedDict()
        self._latest_report_views = {}
        self._report_views_lock = RLock()

    def handle_callback(self, callback_data, user_id=None, today=None):
        parts = str(callback_data or "").strip().split(":")
        if len(parts) != 2 or parts[0] != "experimental_store_economics":
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_CALLBACK_INVALID")

        period = parts[1].strip().upper()
        if period == "CUSTOM":
            return self.begin_custom_period(user_id)
        if period not in self.PERIOD_CODES:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_PERIOD_INVALID")

        request = build_period_profit_request(period_code=period, today=today)
        if request.get("error") is True:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_PERIOD_INVALID")
        return self._calculate_once(
            request["date_from"],
            request["date_to"],
            user_id=user_id,
            mode="preset:" + period,
        )

    def begin_custom_period(self, user_id):
        user_key = self._user_key(user_id)
        if not user_key:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_USER_REQUIRED")
        with self._pending_lock:
            self._pending_custom_period_users[user_key] = self._tenant_scope(user_key)
        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_INPUT_REQUIRED",
            "message": "Введите период в формате 01.01.2026 - 02.02.2026",
            "read_only": True,
            "executed": False,
        }

    def handle_text(self, text, user_id=None, today=None):
        user_key = self._user_key(user_id)
        if not user_key:
            return None
        tenant_scope = self._tenant_scope(user_key)
        with self._pending_lock:
            pending_scope = self._pending_custom_period_users.get(user_key)
            pending = user_key in self._pending_custom_period_users
            if pending and pending_scope != tenant_scope:
                self._pending_custom_period_users.pop(user_key, None)
                return self._custom_period_store_stale()
        if not pending:
            match = re.fullmatch(
                r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*"
                r"(\d{1,2}\.\d{1,2}\.\d{4})",
                " ".join(str(text or "").strip().split()),
            )
            if match:
                parsed = self._parse_custom_period_dates(match.groups())
                if parsed and self._has_calculation_inflight(
                    user_id, "custom", parsed
                ):
                    return self._calculation_in_progress()
            return None

        value = " ".join(str(text or "").strip().split())
        if value.casefold() in {"отмена", "cancel", "/cancel"}:
            self.clear_pending_custom_period_input(user_id)
            return {
                "error": False,
                "status": "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_CANCELLED",
                "message": "Ввод периода отменён.",
                "read_only": True,
                "executed": False,
            }

        match = re.fullmatch(
            r"(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*"
            r"(\d{1,2}\.\d{1,2}\.\d{4})",
            value,
        )
        if not match:
            return self._custom_period_retry()
        parsed = self._parse_custom_period_dates(match.groups())
        if parsed is None:
            return self._custom_period_retry()
        request = build_period_profit_request(
            date_from=parsed[0],
            date_to=parsed[1],
            today=today,
        )
        if request.get("error") is True:
            return self._custom_period_retry()

        return self._calculate_once(
            request["date_from"],
            request["date_to"],
            user_id=user_id,
            mode="custom",
            consume_pending_user_key=user_key,
            expected_pending_tenant_scope=tenant_scope,
        )

    def _calculate_once(
        self,
        date_from,
        date_to,
        user_id=None,
        mode="custom",
        consume_pending_user_key=None,
        expected_pending_tenant_scope=None,
    ):
        user_key = self._user_key(user_id)
        if not user_key:
            return self.calculate(date_from, date_to, user_id=user_id)
        tenant_scope = self._user_key(get_current_tenant_user_id()) or user_key
        period_key = (str(date_from), str(date_to))
        key = (tenant_scope, user_key, str(mode), period_key)
        with self._pending_lock:
            if key in self._calculation_inflight:
                return self._calculation_in_progress()
            if (
                consume_pending_user_key is not None
                and self._pending_custom_period_users.get(
                    consume_pending_user_key
                ) != expected_pending_tenant_scope
            ):
                return self._custom_period_already_used()
            if consume_pending_user_key is not None:
                self._pending_custom_period_users.pop(
                    consume_pending_user_key, None
                )
            self._calculation_inflight.add(key)
        try:
            return self.calculate(date_from, date_to, user_id=user_id)
        finally:
            with self._pending_lock:
                self._calculation_inflight.discard(key)

    def _has_calculation_inflight(self, user_id, mode, period_key):
        user_key = self._user_key(user_id)
        tenant_scope = self._user_key(get_current_tenant_user_id()) or user_key
        key = (tenant_scope, user_key, str(mode), tuple(map(str, period_key)))
        with self._pending_lock:
            return key in self._calculation_inflight

    @staticmethod
    def _parse_custom_period_dates(tokens):
        parsed = []
        for token in tokens:
            try:
                parsed.append(datetime.strptime(token, "%d.%m.%Y").date())
            except (TypeError, ValueError):
                return None
        return parsed

    @staticmethod
    def _calculation_in_progress():
        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_ALREADY_RUNNING",
            "message": "Этот расчёт уже выполняется. Дождитесь ответа на первый запрос.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _custom_period_already_used():
        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_ALREADY_USED",
            "message": "Этот ввод периода уже обработан. Выберите период заново, если нужен повторный расчёт.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _custom_period_store_stale():
        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_STORE_CHANGED",
            "message": "Вы переключили магазин. Старый ввод периода отменён; выберите период заново в текущем магазине.",
            "read_only": True,
            "executed": False,
        }

    def clear_pending_custom_period_input(self, user_id):
        user_key = self._user_key(user_id)
        if user_key:
            with self._pending_lock:
                self._pending_custom_period_users.pop(user_key, None)

    @classmethod
    def _tenant_scope(cls, user_key):
        return cls._user_key(get_current_tenant_user_id()) or user_key

    def calculate(self, date_from, date_to, user_id=None):
        provider, summary_service = self._summary_dependencies()
        if not callable(provider) or summary_service is None:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_DEPENDENCY_UNAVAILABLE")
        try:
            products = provider()
        except Exception:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_PRODUCTS_UNAVAILABLE")
        if not isinstance(products, list):
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_PRODUCTS_UNAVAILABLE")

        token = activate_cost_exclusion()
        try:
            summary = summary_service.calculate(date_from, date_to, products)
        except Exception:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_FINANCE_UNAVAILABLE")
        finally:
            reset_cost_exclusion(token)

        if (
            not isinstance(summary, dict)
            or summary.get("error") is not False
            or summary.get("status") != "PERIOD_PROFIT_SUMMARY_READY"
        ):
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_FINANCE_UNAVAILABLE")

        metrics = self._base_metrics(summary)
        if metrics is None:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_FINANCE_INVALID")
        finance_service = getattr(summary_service, "finance_service", None)
        accrual_posting_categories = self._load_finance_accrual_posting_categories(
            date_from,
            date_to,
            finance_service=finance_service,
        )
        metrics["accrual_posting_category_diagnostics"] = {
            key: accrual_posting_categories[key]
            for key in (
                "available",
                "failure_code",
                "posting_count",
                "operation_count",
                "commission_operation_count",
                "commission_sale_operation_count",
                "commission_sale_amount",
                "commission_refund_operation_count",
                "commission_refund_amount",
                "commission_other_operation_count",
                "commission_other_amount",
                "unmapped_type_count",
                "unmapped_type_amount",
                "storage_service_count",
                "paid_storage",
            )
        }
        metrics["analytics"] = self._load_analytics(date_from, date_to)
        metrics["analytics"] = self._fill_analytics_from_seller_api(
            metrics["analytics"], date_from, date_to
        )
        realization_commission = self._load_finance_realization_commission(
            date_from,
            date_to,
            finance_service=finance_service,
        )
        if (
            realization_commission.get("available") is True
            and metrics["analytics"].get("returns") != 0
            and realization_commission.get("return_fee_row_count", 0) == 0
        ):
            realization_commission = self._failed_realization_commission(
                "OZON_FINANCE_REALIZATION_COMMISSION_MISSING",
                realization_commission,
            )
        metrics["realization_commission_diagnostics"] = realization_commission
        explicit_commission = realization_commission.get("commission")
        commission_source = "FINANCE_REALIZATION_REPORT"
        if explicit_commission is None:
            explicit_commission = accrual_posting_categories.get("commission")
            commission_source = "FINANCE_ACCRUAL_POSTINGS"
        if explicit_commission is None:
            explicit_commission = self._commission_from_explicit_types(summary)
            commission_source = "ACCRUAL_FEE_TYPES"
        if explicit_commission is None:
            commission_source = "POSTING_SALE_COMMISSION"
        elif commission_source != "FINANCE_REALIZATION_REPORT":
            refund_count = accrual_posting_categories.get(
                "commission_refund_operation_count", 0
            )
            fee_breakdown = summary.get("fee_breakdown")
            summary_has_refund = isinstance(fee_breakdown, dict) and any(
                self._commission_label_kind([label]) == "refund"
                for label in fee_breakdown
            )
            summary_has_refund = summary_has_refund or any(
                self._commission_label_kind(entry["labels"]) == "refund"
                for entry in self._accrual_type_entries(summary)
            )
            known_returns = metrics["analytics"].get("returns")
            if not summary_has_refund and not refund_count and known_returns != 0:
                commission_source = "POSTING_SALE_COMMISSION"
        if explicit_commission is not None:
            commission_delta = round(
                explicit_commission - metrics["commission"],
                2,
            )
            metrics["commission"] = explicit_commission
            metrics["other_fees"] = round(
                metrics["other_fees"] - commission_delta,
                2,
            )
        metrics["commission_source"] = commission_source

        accepted_skus = self._catalog_skus(products)
        for row in summary.get("products") or []:
            if isinstance(row, dict):
                sku = self._text(row.get("sku"))
                if sku:
                    accepted_skus.add(sku)
        metrics["advertising"] = self._load_advertising(
            date_from,
            date_to,
            accepted_skus,
        )
        metrics["fee_subcategories"] = self._fee_subcategories(summary)
        posting_storage = accrual_posting_categories.get("paid_storage")
        if posting_storage is not None:
            metrics["fee_subcategories"]["paid_storage"] = posting_storage
        metrics["fee_breakdown"] = self._fee_breakdown(summary)
        metrics["finance_advertising"] = self._finance_advertising(
            metrics["fee_breakdown"]
        )
        metrics["accrual_diagnostics"] = self._accrual_category_diagnostics(
            summary
        )
        metrics["expense_breakdown"] = self._build_expense_breakdown(
            metrics,
            date_from,
            date_to,
        )

        report_text = self._render(date_from, date_to, metrics)
        details_text = self._render_details(date_from, date_to, metrics)
        report_view_id = uuid4().hex[:12]
        if user_id:
            self._save_report_views(
                user_id,
                report_text,
                details_text,
                date_from=date_from,
                date_to=date_to,
                report_view_id=report_view_id,
            )

        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_READY",
            "date_from": date_from,
            "date_to": date_to,
            "report_view_id": report_view_id,
            "metrics": metrics,
            "text": report_text,
            "details_text": details_text,
            "cost_excluded": True,
            "profit_complete": False,
            "read_only": True,
            "executed": False,
        }

    def handle_details(self, user_id=None, report_view_id=None):
        return self._get_cached_report_view(
            user_id, "details", report_view_id=report_view_id
        )

    def handle_summary(self, user_id=None, report_view_id=None):
        return self._get_cached_report_view(
            user_id, "summary", report_view_id=report_view_id
        )

    def handle_returns_api_diagnostic(self, user_id=None, report_view_id=None):
        cached = self._get_report_view(user_id, report_view_id)
        if cached is None:
            return self._returns_diagnostic_error(
                "Сначала откройте отчёт экспериментальной экономики."
            )
        date_from = cached.get("date_from")
        date_to = cached.get("date_to")
        if not date_from or not date_to:
            return self._returns_diagnostic_error(
                "Период прошлого отчёта недоступен. Сформируйте его заново."
            )
        getter = getattr(self.analytics_client, "get_returns", None)
        if not callable(getter):
            return self._returns_diagnostic_error(
                "Клиент Seller API возвратов недоступен."
            )

        deadline = monotonic() + self.RETURNS_DIAGNOSTIC_TIME_BUDGET_SECONDS
        http_attempts = [0]
        schemas = []
        failure_code = None
        sample_shape = None

        def observe_request_attempt(_endpoint=None):
            http_attempts[0] += 1

        for schema in ("FBO", "FBS"):
            state = {
                "schema": schema,
                "page_count": 0,
                "api_row_count": 0,
                "unique_count": 0,
                "complete": False,
                "types": {},
                "statuses": {},
                "change_moments": [],
            }
            seen_records = {}
            last_id = 0
            for _page_number in range(
                self.RETURNS_DIAGNOSTIC_MAX_PAGES_PER_SCHEMA
            ):
                remaining = deadline - monotonic()
                if remaining <= 0 or http_attempts[0] >= (
                    self.RETURNS_DIAGNOSTIC_MAX_HTTP_ATTEMPTS
                ):
                    failure_code = "DIAGNOSTIC_BUDGET_REACHED"
                    break
                try:
                    response = getter(
                        return_schema=schema,
                        since=date_from,
                        to=date_to,
                        limit=500,
                        last_id=last_id,
                        timeout=min(15, remaining),
                        max_attempts=2,
                        total_timeout=min(25, remaining),
                        request_attempt_observer=observe_request_attempt,
                    )
                except Exception:
                    failure_code = "OZON_RETURNS_REQUEST_FAILED"
                    break
                if not isinstance(response, dict) or response.get("error") is True:
                    failure_code = self._safe_returns_diagnostic_error_code(
                        response
                    )
                    break
                rows = response.get("returns")
                has_next = response.get("has_next")
                if not isinstance(rows, list) or type(has_next) is not bool:
                    failure_code = "OZON_RETURNS_RESPONSE_INVALID"
                    break

                state["page_count"] += 1
                state["api_row_count"] += len(rows)
                invalid_record = False
                for row in rows:
                    if not isinstance(row, dict):
                        failure_code = "OZON_RETURNS_RECORD_INVALID"
                        invalid_record = True
                        break
                    raw_id = row.get("id")
                    if raw_id is None:
                        raw_id = row.get("return_id")
                    record_id = self._integer(raw_id)
                    if record_id is None or record_id <= 0:
                        failure_code = "OZON_RETURNS_RECORD_ID_MISSING"
                        invalid_record = True
                        break
                    signature = self._freeze_api_value(row)
                    if record_id in seen_records:
                        if seen_records[record_id] != signature:
                            failure_code = "OZON_RETURNS_DUPLICATE_CONFLICT"
                            invalid_record = True
                            break
                        continue
                    seen_records[record_id] = signature
                    state["unique_count"] += 1
                    if sample_shape is None:
                        sample_shape = self._returns_diagnostic_shape(row)

                    return_type = self._safe_diagnostic_label(
                        row.get("type"), fallback="(тип отсутствует)"
                    )
                    type_group = state["types"].setdefault(
                        return_type,
                        {"rows": 0, "quantity": 0, "quantity_missing": 0},
                    )
                    type_group["rows"] += 1
                    product = row.get("product")
                    quantity = (
                        self._integer(product.get("quantity"))
                        if isinstance(product, dict)
                        else None
                    )
                    if quantity is None:
                        type_group["quantity_missing"] += 1
                    else:
                        type_group["quantity"] += quantity

                    visual = row.get("visual")
                    visual_status = (
                        visual.get("status")
                        if isinstance(visual, dict)
                        else None
                    )
                    change_moment = (
                        visual.get("change_moment")
                        if isinstance(visual, dict)
                        else None
                    )
                    safe_moment = self._safe_diagnostic_timestamp(change_moment)
                    if safe_moment:
                        state["change_moments"].append(safe_moment)
                    status_name = (
                        visual_status.get("sys_name")
                        if isinstance(visual_status, dict)
                        else None
                    )
                    if status_name:
                        status_label = self._safe_diagnostic_label(
                            status_name,
                            fallback="(статус не распознан)",
                        )
                        state["statuses"][status_label] = (
                            state["statuses"].get(status_label, 0) + 1
                        )
                if invalid_record:
                    break

                if has_next is False:
                    state["complete"] = True
                    break
                if not rows:
                    failure_code = "OZON_RETURNS_CURSOR_INVALID"
                    break
                next_id = self._integer(rows[-1].get("id"))
                if next_id is None:
                    next_id = self._integer(rows[-1].get("return_id"))
                if next_id is None or next_id <= last_id:
                    failure_code = "OZON_RETURNS_CURSOR_INVALID"
                    break
                last_id = next_id
            schemas.append(state)
            if failure_code:
                break

        return {
            "error": False,
            "status": "EXPERIMENTAL_RETURNS_API_DIAGNOSTIC_READY",
            "message": self._render_returns_api_diagnostic(
                date_from,
                date_to,
                schemas,
                sample_shape,
                http_attempts[0],
                failure_code,
            ),
            "read_only": True,
            "executed": False,
        }

    def handle_analytics_api_diagnostic(self, user_id=None, report_view_id=None):
        cached = self._get_report_view(user_id, report_view_id)
        if cached is None:
            return self._analytics_diagnostic_error(
                "Сначала откройте отчёт экспериментальной экономики."
            )
        date_from = cached.get("date_from")
        date_to = cached.get("date_to")
        if not date_from or not date_to:
            return self._analytics_diagnostic_error(
                "Период прошлого отчёта недоступен. Сформируйте его заново."
            )
        getter = getattr(self.analytics_client, "get_analytics_data", None)
        if not callable(getter):
            return self._analytics_diagnostic_error(
                "Клиент Ozon Analytics недоступен."
            )

        deadline = monotonic() + self.ANALYTICS_DIAGNOSTIC_TIME_BUDGET_SECONDS
        http_attempts = [0]

        def observe_request_attempt(_endpoint=None):
            http_attempts[0] += 1

        remaining = deadline - monotonic()
        if remaining <= 0:
            return self._render_analytics_api_diagnostic(
                date_from,
                date_to,
                None,
                http_attempts[0],
                "DIAGNOSTIC_BUDGET_REACHED",
            )
        try:
            response = getter(
                date_from,
                date_to,
                metrics=list(self.ANALYTICS_METRICS),
                dimension=list(self.ANALYTICS_DIMENSIONS),
                limit=self.ANALYTICS_PAGE_SIZE,
                offset=0,
                timeout=min(15, remaining),
                max_attempts=self.ANALYTICS_DIAGNOSTIC_MAX_HTTP_ATTEMPTS,
                total_timeout=min(25, remaining),
                request_attempt_observer=observe_request_attempt,
            )
        except Exception:
            response = None
        failure_code = None
        if not isinstance(response, dict) or response.get("error") is True:
            failure_code = (
                self._safe_returns_diagnostic_error_code(response)
                if isinstance(response, dict)
                else "OZON_ANALYTICS_REQUEST_FAILED"
            )
        result = response.get("result") if isinstance(response, dict) else None
        rows = result.get("data") if isinstance(result, dict) else None
        if failure_code is None and (
            not isinstance(rows, list)
            or len(rows) > self.ANALYTICS_PAGE_SIZE
            or any(not isinstance(row, dict) for row in rows)
        ):
            failure_code = "ANALYTICS_RESPONSE_INVALID"
        if failure_code is not None:
            return {
                "error": False,
                "status": "EXPERIMENTAL_ANALYTICS_API_DIAGNOSTIC_READY",
                "message": self._render_analytics_api_diagnostic(
                    date_from,
                    date_to,
                    None,
                    http_attempts[0],
                    failure_code,
                ),
                "read_only": True,
                "executed": False,
            }

        totals = result.get("totals")
        if not isinstance(totals, list):
            totals = None
        complete = (
            len(rows) < self.ANALYTICS_PAGE_SIZE
            and result.get("has_next") is not True
        )
        sample_shape = self._analytics_diagnostic_shape(rows[0]) if rows else []
        metric_summaries = []
        for index, metric_name in enumerate(self.ANALYTICS_METRICS):
            total_value = None
            if totals is not None and index < len(totals):
                total_value, _ = _analytics_metric_value(
                    totals[index], metric_name
                )
            row_sum = Decimal("0")
            missing = 0
            for row in rows:
                values = row.get("metrics") if isinstance(row, dict) else None
                value, issue = _analytics_metric_value(
                    values[index]
                    if isinstance(values, list) and index < len(values)
                    else None,
                    metric_name,
                )
                if issue:
                    missing += 1
                else:
                    row_sum += value
            metric_summaries.append(
                {
                    "name": metric_name,
                    "total": _public_analytics_number(total_value),
                    "row_sum": _public_analytics_number(row_sum)
                    if missing == 0
                    else None,
                    "missing_rows": missing,
                }
            )

        day_values = []
        for row in rows:
            dimensions = row.get("dimensions") if isinstance(row, dict) else None
            if not isinstance(dimensions, list) or not dimensions:
                continue
            dimension = dimensions[0]
            raw_day = dimension.get("id") if isinstance(dimension, dict) else None
            if not isinstance(raw_day, str) or not re.match(
                r"^\d{4}-\d{2}-\d{2}", raw_day
            ):
                continue
            try:
                day_values.append(date.fromisoformat(raw_day[:10]).isoformat())
            except ValueError:
                continue
        return {
            "error": False,
            "status": "EXPERIMENTAL_ANALYTICS_API_DIAGNOSTIC_READY",
            "message": self._render_analytics_api_diagnostic(
                date_from,
                date_to,
                {
                    "rows": len(rows),
                    "complete": complete,
                    "totals_count": len(totals) if totals is not None else None,
                    "metrics": metric_summaries,
                    "days": day_values,
                    "shape": sample_shape,
                },
                http_attempts[0],
                None,
            ),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _analytics_diagnostic_shape(row):
        def value_type(value):
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "bool"
            if isinstance(value, int):
                return "int"
            if isinstance(value, float):
                return "number"
            if isinstance(value, str):
                return "string"
            if isinstance(value, dict):
                return "object"
            if isinstance(value, list):
                return "array"
            return "other"

        if not isinstance(row, dict):
            return []
        fields = [
            f"{key}={value_type(row.get(key))}"
            for key in ("dimensions", "metrics")
            if key in row
        ]
        dimensions = row.get("dimensions")
        if isinstance(dimensions, list) and dimensions and isinstance(
            dimensions[0], dict
        ):
            fields.extend(
                f"dimensions[0].{key}={value_type(dimensions[0].get(key))}"
                for key in ("id", "name")
                if key in dimensions[0]
            )
        metrics = row.get("metrics")
        if isinstance(metrics, list):
            fields.extend(
                f"metrics[{index}]={value_type(value)}"
                for index, value in enumerate(metrics[:3])
            )
        return fields

    @staticmethod
    def _render_analytics_api_diagnostic(
        date_from, date_to, data, http_attempts, failure_code
    ):
        lines = [
            f"🔎 Ozon Analytics за {date_from} — {date_to}",
            "Запрос: метрики ordered_units, cancellations, returns; разрез day; limit 1000.",
        ]
        if failure_code:
            lines.append(f"Ответ не удалось проверить ({failure_code}).")
        elif not isinstance(data, dict):
            lines.append("Ответ не удалось проверить.")
        else:
            lines.append(
                f"Строк дневных данных: {data['rows']}; выборка до 1000 строк: "
                + ("полная." if data["complete"] else "неполная.")
            )
            days = data.get("days") or []
            if days:
                lines.append(f"Даты в строках: {min(days)} — {max(days)}.")
            for metric in data.get("metrics", []):
                total = (
                    str(metric["total"])
                    if metric["total"] is not None
                    else "нет в totals"
                )
                row_sum = (
                    str(metric["row_sum"])
                    if metric["row_sum"] is not None
                    else f"неполная ({metric['missing_rows']} строк без значения)"
                )
                lines.append(
                    f"{metric['name']}: totals={total}; сумма строк={row_sum}."
                )
            lines.append(
                "Полей первой строки: "
                + (", ".join(data.get("shape") or []) or "нет строк")
                + f"; totals: {data.get('totals_count') if data.get('totals_count') is not None else 'нет'} значений."
            )
        lines.append(
            f"HTTP-попыток: {http_attempts}; максимум {ExperimentalStoreEconomicsRuntimeService.ANALYTICS_DIAGNOSTIC_MAX_HTTP_ATTEMPTS}; одна страница."
        )
        return "\n".join(lines)

    @staticmethod
    def _analytics_diagnostic_error(message):
        return {
            "error": False,
            "status": "EXPERIMENTAL_ANALYTICS_API_DIAGNOSTIC_UNAVAILABLE",
            "message": message,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _returns_diagnostic_error(message):
        return {
            "error": False,
            "status": "EXPERIMENTAL_RETURNS_API_DIAGNOSTIC_UNAVAILABLE",
            "message": message,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _safe_returns_diagnostic_error_code(response):
        if isinstance(response, dict):
            raw_code = response.get("code") or response.get("error_code")
            if raw_code is not None:
                code = str(raw_code).upper()
                if re.fullmatch(r"[A-Z0-9_]{1,64}", code):
                    return code
        return "OZON_RETURNS_REQUEST_FAILED"

    @staticmethod
    def _safe_diagnostic_label(value, fallback):
        text = str(value or "").strip()
        if not text:
            return fallback
        text = re.sub(r"[^\w .-]", "", text, flags=re.UNICODE)[:64].strip()
        return text or fallback

    @staticmethod
    def _safe_diagnostic_timestamp(value):
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or len(value) > 40:
            return None
        if not re.fullmatch(r"[0-9TtZz:+.\-]+", value):
            return None
        return value

    @staticmethod
    def _returns_diagnostic_shape(row):
        def value_type(value):
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "bool"
            if isinstance(value, int):
                return "int"
            if isinstance(value, float):
                return "number"
            if isinstance(value, str):
                return "string"
            if isinstance(value, dict):
                return "object"
            if isinstance(value, list):
                return "array"
            return "other"

        visual = row.get("visual") if isinstance(row.get("visual"), dict) else {}
        status = visual.get("status") if isinstance(visual.get("status"), dict) else {}
        product = row.get("product") if isinstance(row.get("product"), dict) else {}
        fields = (
            ("id", row.get("id", row.get("return_id"))),
            ("type", row.get("type")),
            ("schema", row.get("schema")),
            ("product.quantity", product.get("quantity")),
            ("visual.change_moment", visual.get("change_moment")),
            ("visual.status.sys_name", status.get("sys_name")),
        )
        return [
            f"{name}={value_type(value)}"
            for name, value in fields
            if value is not None
        ]

    @staticmethod
    def _format_returns_diagnostic_groups(groups, kind):
        if not groups:
            return "нет"
        labels = sorted(groups)
        # Keep the button response comfortably below Telegram's 4096-char limit
        # even when the API returns many distinct type/status labels.
        shown = labels[:6]
        parts = []
        for label in shown:
            value = groups[label]
            if kind == "type":
                quantity_text = str(value["quantity"])
                if value["quantity_missing"]:
                    quantity_text += (
                        f", неизвестно в {value['quantity_missing']} строках"
                    )
                parts.append(
                    f"{label}: строк {value['rows']}, quantity {quantity_text}"
                )
            else:
                parts.append(f"{label}: {value}")
        if len(labels) > len(shown):
            parts.append(f"прочих категорий: {len(labels) - len(shown)}")
        return "; ".join(parts)

    def _render_returns_api_diagnostic(
        self,
        date_from,
        date_to,
        schemas,
        sample_shape,
        http_attempts,
        failure_code,
    ):
        lines = [
            f"🔎 API возвратов за {date_from} — {date_to}",
            "Показываю только типы, статусы и количества; идентификаторы и товары скрыты.",
        ]
        for state in schemas:
            completeness = "полностью прочитан" if state["complete"] else "неполная страница"
            lines.append(
                f"{state['schema']}: страниц {state['page_count']}, "
                f"строк API {state['api_row_count']}, уникальных ID "
                f"{state['unique_count']} ({completeness})."
            )
            lines.append(
                "  Типы: "
                + self._format_returns_diagnostic_groups(state["types"], "type")
            )
            if state["statuses"]:
                lines.append(
                    "  Статусы: "
                    + self._format_returns_diagnostic_groups(
                        state["statuses"], "status"
                    )
                )
            moments = sorted(set(state["change_moments"]))
            if moments:
                if len(moments) == 1:
                    lines.append("  visual.change_moment: " + moments[0])
                else:
                    lines.append(
                        "  visual.change_moment в ответах: "
                        + moments[0]
                        + " — "
                        + moments[-1]
                    )
        if sample_shape:
            lines.append("Поля и типы в первой записи: " + ", ".join(sample_shape))
        if failure_code:
            lines.append(f"Диагностика остановлена: {failure_code}.")
        complete = bool(schemas) and not failure_code and all(
            state["complete"] for state in schemas
        )
        lines.append(
            "Полная выборка FBO/FBS: "
            + ("да" if complete else "нет; не считайте итог полным.")
        )
        lines.append(
            f"Фактических HTTP-попыток: {http_attempts}; "
            "лимит диагностики — не более 10, 2 страниц на схему, 120 секунд."
        )
        return "\n".join(lines)

    def _report_scope_key(self, user_id):
        user_key = self._user_key(user_id)
        if not user_key:
            return None
        tenant_scope = self._user_key(get_current_tenant_user_id()) or user_key
        return user_key, tenant_scope

    def _save_report_views(
        self,
        user_id,
        summary_text,
        details_text,
        date_from=None,
        date_to=None,
        report_view_id=None,
    ):
        scope = self._report_scope_key(user_id)
        if scope is None:
            return None
        view_id = str(report_view_id or uuid4().hex[:12]).strip()
        if not re.fullmatch(r"[0-9a-f]{12}", view_id):
            view_id = uuid4().hex[:12]
        key = (*scope, view_id)
        with self._report_views_lock:
            self._report_views[key] = {
                "summary": summary_text,
                "details": details_text,
                "date_from": str(date_from) if date_from is not None else None,
                "date_to": str(date_to) if date_to is not None else None,
                "report_view_id": view_id,
            }
            self._report_views.move_to_end(key)
            self._latest_report_views[scope] = key
            while len(self._report_views) > self.REPORT_CACHE_MAX_SCOPES:
                evicted_key, _ = self._report_views.popitem(last=False)
                evicted_scope = (evicted_key[0], evicted_key[1])
                if self._latest_report_views.get(evicted_scope) == evicted_key:
                    self._latest_report_views.pop(evicted_scope, None)
        return view_id

    def _get_report_view(self, user_id, report_view_id=None):
        scope = self._report_scope_key(user_id)
        if scope is None:
            return None
        with self._report_views_lock:
            if report_view_id is None:
                key = self._latest_report_views.get(scope)
            else:
                view_id = str(report_view_id or "").strip()
                if not re.fullmatch(r"[0-9a-f]{12}", view_id):
                    return None
                key = (*scope, view_id)
            cached = self._report_views.get(key)
            if isinstance(cached, dict):
                self._report_views.move_to_end(key)
                return dict(cached)
        return None

    def _get_cached_report_view(self, user_id, view, report_view_id=None):
        cached = self._get_report_view(user_id, report_view_id)
        if not isinstance(cached, dict) or not isinstance(cached.get(view), str):
            return {
                "error": False,
                "status": "EXPERIMENTAL_STORE_ECONOMICS_VIEW_EXPIRED",
                "message": (
                    "Подробности этого расчёта уже недоступны. "
                    "Сформируйте отчёт ещё раз."
                ),
                "read_only": True,
                "executed": False,
            }
        return {
            "error": False,
            "status": (
                "EXPERIMENTAL_STORE_ECONOMICS_DETAILS_READY"
                if view == "details"
                else "EXPERIMENTAL_STORE_ECONOMICS_READY"
            ),
            "message": cached[view],
            "report_view_id": cached.get("report_view_id"),
            "date_from": cached.get("date_from"),
            "date_to": cached.get("date_to"),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _base_metrics(cls, summary):
        fields = (
            "revenue",
            "revenue_tax_base",
            "discount_points",
            "net_accrual",
            "tax",
            "profit",
            "acquiring",
            "commission",
            "logistics",
            "other_fees",
        )
        result = {}
        for field in fields:
            value = cls._number(summary.get(field))
            if value is None:
                return None
            result[field] = value
        return result

    def _load_advertising(self, date_from, date_to, accepted_skus):
        service = self.advertising_service
        loader = getattr(service, "load", None)
        if not callable(loader) or not accepted_skus:
            return {"status": "UNAVAILABLE", "cpc": None, "campaign_count": None}
        try:
            result = loader(date_from, date_to, accepted_skus)
        except Exception:
            return {"status": "UNAVAILABLE", "cpc": None, "campaign_count": None}
        if not isinstance(result, dict) or result.get("error") is not False:
            return {"status": "UNAVAILABLE", "cpc": None, "campaign_count": None}
        if result.get("configured") is not True:
            return {"status": "NOT_CONFIGURED", "cpc": None, "campaign_count": None}
        amount = self._number(result.get("expense"))
        if (
            result.get("complete") is not True
            or amount is None
            or amount < 0
        ):
            return {"status": "INCOMPLETE", "cpc": None, "campaign_count": None}
        campaign_count = self._integer(result.get("campaign_count"))
        # Historical Performance CSV rows do not include campaign IDs, so the
        # advertising service may report zero IDs even when it found spend.
        # Zero therefore means "not available" here, not "no campaigns".
        if campaign_count == 0:
            campaign_count = None
        return {
            "status": "READY",
            "cpc": amount,
            "campaign_count": campaign_count,
            "scope": "CPC_MATCHED_SKUS",
        }

    def _load_analytics(self, date_from, date_to):
        getter = getattr(self.analytics_client, "get_analytics_data", None)
        if not callable(getter):
            return self._empty_analytics_result(
                "UNAVAILABLE", "ANALYTICS_CLIENT_UNAVAILABLE"
            )
        rows = []
        totals = None
        complete = False
        for page_number in range(self.ANALYTICS_MAX_PAGES):
            offset = page_number * self.ANALYTICS_PAGE_SIZE
            try:
                response = getter(
                    date_from,
                    date_to,
                    metrics=list(self.ANALYTICS_METRICS),
                    dimension=list(self.ANALYTICS_DIMENSIONS),
                    limit=self.ANALYTICS_PAGE_SIZE,
                    offset=offset,
                )
            except Exception:
                return self._empty_analytics_result(
                    "UNAVAILABLE" if page_number == 0 else "INCOMPLETE",
                    "ANALYTICS_REQUEST_FAILED"
                    if page_number == 0
                    else "ANALYTICS_PAGE_UNAVAILABLE",
                )
            if not isinstance(response, dict) or response.get("error") is True:
                diagnostic = self._analytics_response_failure_code(response)
                return self._empty_analytics_result(
                    "UNAVAILABLE" if page_number == 0 else "INCOMPLETE",
                    diagnostic
                    if page_number == 0
                    else "ANALYTICS_PAGE_UNAVAILABLE",
                )
            result = response.get("result")
            page_rows = result.get("data") if isinstance(result, dict) else None
            if not isinstance(page_rows, list) or len(page_rows) > self.ANALYTICS_PAGE_SIZE:
                return self._empty_analytics_result(
                    "INVALID", "ANALYTICS_DATA_MISSING"
                )
            if page_number == 0:
                page_totals = result.get("totals") if isinstance(result, dict) else None
                totals = page_totals if isinstance(page_totals, list) else None
            rows.extend(page_rows)
            if len(page_rows) < self.ANALYTICS_PAGE_SIZE:
                complete = True
                break
        if not complete:
            return self._empty_analytics_result(
                "INCOMPLETE", "ANALYTICS_PAGE_LIMIT_REACHED"
            )

        values = []
        issues = []
        for index, metric_name in enumerate(self.ANALYTICS_METRICS):
            total_value = None
            total_issue = None
            if isinstance(totals, list) and index < len(totals):
                total_value, total_issue = _analytics_metric_value(
                    totals[index], metric_name
                )
                if total_issue is None:
                    values.append(total_value)
                    issues.append(None)
                    continue

            value, issue = self._sum_analytics_rows(rows, index, metric_name)
            if issue is None:
                values.append(value)
                issues.append(None)
            else:
                values.append(None)
                issues.append(total_issue or issue)

        public_values = [
            _public_analytics_number(value)
            for value in values
        ]
        for index, value in enumerate(values):
            if value is not None and public_values[index] is None:
                issues[index] = self.ANALYTICS_METRICS[index].upper() + "_TOTAL_INVALID"
        ready_count = sum(issue is None for issue in issues)
        if ready_count == len(issues):
            status = "READY"
        elif ready_count:
            status = "PARTIAL"
        elif all(_is_missing_analytics_metric(issue) for issue in issues):
            status = "UNAVAILABLE"
        elif any(issue == "ANALYTICS_PAGE_LIMIT_REACHED" for issue in issues):
            status = "INCOMPLETE"
        else:
            status = "INVALID"
        return _analytics_result(
            dict(zip(self.ANALYTICS_METRICS, public_values)),
            dict(zip(self.ANALYTICS_METRICS, issues)),
            status,
        )

    @staticmethod
    def _analytics_response_failure_code(response):
        if not isinstance(response, dict):
            return "ANALYTICS_RESPONSE_UNAVAILABLE"
        code = response.get("code")
        status_code = response.get("status_code")
        try:
            status_code = int(status_code)
        except (TypeError, ValueError, OverflowError):
            status_code = None
        if code == "OZON_RATE_LIMITED" or status_code == 429:
            return "ANALYTICS_RATE_LIMITED"
        if status_code == 403 or code == "OZON_HTTP_403":
            return "ANALYTICS_ACCESS_DENIED"
        return "ANALYTICS_RESPONSE_UNAVAILABLE"

    def _fill_analytics_from_seller_api(self, analytics, date_from, date_to):
        """Use complete Seller API operational records when Analytics omits a metric.

        Cancellation counts are based on FBO/FBS postings created in the
        requested window that are currently cancelled. Return counts are based
        on FBO/FBS return records whose status changed in that window. These
        are explicitly named as fallbacks in the report because their date
        semantics differ from the Analytics metrics.
        """
        result = dict(analytics or {})
        # A shared API period does not prove that the event date is the same
        # cohort as ordered_units. Keep percentages hidden until the source
        # contract confirms that relationship.
        result["cancellations_cohort_compatible"] = False
        result["returns_cohort_compatible"] = False
        if result.get("cancellations") is None:
            value = self._load_cancelled_posting_units(date_from, date_to)
            if value is not None:
                result["cancellations"] = value
                result["cancellations_status"] = "READY"
                result["cancellations_diagnostic"] = None
                result["cancellations_source"] = "SELLER_POSTINGS"
            else:
                result["cancellations_source"] = "SELLER_API_UNAVAILABLE"
        else:
            result["cancellations_source"] = "ANALYTICS"

        if result.get("returns") is None:
            value = self._load_return_units(date_from, date_to)
            if value is not None:
                result["returns"] = value
                result["returns_status"] = "READY"
                result["returns_diagnostic"] = None
                result["returns_source"] = "SELLER_RETURNS"
            else:
                result["returns_source"] = "SELLER_API_UNAVAILABLE"
        else:
            result["returns_source"] = "ANALYTICS"

        return result

    def _load_cancelled_posting_units(self, date_from, date_to):
        client = self.analytics_client
        fbo_getter = getattr(client, "get_fbo_postings", None)
        fbs_getter = getattr(client, "get_fbs_postings", None)
        if not callable(fbo_getter) or not callable(fbs_getter):
            return None

        scoped_postings = []
        try:
            fbo = fbo_getter(
                since=date_from,
                to=date_to,
                limit=(
                    100 * self.OPERATIONAL_POSTING_MAX_PAGES
                ),
                offset=0,
                direction="ASC",
                status="cancelled",
            )
            fbs = fbs_getter(
                since=date_from,
                to=date_to,
                status="cancelled",
                max_pages=self.OPERATIONAL_POSTING_MAX_PAGES,
            )
        except Exception:
            return None

        fbo_postings, fbo_complete = _extract_postings_page(fbo)
        fbs_postings, fbs_complete = _extract_postings_page(fbs)
        if not fbo_complete or not fbs_complete:
            return None
        scoped_postings.extend(("FBO", row) for row in fbo_postings)
        scoped_postings.extend(("FBS", row) for row in fbs_postings)

        total = 0
        seen_postings = {}
        for schema, posting in scoped_postings:
            if not isinstance(posting, dict):
                return None
            status = str(posting.get("status") or "").casefold()
            if status not in {"cancelled", "canceled"}:
                continue
            posting_number = self._text(posting.get("posting_number"))
            if not posting_number:
                return None
            products = posting.get("products")
            if not isinstance(products, list):
                return None
            quantities = []
            for product in products:
                if not isinstance(product, dict):
                    return None
                quantity = self._integer(product.get("quantity"))
                if quantity is None:
                    return None
                sku = self._text(product.get("sku"))
                quantities.append((sku, quantity))
            identity = (schema, posting_number)
            signature = (status, tuple(quantities))
            if identity in seen_postings:
                if seen_postings[identity] != signature:
                    return None
                continue
            seen_postings[identity] = signature
            total += sum(quantity for _sku, quantity in quantities)
        return total

    def _load_return_units(self, date_from, date_to):
        getter = getattr(self.analytics_client, "get_returns", None)
        if not callable(getter):
            return None

        total = 0
        for schema in ("FBO", "FBS"):
            last_id = 0
            seen_records = {}
            for page_number in range(self.OPERATIONAL_RETURN_MAX_PAGES):
                try:
                    response = getter(
                        return_schema=schema,
                        since=date_from,
                        to=date_to,
                        limit=500,
                        last_id=last_id,
                    )
                except Exception:
                    return None
                if not isinstance(response, dict) or response.get("error") is True:
                    return None
                rows = response.get("returns")
                if not isinstance(rows, list):
                    return None
                for row in rows:
                    if not isinstance(row, dict):
                        return None
                    raw_id = row.get("id")
                    if raw_id is None:
                        raw_id = row.get("return_id")
                    record_id = self._integer(raw_id)
                    if record_id is None or record_id <= 0:
                        return None
                    record_type = str(row.get("type") or "").casefold()
                    product = row.get("product")
                    quantity = None
                    if record_type == "clientreturn":
                        if not isinstance(product, dict):
                            return None
                        quantity = self._integer(product.get("quantity"))
                        if quantity is None:
                            return None
                    # Compare the full API record, including product identity.
                    # A repeated return ID with the same quantity but a different
                    # product must not silently count as a harmless duplicate.
                    signature = self._freeze_api_value(row)
                    if record_id in seen_records:
                        if seen_records[record_id] != signature:
                            return None
                        continue
                    seen_records[record_id] = signature
                    if record_type == "clientreturn":
                        total += quantity
                if response.get("has_next") is not True:
                    break
                if not rows:
                    return None
                cursor_value = rows[-1].get("id")
                if cursor_value is None:
                    cursor_value = rows[-1].get("return_id")
                next_id = self._integer(cursor_value)
                if next_id is None:
                    return None
                if next_id <= last_id:
                    return None
                last_id = next_id
            else:
                return None
        return total

    @classmethod
    def _empty_analytics_result(cls, status, diagnostic):
        return _analytics_result(
            {metric: None for metric in cls.ANALYTICS_METRICS},
            {metric: diagnostic for metric in cls.ANALYTICS_METRICS},
            status,
        )

    def _sum_analytics_rows(self, rows, metric_index, metric_name):
        total = Decimal("0")
        for row in rows:
            if not isinstance(row, dict):
                return None, "ANALYTICS_ROW_INVALID"
            values = row.get("metrics")
            if not isinstance(values, list):
                return None, "ANALYTICS_METRICS_INVALID"
            if metric_index >= len(values):
                return None, metric_name.upper() + "_NOT_RETURNED"
            amount, issue = _analytics_metric_value(
                values[metric_index], metric_name
            )
            if issue is not None:
                return None, issue
            total += amount
            if not total.is_finite():
                return None, metric_name.upper() + "_TOTAL_INVALID"
        return total, None

    @classmethod
    def _fee_subcategories(cls, summary):
        breakdown = summary.get("fee_breakdown")
        accrual_types = cls._accrual_type_entries(summary)
        result = {}
        for category, matchers in cls.FEE_LABEL_MATCHERS.items():
            amounts = []
            if category == "paid_storage" and accrual_types:
                for entry in accrual_types:
                    if cls._matches_fee_category(
                        entry["labels"], category, matchers
                    ):
                        amount = cls._number(entry["amount"])
                        if amount is not None:
                            amounts.append(amount)
            if not amounts and isinstance(breakdown, dict):
                for label, value in breakdown.items():
                    matched = cls._matches_fee_category(
                        [label], category, matchers
                    )
                    if matched:
                        amount = cls._number(value)
                        if amount is not None:
                            amounts.append(amount)
            total = sum(amounts)
            result[category] = (
                round(total, 2)
                if amounts and isfinite(total)
                else None
            )
        return result

    @classmethod
    def _commission_from_explicit_types(cls, summary):
        accrual_types = cls._accrual_type_entries(summary)
        amounts = []
        for entry in accrual_types:
            if cls._is_explicit_commission_label(entry["labels"]):
                amount = cls._number(entry["amount"])
                if amount is None:
                    return None
                amounts.append(amount)
        if amounts:
            total = sum(amounts)
            return round(total, 2) if isfinite(total) else None

        breakdown = summary.get("fee_breakdown")
        if not isinstance(breakdown, dict):
            return None
        amounts = []
        for label, value in breakdown.items():
            if not cls._is_explicit_commission_label([label]):
                continue
            amount = cls._number(value)
            if amount is None:
                return None
            amounts.append(amount)
        if not amounts:
            return None
        total = sum(amounts)
        return round(total, 2) if isfinite(total) else None

    def _load_finance_realization_commission(
        self,
        date_from,
        date_to,
        finance_service=None,
    ):
        """Load sale and return commission from complete monthly realization reports.

        The posting-accrual endpoint can omit return commission rows. The
        realization report is therefore preferred when the requested interval is
        made of whole calendar months. Partial-month results stay on the existing
        fallback path and are marked provisional when return commission is not
        evidenced.
        """
        try:
            start = date.fromisoformat(str(date_from))
            end = date.fromisoformat(str(date_to))
        except (TypeError, ValueError):
            return self._empty_realization_commission(
                "OZON_FINANCE_REALIZATION_DATE_RANGE_INVALID"
            )
        if end < start:
            return self._empty_realization_commission(
                "OZON_FINANCE_REALIZATION_DATE_RANGE_INVALID"
            )
        if start.day != 1 or end.day != monthrange(end.year, end.month)[1]:
            return self._empty_realization_commission(
                "OZON_FINANCE_REALIZATION_PERIOD_NOT_FULL_MONTHS"
            )

        ozon_client = getattr(finance_service, "ozon", None)
        getter = getattr(ozon_client, "get_monthly_realization_report", None)
        if not callable(getter):
            return self._empty_realization_commission(
                "OZON_FINANCE_REALIZATION_CLIENT_UNAVAILABLE"
            )

        result = self._empty_realization_commission(failure_code=None)
        result["available"] = True
        sale_total = 0.0
        return_total = 0.0
        current = date(start.year, start.month, 1)
        while current <= end:
            try:
                response = getter(current.year, current.month)
            except Exception:
                return self._empty_realization_commission(
                    "OZON_FINANCE_REALIZATION_REQUEST_FAILED"
                )
            if not isinstance(response, dict):
                return self._empty_realization_commission(
                    "OZON_FINANCE_REALIZATION_RESPONSE_UNAVAILABLE"
                )
            if response.get("error") is True:
                return self._empty_realization_commission(
                    self._safe_realization_commission_failure_code(
                        response.get("code"), response.get("status_code")
                    )
                )
            rows = response.get("rows")
            if not isinstance(rows, list):
                nested = response.get("result")
                rows = nested.get("rows") if isinstance(nested, dict) else None
            if not isinstance(rows, list) or not rows:
                return self._empty_realization_commission(
                    "OZON_FINANCE_REALIZATION_ROWS_UNAVAILABLE"
                )

            for row in rows:
                if not isinstance(row, dict):
                    return self._empty_realization_commission(
                        "OZON_FINANCE_REALIZATION_ROW_INVALID"
                    )
                result["row_count"] += 1
                delivery = row.get("delivery_commission")
                returned = row.get("return_commission")
                delivery_missing = delivery is None
                return_missing = returned is None
                if delivery_missing:
                    result["delivery_commission_missing_row_count"] += 1
                else:
                    result["delivery_commission_row_count"] += 1
                if return_missing:
                    result["return_commission_missing_row_count"] += 1
                else:
                    result["return_commission_row_count"] += 1
                if delivery_missing and return_missing:
                    return self._failed_realization_commission(
                        "OZON_FINANCE_REALIZATION_COMMISSION_MISSING",
                        result,
                    )
                if (
                    (not delivery_missing and not isinstance(delivery, dict))
                    or (not return_missing and not isinstance(returned, dict))
                ):
                    return self._failed_realization_commission(
                        "OZON_FINANCE_REALIZATION_ROW_INVALID",
                        result,
                    )
                # The monthly sales report stores the base Ozon commission in
                # ``standard_fee``. Its ``commission`` field can be zero even
                # when a nonzero fee is present. Convert the report's positive
                # fee values to the signed accrual convention used here.
                sale_amount = (
                    0.0
                    if delivery_missing
                    else self._number(delivery.get("standard_fee"))
                )
                return_amount = (
                    0.0
                    if return_missing
                    else self._number(returned.get("standard_fee"))
                )
                if sale_amount is None or return_amount is None:
                    return self._failed_realization_commission(
                        "OZON_FINANCE_REALIZATION_COMMISSION_INVALID",
                        result,
                    )
                sale_amount = -abs(sale_amount)
                return_amount = abs(return_amount)
                sale_total += sale_amount
                return_total += return_amount
                if sale_amount:
                    result["sale_fee_row_count"] += 1
                if return_amount:
                    result["return_fee_row_count"] += 1

            result["month_count"] += 1
            current = (
                date(current.year + 1, 1, 1)
                if current.month == 12
                else date(current.year, current.month + 1, 1)
            )

        result["sale_commission_amount"] = round(sale_total, 2)
        result["return_commission_amount"] = round(return_total, 2)
        if sale_total == 0 and return_total == 0:
            return self._failed_realization_commission(
                "OZON_FINANCE_REALIZATION_COMMISSION_ZERO",
                result,
            )
        result["commission"] = round(sale_total + return_total, 2)
        return result

    @staticmethod
    def _empty_realization_commission(failure_code):
        return {
            "available": False,
            "failure_code": failure_code,
            "month_count": 0,
            "row_count": 0,
            "delivery_commission_row_count": 0,
            "return_commission_row_count": 0,
            "delivery_commission_missing_row_count": 0,
            "return_commission_missing_row_count": 0,
            "sale_fee_row_count": 0,
            "sale_commission_amount": None,
            "return_fee_row_count": 0,
            "return_commission_amount": None,
            "commission": None,
        }

    @classmethod
    def _failed_realization_commission(cls, failure_code, partial_result):
        result = cls._empty_realization_commission(failure_code)
        for key in (
            "month_count",
            "row_count",
            "delivery_commission_row_count",
            "return_commission_row_count",
            "delivery_commission_missing_row_count",
            "return_commission_missing_row_count",
        ):
            result[key] = partial_result.get(key, 0)
        return result

    @classmethod
    def _safe_realization_commission_failure_code(cls, code, status_code=None):
        if code == "OZON_HTTP_ERROR":
            try:
                status = int(status_code)
            except (TypeError, ValueError, OverflowError):
                status = None
            if status is not None and 100 <= status <= 599:
                return f"OZON_HTTP_{status}"
        if isinstance(code, str):
            match = re.fullmatch(r"OZON_HTTP_(\d{3})", code)
            if match and 100 <= int(match.group(1)) <= 599:
                return code
            if (
                code in cls.REALIZATION_FAILURE_CODES
                or code in cls.OZON_REQUEST_FAILURE_CODES
            ):
                return code
        return "OZON_FINANCE_REALIZATION_RESPONSE_UNAVAILABLE"

    @classmethod
    def _accrual_type_entries(cls, summary):
        source = summary.get("accrual_type_breakdown")
        if not isinstance(source, dict):
            return []
        entries = []
        for raw_id, raw_entry in source.items():
            if not isinstance(raw_entry, dict):
                continue
            try:
                int(raw_id)
            except (TypeError, ValueError, OverflowError):
                continue
            labels = [
                cls._text(raw_entry.get("description")),
                cls._text(raw_entry.get("name")),
            ]
            labels = [label for label in labels if label]
            amount = cls._number(raw_entry.get("amount"))
            if labels and amount is not None:
                entries.append(
                    {"id": str(raw_id), "labels": labels, "amount": amount}
                )
        return entries

    @classmethod
    def _accrual_category_diagnostics(cls, summary):
        entries = cls._accrual_type_entries(summary)
        labels = (
            [entry["labels"] for entry in entries]
            if entries
            else [
                [cls._text(label)]
                for label in (summary.get("fee_breakdown") or {})
                if cls._text(label)
            ]
        )
        return {
            "fee_type_count": len(labels),
            "commission_matches": sum(
                int(cls._is_explicit_commission_label(type_labels))
                for type_labels in labels
            ),
            "storage_matches": sum(
                int(
                    cls._matches_fee_category(
                        type_labels,
                        "paid_storage",
                        cls.FEE_LABEL_MATCHERS["paid_storage"],
                    )
                )
                for type_labels in labels
            ),
        }

    def _load_finance_accrual_posting_categories(
        self,
        date_from,
        date_to,
        finance_service=None,
    ):
        """Read explicit fee types from the active Seller API accrual endpoint.

        Posting numbers are taken from the period's already-read by-day rows.
        They are used only as lookup keys here; no cost is attributed to a SKU.
        """
        getter = getattr(
            self.finance_transaction_client,
            "get_accruals_by_postings",
            None,
        )
        if not callable(getter):
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE"
            )

        posting_number_getter = getattr(
            finance_service,
            "get_period_posting_numbers",
            None,
        )
        if not callable(posting_number_getter):
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_NUMBERS_UNAVAILABLE"
            )
        try:
            numbers_result = posting_number_getter(date_from, date_to)
        except Exception:
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_NUMBERS_UNAVAILABLE"
            )
        if not isinstance(numbers_result, dict) or numbers_result.get("error") is True:
            return self._empty_accrual_posting_categories(
                self._safe_accrual_posting_failure_code(
                    numbers_result.get("code")
                    if isinstance(numbers_result, dict)
                    else None
                )
            )

        posting_numbers = numbers_result.get("posting_numbers")
        if not isinstance(posting_numbers, list) or any(
            not isinstance(value, str) or not value.strip()
            for value in posting_numbers
        ):
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_NUMBERS_INVALID"
            )
        posting_numbers = list(dict.fromkeys(value.strip() for value in posting_numbers))
        if not posting_numbers:
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_NUMBERS_EMPTY"
            )

        accrual_types = getattr(finance_service, "accrual_types", None)
        if not isinstance(accrual_types, dict) or not accrual_types:
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_ACCRUAL_TYPES_UNAVAILABLE"
            )

        batches = [
            posting_numbers[offset:offset + self.ACCRUAL_POSTING_BATCH_SIZE]
            for offset in range(0, len(posting_numbers), self.ACCRUAL_POSTING_BATCH_SIZE)
        ]
        workers = min(self.ACCRUAL_POSTING_WORKERS, len(batches))
        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(copy_context().run, getter, batch)
                    for batch in batches
                ]
                responses = [future.result() for future in futures]
        except Exception:
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_POSTING_CLIENT_EXCEPTION"
            )

        requested = set(posting_numbers)
        returned = set()
        accrual_rows = []
        for response in responses:
            if not isinstance(response, dict):
                return self._empty_accrual_posting_categories(
                    "OZON_FINANCE_ACCRUAL_POSTINGS_RESPONSE_INVALID"
                )
            if response.get("error") is True:
                return self._empty_accrual_posting_categories(
                    self._safe_accrual_posting_failure_code(response.get("code"))
                )
            posting_accruals = response.get("posting_accruals")
            if response.get("error") is not False or not isinstance(
                posting_accruals, list
            ):
                return self._empty_accrual_posting_categories(
                    "OZON_FINANCE_ACCRUAL_POSTINGS_RESPONSE_INVALID"
                )
            for posting in posting_accruals:
                if not isinstance(posting, dict):
                    return self._empty_accrual_posting_categories(
                        "OZON_FINANCE_ACCRUAL_POSTINGS_RESPONSE_INVALID"
                    )
                posting_number = str(posting.get("posting_number") or "").strip()
                accruals = posting.get("accruals")
                if (
                    not posting_number
                    or posting_number not in requested
                    or posting_number in returned
                    or not isinstance(accruals, list)
                    or any(not isinstance(item, dict) for item in accruals)
                ):
                    return self._empty_accrual_posting_categories(
                        "OZON_FINANCE_ACCRUAL_POSTINGS_SCOPE_INVALID"
                    )
                returned.add(posting_number)
                accrual_rows.extend(accruals)

        if returned != requested:
            return self._empty_accrual_posting_categories(
                "OZON_FINANCE_ACCRUAL_POSTINGS_SCOPE_INVALID"
            )

        result = {
            **self._empty_accrual_posting_categories(failure_code=None),
            "available": True,
            "posting_count": len(returned),
            "operation_count": len(accrual_rows),
        }
        commission_total = 0.0
        commission_count = 0
        commission_invalid = False
        commission_sale_total = 0.0
        commission_sale_count = 0
        commission_sale_invalid = False
        commission_refund_total = 0.0
        commission_refund_count = 0
        commission_refund_invalid = False
        commission_other_total = 0.0
        commission_other_count = 0
        commission_other_invalid = False
        unmapped_type_count = 0
        unmapped_type_total = 0.0
        unmapped_type_invalid = False
        storage_total = 0.0
        storage_count = 0
        storage_invalid = False

        for accrual in accrual_rows:
            try:
                type_id = int(accrual.get("type_id"))
            except (TypeError, ValueError, OverflowError):
                unmapped_type_count += 1
                raw_accrued = accrual.get("accrued")
                amount = self._number(
                    raw_accrued.get("amount")
                    if isinstance(raw_accrued, dict)
                    else None
                )
                if amount is None:
                    unmapped_type_invalid = True
                else:
                    unmapped_type_total += amount
                continue
            type_info = accrual_types.get(type_id)
            if not isinstance(type_info, dict):
                unmapped_type_count += 1
                raw_accrued = accrual.get("accrued")
                amount = self._number(
                    raw_accrued.get("amount")
                    if isinstance(raw_accrued, dict)
                    else None
                )
                if amount is None:
                    unmapped_type_invalid = True
                else:
                    unmapped_type_total += amount
                continue
            labels = [
                self._text(type_info.get("description")),
                self._text(type_info.get("name")),
            ]
            labels = [label for label in labels if label]
            is_commission = self._is_explicit_commission_label(labels)
            commission_kind = self._commission_label_kind(labels)
            is_storage = self._matches_fee_category(
                labels,
                "paid_storage",
                self.FEE_LABEL_MATCHERS["paid_storage"],
            )
            if not is_commission and not is_storage:
                continue

            accrued = accrual.get("accrued")
            amount = self._number(
                accrued.get("amount") if isinstance(accrued, dict) else None
            )
            if is_commission:
                commission_count += 1
                if amount is None:
                    commission_invalid = True
                else:
                    commission_total += amount
                if commission_kind == "sale":
                    commission_sale_count += 1
                    if amount is None:
                        commission_sale_invalid = True
                    else:
                        commission_sale_total += amount
                elif commission_kind == "refund":
                    commission_refund_count += 1
                    if amount is None:
                        commission_refund_invalid = True
                    else:
                        commission_refund_total += amount
                else:
                    commission_other_count += 1
                    if amount is None:
                        commission_other_invalid = True
                    else:
                        commission_other_total += amount
            if is_storage:
                storage_count += 1
                if amount is None:
                    storage_invalid = True
                else:
                    storage_total += amount

        result["commission_operation_count"] = commission_count
        result["commission_sale_operation_count"] = commission_sale_count
        result["commission_refund_operation_count"] = commission_refund_count
        result["commission_other_operation_count"] = commission_other_count
        result["unmapped_type_count"] = unmapped_type_count
        if unmapped_type_count and not unmapped_type_invalid:
            result["unmapped_type_amount"] = round(unmapped_type_total, 2)
        result["storage_service_count"] = storage_count
        if commission_sale_count and not commission_sale_invalid:
            result["commission_sale_amount"] = round(commission_sale_total, 2)
        if commission_refund_count and not commission_refund_invalid:
            result["commission_refund_amount"] = round(commission_refund_total, 2)
        if commission_other_count and not commission_other_invalid:
            result["commission_other_amount"] = round(commission_other_total, 2)
        if commission_count and not commission_invalid:
            result["commission"] = round(commission_total, 2)
        result["paid_storage"] = (
            round(storage_total, 2)
            if storage_count and not storage_invalid
            else None
        )
        return result

    @classmethod
    def _safe_accrual_posting_failure_code(cls, code):
        if isinstance(code, str) and code in cls.ACCRUAL_POSTING_FAILURE_CODES:
            return code
        if isinstance(code, str):
            match = re.fullmatch(r"OZON_HTTP_(\d{3})", code)
            if match and 100 <= int(match.group(1)) <= 599:
                return code
        return "OZON_FINANCE_ACCRUAL_POSTINGS_REQUEST_FAILED"

    @staticmethod
    def _empty_accrual_posting_categories(
        failure_code="OZON_FINANCE_POSTING_CLIENT_UNAVAILABLE",
    ):
        return {
            "available": False,
            "failure_code": failure_code,
            "posting_count": 0,
            "operation_count": 0,
            "commission_operation_count": 0,
            "commission_sale_operation_count": 0,
            "commission_sale_amount": None,
            "commission_refund_operation_count": 0,
            "commission_refund_amount": None,
            "commission_other_operation_count": 0,
            "commission_other_amount": None,
            "unmapped_type_count": 0,
            "unmapped_type_amount": None,
            "storage_service_count": 0,
            "paid_storage": None,
            "commission": None,
        }

    @classmethod
    def _commission_label_kind(cls, labels):
        normalized = [
            " ".join(cls._text(label).casefold().split()).rstrip(" .:;")
            for label in labels
        ]
        refund_aliases = (
            "возврат вознаграждения",
            "commission refund",
            "refund of commission",
        )
        if any(
            alias in label
            for label in normalized
            for alias in refund_aliases
        ):
            return "refund"
        sale_aliases = (
            "вознаграждение за продажу",
            "sale commission",
            "commission for sale",
        )
        if any(
            alias in label
            for label in normalized
            for alias in sale_aliases
        ):
            return "sale"
        if cls._is_explicit_commission_label(labels):
            return "other"
        return None

    @classmethod
    def _is_explicit_commission_label(cls, labels):
        aliases = tuple(cls.COMMISSION_FEE_LABELS)
        for label in labels:
            normalized = " ".join(cls._text(label).casefold().split())
            normalized = normalized.rstrip(" .:;")
            if normalized in cls.COMMISSION_FEE_LABELS:
                return True
            if any(alias in normalized for alias in aliases):
                return True
        return False

    @classmethod
    def _matches_fee_category(cls, labels, category, matchers):
        for label in labels:
            normalized = cls._text(label).casefold()
            if any(matcher in normalized for matcher in matchers):
                return True
            if category == "paid_storage":
                # The accrual dictionary may use the compact type name
                # "Размещение" while the Seller UI uses a longer label.
                last_word = re.sub(
                    r"[^a-zа-яё]+", " ", normalized
                ).split()
                if last_word and last_word[-1].startswith(
                    ("размещ", "placement")
                ):
                    return True
        return False

    @classmethod
    def _fee_breakdown(cls, summary):
        source = summary.get("fee_breakdown")
        if not isinstance(source, dict):
            return []
        result = []
        for raw_label, raw_amount in source.items():
            label = " ".join(cls._text(raw_label).split())
            amount = cls._number(raw_amount)
            if not label or amount is None or amount == 0:
                continue
            result.append({"label": label, "amount": round(amount, 2)})
        return sorted(
            result,
            key=lambda item: (-abs(item["amount"]), item["label"].casefold()),
        )

    @classmethod
    def _finance_advertising(cls, fee_breakdown):
        groups = {
            "CPC": {"amount": 0.0, "count": 0, "labels": []},
            "CPO": {"amount": 0.0, "count": 0, "labels": []},
            "CPM": {"amount": 0.0, "count": 0, "labels": []},
            "OTHER": {"amount": 0.0, "count": 0, "labels": []},
        }
        for item in fee_breakdown:
            label = item["label"]
            normalized = label.casefold().replace("_", " ")
            if not any(
                matcher in normalized
                for matcher in cls.ADVERTISING_FEE_MATCHERS
            ):
                continue
            if any(token in normalized for token in ("cpc", "click", "клик")):
                group = "CPC"
            elif any(token in normalized for token in ("cpo", "заказ", "order")):
                group = "CPO"
            elif any(token in normalized for token in ("cpm", "показ", "impression")):
                group = "CPM"
            else:
                group = "OTHER"
            target = groups[group]
            target["amount"] = round(target["amount"] + item["amount"], 2)
            target["count"] += 1
            target["labels"].append(label)
        return {
            "groups": groups,
            "has_explicit_types": any(group["count"] for group in groups.values()),
        }

    @classmethod
    def _build_expense_breakdown(cls, metrics, date_from, date_to):
        """Split the existing residual by explicit fee labels without re-adding it.

        Account-level net accrual and primary expenses remain authoritative.
        Fee labels only partition ``other_fees``; delivery details such as last
        mile are nested in logistics and therefore excluded from this split.
        """
        source_name = "FINANCE_ACCRUAL_BY_DAY"
        period = {"date_from": str(date_from), "date_to": str(date_to)}
        raw_entries = metrics.get("fee_breakdown") or []
        buckets = {
            "advertising": {
                name: {"amount": 0.0, "count": 0, "labels": []}
                for name in ("CPC", "CPO", "CPM", "OTHER")
            },
            "reverse_logistics": {"amount": 0.0, "count": 0, "labels": []},
            "cross_docking": {"amount": 0.0, "count": 0, "labels": []},
            "paid_storage": {"amount": 0.0, "count": 0, "labels": []},
            "other_services": {"amount": 0.0, "count": 0, "labels": []},
        }
        last_mile_labels = []
        classified_details = []
        posting_diagnostics = metrics.get("accrual_posting_category_diagnostics") or {}
        posting_storage_authoritative = (
            posting_diagnostics.get("available") is True
            and posting_diagnostics.get("paid_storage") is not None
        )
        storage_source = (
            "FINANCE_ACCRUAL_POSTINGS"
            if posting_storage_authoritative
            else source_name
        )
        last_mile = metrics.get("fee_subcategories", {}).get("last_mile")
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            label = cls._text(item.get("label"))
            amount = cls._number(item.get("amount"))
            if not label or amount is None:
                continue
            normalized = " ".join(label.casefold().split())
            if cls._matches_fee_category(
                [label], "last_mile", cls.FEE_LABEL_MATCHERS["last_mile"]
            ):
                last_mile_labels.append(label)
                classified_details.append(
                    {"label": label, "amount": round(amount, 2), "category": "last_mile_in_logistics"}
                )
                continue
            if cls._is_explicit_commission_label([label]) or any(
                matcher in normalized
                for matcher in ("комисс", "commission", "эквайр", "acquir")
            ):
                classified_details.append(
                    {"label": label, "amount": round(amount, 2), "category": "primary_expense"}
                )
                continue
            if cls._matches_fee_category(
                [label],
                "cross_docking",
                cls.FEE_LABEL_MATCHERS["cross_docking"],
            ):
                bucket = buckets["cross_docking"]
                category_name = "cross_docking"
            elif cls._matches_fee_category(
                [label],
                "reverse_logistics",
                cls.FEE_LABEL_MATCHERS["reverse_logistics"],
            ):
                bucket = buckets["reverse_logistics"]
                category_name = "reverse_logistics"
            elif cls._matches_fee_category(
                [label],
                "paid_storage",
                cls.FEE_LABEL_MATCHERS["paid_storage"],
            ):
                # The posting source can confirm a storage charge omitted from
                # the by-day label list. Use the already-resolved metric once.
                if metrics.get("fee_subcategories", {}).get("paid_storage") is not None:
                    classified_details.append(
                        {
                            "label": label,
                            "amount": round(amount, 2),
                            "category": (
                                "paid_storage_reference"
                                if posting_storage_authoritative
                                else "paid_storage"
                            ),
                            "source": source_name,
                            "additive": not posting_storage_authoritative,
                        }
                    )
                    continue
                bucket = buckets["paid_storage"]
                category_name = "paid_storage"
            elif any(
                matcher in normalized
                for matcher in ("логист", "достав", "logistic", "delivery")
            ):
                # General delivery types are already included in logistics.
                classified_details.append(
                    {"label": label, "amount": round(amount, 2), "category": "included_in_logistics"}
                )
                continue
            elif any(
                matcher in normalized
                for matcher in cls.ADVERTISING_FEE_MATCHERS
            ):
                if any(token in normalized for token in ("cpc", "click", "клик")):
                    group = "CPC"
                elif any(token in normalized for token in ("cpo", "заказ", "order")):
                    group = "CPO"
                elif any(token in normalized for token in ("cpm", "показ", "impression")):
                    group = "CPM"
                else:
                    group = "OTHER"
                bucket = buckets["advertising"][group]
                category_name = "advertising_" + group.casefold()
            else:
                bucket = buckets["other_services"]
                category_name = "other_services"
            bucket["amount"] = round(bucket["amount"] + amount, 2)
            bucket["count"] += 1
            bucket["labels"].append(label)
            classified_details.append(
                {"label": label, "amount": round(amount, 2), "category": category_name}
            )

        if metrics.get("fee_subcategories", {}).get("paid_storage") is not None:
            storage_bucket = buckets["paid_storage"]
            storage_bucket["amount"] = metrics["fee_subcategories"]["paid_storage"]
            storage_bucket["count"] = 1
            storage_bucket["labels"] = ["Подтверждённые начисления за размещение"]

        category_amounts = []
        normalized_buckets = {}
        for name, bucket in buckets.items():
            if name == "advertising":
                normalized_groups = {}
                for group_name, group in bucket.items():
                    value = round(group["amount"], 2) if group["count"] else None
                    normalized_groups[group_name] = {
                        "amount": value,
                        "count": group["count"],
                        "labels": list(group["labels"]),
                        "source": source_name if group["count"] else None,
                        "period": period,
                        "complete": bool(group["count"]),
                    }
                    if value is not None:
                        category_amounts.append(value)
                normalized_buckets[name] = normalized_groups
                continue
            value = round(bucket["amount"], 2) if bucket["count"] else None
            normalized_buckets[name] = {
                "amount": value,
                "count": bucket["count"],
                "labels": list(bucket["labels"]),
                "source": (
                    storage_source
                    if name == "paid_storage" and bucket["count"]
                    else source_name if bucket["count"] else None
                ),
                "period": period,
                "complete": bool(bucket["count"]),
            }
            if value is not None:
                category_amounts.append(value)

        reported_other_fees = cls._number(metrics.get("other_fees"))
        net_accrual = cls._number(metrics.get("net_accrual"))
        revenue = cls._number(metrics.get("revenue"))
        acquiring = cls._number(metrics.get("acquiring"))
        commission = cls._number(metrics.get("commission"))
        logistics = cls._number(metrics.get("logistics"))
        if all(
            value is not None
            for value in (net_accrual, revenue, acquiring, commission, logistics)
        ):
            other_fees = round(
                net_accrual - revenue - acquiring - commission - logistics,
                2,
            )
        else:
            other_fees = reported_other_fees or 0.0
        classified_total = round(sum(category_amounts), 2)
        unallocated = round(other_fees - classified_total, 2)
        residual_available = reported_other_fees is not None or net_accrual is not None
        reported_other_fees_delta = (
            round(other_fees - reported_other_fees, 2)
            if reported_other_fees is not None
            else None
        )
        breakdown_available = bool(raw_entries) or abs(other_fees) <= 0.01
        classification_complete = (
            residual_available
            and breakdown_available
            and abs(unallocated) <= 0.01
            and (reported_other_fees_delta is None or abs(reported_other_fees_delta) <= 0.01)
        )
        unallocated_result = {
            "amount": unallocated if residual_available else None,
            "source": "NET_ACCRUAL_RECONCILIATION" if residual_available else None,
            "period": period,
            "complete": residual_available,
        }
        last_mile_result = {
            "amount": last_mile,
            "labels": last_mile_labels,
            "source": source_name if last_mile is not None else None,
            "period": period,
            "complete": last_mile is not None,
            "included_in": "logistics",
            "additive": False,
        }
        if (
            metrics.get("fee_subcategories", {}).get("paid_storage") is not None
            and not any(
                detail["category"] == "paid_storage"
                for detail in classified_details
            )
        ):
            classified_details.append(
                {
                    "label": (
                        "Размещение на складе (начисления по отправлениям)"
                        if storage_source == "FINANCE_ACCRUAL_POSTINGS"
                        else "Размещение на складе (дневные начисления Ozon)"
                    ),
                    "amount": round(metrics["fee_subcategories"]["paid_storage"], 2),
                    "category": "paid_storage",
                }
            )
        return {
            "source": source_name if breakdown_available else None,
            "period": period,
            "complete": classification_complete,
            "classification_status": (
                "COMPLETE" if classification_complete else "PARTIAL"
            ),
            "categories": normalized_buckets,
            "last_mile": last_mile_result,
            "unallocated_adjustment": unallocated_result,
            "classified_other_fees": classified_total,
            "original_other_fees": round(other_fees, 2),
            "summary_other_fees": reported_other_fees,
            "summary_other_fees_delta": reported_other_fees_delta,
            "details": classified_details,
            "performance_cpc_additive": False,
        }

    @classmethod
    def _other_fee_details(cls, fee_breakdown):
        excluded_matchers = (
            *cls.ADVERTISING_FEE_MATCHERS,
            "эквайр",
            "acquir",
            "комисс",
            "commission",
            "логист",
            "достав",
            "logistic",
            "delivery",
            *(matcher for matchers in cls.FEE_LABEL_MATCHERS.values() for matcher in matchers),
        )
        reverse_logistics_matchers = cls.FEE_LABEL_MATCHERS[
            "reverse_logistics"
        ]
        return [
            item
            for item in fee_breakdown
            if " ".join(item["label"].casefold().split()).rstrip(" .:;")
            not in cls.COMMISSION_FEE_LABELS
            and (
                any(
                    matcher in item["label"].casefold()
                    for matcher in reverse_logistics_matchers
                )
                or not any(
                    matcher in item["label"].casefold()
                    for matcher in excluded_matchers
                )
            )
        ]

    @staticmethod
    def _render(date_from, date_to, metrics):
        advertising = metrics["advertising"]
        analytics = metrics["analytics"]
        fees = metrics["fee_subcategories"]
        breakdown = metrics["expense_breakdown"]
        categories = breakdown["categories"]
        revenue = metrics["revenue"]
        ad_groups = categories["advertising"]
        ad_lines = []
        for group_name in ("CPC", "CPO", "CPM", "OTHER"):
            group = ad_groups[group_name]
            if group["amount"] is not None:
                title = "прочие явные услуги" if group_name == "OTHER" else group_name
                ad_lines.append(
                    f"   • {title}: "
                    f"{_money_with_revenue_share(group['amount'], revenue)}"
                )
        if not ad_lines:
            ad_lines.append("   • Явные рекламные начисления не найдены")

        cpc_text = _money_or_status(
            advertising.get("cpc"), advertising.get("status")
        )
        if advertising.get("cpc") is not None:
            cpc_text = _money_with_revenue_share(
                advertising["cpc"], revenue
            )
        campaign_count = advertising.get("campaign_count")
        if isinstance(campaign_count, int) and not isinstance(campaign_count, bool):
            cpc_text += f" ({campaign_count} камп.)"
        ad_lines.append(
            "   • Performance CPC для сверки, не входит в сумму: " + cpc_text
        )

        ordered_units = analytics.get("ordered_units")
        ordered_text = _units_with_order_share(
            ordered_units, ordered_units, ordered=True
        )
        cancellations_source = analytics.get("cancellations_source")
        returns_source = analytics.get("returns_source")
        cancellation_text = _period_event_units(
            analytics.get("cancellations"),
            ordered_units,
            analytics.get("cancellations_cohort_compatible") is True,
            (
                "период создания отправлений и текущий статус не образуют подтверждённую когорту"
                if cancellations_source == "SELLER_POSTINGS"
                else "сопоставимость периода метрики с заказанными единицами не подтверждена"
            ),
        )
        returns_text = _period_event_units(
            analytics.get("returns"),
            ordered_units,
            analytics.get("returns_cohort_compatible") is True,
            (
                "возвраты выбраны по дате смены статуса, а не по дате заказа"
                if returns_source == "SELLER_RETURNS"
                else "сопоставимость периода метрики с заказанными единицами не подтверждена"
            ),
        )
        cancellation_label = (
            "Отменённые единицы (FBO/FBS, заказы периода)"
            if cancellations_source == "SELLER_POSTINGS"
            else "Отменённые единицы (Analytics)"
        )
        returns_label = (
            "Клиентские возвраты FBO/FBS (тип ClientReturn; статус изменён в периоде)"
            if returns_source == "SELLER_RETURNS"
            else "Возвраты (Analytics)"
        )
        if cancellation_text is None:
            cancellation_text = _unit_or_unconfirmed(
                analytics.get("cancellations"),
                analytics.get("cancellations_status"),
                analytics.get("cancellations_diagnostic"),
                "отменённых единиц",
            )
            if cancellations_source == "SELLER_API_UNAVAILABLE":
                cancellation_text += "; Seller API не вернул полный набор"
        if returns_text is None:
            returns_text = _unit_or_unconfirmed(
                analytics.get("returns"),
                analytics.get("returns_status"),
                analytics.get("returns_diagnostic"),
                "возвратов",
            )
            if returns_source == "SELLER_API_UNAVAILABLE":
                returns_text += "; Seller API не вернул полный набор"
        if ordered_text is None:
            ordered_text = _unit_or_unconfirmed(
                ordered_units,
                analytics.get("ordered_units_status"),
                analytics.get("ordered_units_diagnostic"),
                "заказанных единиц",
            )

        def category_amount(name):
            value = categories[name].get("amount")
            return (
                _money_with_revenue_share(value, revenue)
                if value is not None
                else "нет подтверждённых начислений"
            )

        commission_source = metrics.get("commission_source")
        commission_label = {
            "POSTING_SALE_COMMISSION": "Комиссия Ozon (предварительно; возвратная не подтверждена)",
            "FINANCE_REALIZATION_REPORT": "Комиссия Ozon (отчёт реализации)",
            "FINANCE_ACCRUAL_POSTINGS": "Комиссия Ozon (начисления по отправлениям)",
            "ACCRUAL_FEE_TYPES": "Комиссия Ozon (типы финансовых начислений)",
        }.get(commission_source, "Комиссия Ozon")
        unallocated = breakdown["unallocated_adjustment"].get("amount")
        unallocated_text = (
            _money_with_revenue_share(unallocated, revenue)
            if unallocated is not None
            else "не удалось сверить"
        )
        completeness_note = (
            "Разбивка расходов полная по доступным типам."
            if breakdown.get("complete") is True
            else "Разбивка расходов частичная; итог начислений сохранён."
        )

        lines = [
            f"🧪 Экономика магазина за период {date_from} — {date_to}",
            "",
            "1. Выручка общая (100%): " + _money(metrics["revenue"]),
            "2. Выручка ФНС (выручка − баллы): "
            + _money_with_revenue_share(metrics["revenue_tax_base"], revenue),
            "3. Баллы за скидки: "
            + _money_with_revenue_share(metrics["discount_points"], revenue),
            "4. Начисления Ozon нетто: "
            + _money_with_revenue_share(metrics["net_accrual"], revenue),
            "5. Налог: " + _money_with_revenue_share(metrics["tax"], revenue),
            "6. Прибыль без себестоимости: "
            + _money_with_revenue_share(metrics["profit"], revenue),
            "7. Реклама по начислениям Ozon:",
            *ad_lines,
            "8. Эквайринг: "
            + _money_with_revenue_share(metrics["acquiring"], revenue),
            f"9. {commission_label}: "
            + _money_with_revenue_share(metrics["commission"], revenue),
            "10. Логистика доставки: "
            + _money_with_revenue_share(metrics["logistics"], revenue),
            "   • До места выдачи и выдача товара, уже в логистике: "
            + (
                _money_with_revenue_share(fees["last_mile"], revenue)
                if fees.get("last_mile") is not None
                else "нет подтверждённой детализации"
            ),
            "11. Обратная логистика: " + category_amount("reverse_logistics"),
            "12. Кросс-докинг: " + category_amount("cross_docking"),
            "13. Размещение и хранение: " + category_amount("paid_storage"),
            "14. Остальные услуги по явным типам: " + category_amount("other_services"),
            "15. Неразнесённая сверочная разница (баланс, не отдельное начисление): "
            + unallocated_text,
            "16. Заказанные единицы (Analytics): " + ordered_text,
            f"17. {cancellation_label}: {cancellation_text}",
            f"18. {returns_label}: {returns_text}",
            "",
            "⚠️ Экспериментальный отчёт; прибыль без себестоимости не является чистой прибылью.",
            completeness_note,
            "Начисления уже включены в прибыль. Не складывайте подкатегории и сверочную разницу повторно; Performance CPC показан отдельно для сверки.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_details(date_from, date_to, metrics):
        breakdown = metrics["expense_breakdown"]
        categories = breakdown["categories"]
        revenue = metrics["revenue"]
        lines = [
            f"📋 Подробности экономики магазина за период {date_from} — {date_to}",
            "",
            "Итоговые суммы выручки, начислений, налога и прибыли взяты из существующего расчёта. Переразнесение меняет только аналитические категории, не net accrual и не прибыль.",
            "",
            "Сверка суммы: выручка + эквайринг + комиссия + логистика + расчётная строка прочих начислений = начисления Ozon нетто.",
            "Внутри строки прочих начислений подтверждённые CPC/CPO/CPM, обратная логистика, кросс-докинг, размещение и остальные услуги выделены один раз. Неразнесённая сверочная разница — баланс до общей суммы, а не самостоятельное удержание.",
            "Последняя миля показана как подкатегория логистики и не прибавляется повторно. Performance CPC — внешняя сверка и не входит в начисления.",
            "",
            "Источники категорий:",
        ]
        source_labels = {
            "FINANCE_ACCRUAL_BY_DAY": "финансовые начисления Ozon за период",
            "FINANCE_ACCRUAL_POSTINGS": "начисления Seller API по отправлениям",
            "NET_ACCRUAL_RECONCILIATION": "сверка с общими net accrual",
        }

        def add_source_line(title, item):
            amount = item.get("amount")
            value = (
                _money_with_revenue_share(amount, revenue)
                if amount is not None
                else "нет подтверждённых данных"
            )
            source = source_labels.get(item.get("source"), "источник не подтверждён")
            complete = "подтверждено" if item.get("complete") else "частичные данные"
            lines.append(f"• {title}: {value}; источник — {source}; статус — {complete}.")

        for group_name, group_title in (
            ("CPC", "Реклама CPC"),
            ("CPO", "Реклама CPO"),
            ("CPM", "Реклама CPM"),
            ("OTHER", "Другие явные рекламные услуги"),
        ):
            add_source_line(
                group_title,
                categories["advertising"][group_name],
            )
        for key, title in (
            ("reverse_logistics", "Обратная логистика"),
            ("cross_docking", "Кросс-докинг"),
            ("paid_storage", "Размещение и хранение"),
            ("other_services", "Остальные услуги по типам"),
        ):
            add_source_line(title, categories[key])
        add_source_line("Неразнесённая сверочная разница", breakdown["unallocated_adjustment"])
        last_mile = breakdown["last_mile"]
        add_source_line("Доставка до места выдачи и выдача товара (в составе логистики)", last_mile)
        if categories["paid_storage"].get("amount") is None:
            lines.append(
                "Плату за размещение можно сверить в Ozon Seller → Экономика магазина → "
                "Стоимость размещения на складе Ozon → Всего за период."
            )
        lines.extend(
            [
                "",
                "Строки финансового отчёта Ozon по категориям (сохранены подписи источника):",
            ]
        )
        for item in breakdown.get("details") or []:
            reference_note = (
                "; справочная сумма другого источника, не складывается повторно"
                if item.get("additive") is False
                else ""
            )
            lines.append(
                f"• «{item['label']}»: "
                f"{_money_with_revenue_share(item['amount'], revenue)} "
                f"[{item['category']}{reference_note}]."
            )
        if not breakdown.get("details"):
            lines.append("• Детальные типы начислений недоступны; остаток сохранён в сверке.")

        commission_source = metrics.get("commission_source")
        lines.extend(["", "Комиссия и детализация источника:"])
        realization = metrics.get("realization_commission_diagnostics") or {}
        if realization.get("available") is True:
            lines.append(
                "Источник — месячный отчёт реализации Ozon (/v2/finance/realization); "
                f"полных месяцев {realization.get('month_count', 0)}, строк отчёта "
                f"{realization.get('row_count', 0)}. Число строк отчёта не является числом продаж или заказанных единиц."
            )
            lines.append(
                f"Комиссия продажи: {realization.get('sale_fee_row_count', 0)} строк с суммой "
                f"{_money(realization.get('sale_commission_amount'))}; возврат: "
                f"{realization.get('return_fee_row_count', 0)} строк с суммой "
                f"{_money(realization.get('return_commission_amount'))}."
            )
        else:
            failure_code = ExperimentalStoreEconomicsRuntimeService._safe_realization_commission_failure_code(
                realization.get("failure_code")
            )
            lines.append(
                f"Месячный отчёт реализации не подтвердил комиссию ({failure_code}); "
                f"использован источник {commission_source or 'неизвестен'}, "
                "предварительная сумма может не включать возвратную комиссию."
            )
        posting = metrics.get("accrual_posting_category_diagnostics") or {}
        if posting.get("available") is True:
            def diagnostic_amount(count_key, amount_key):
                count = posting.get(count_key, 0)
                if count == 0:
                    return _money(0)
                amount = posting.get(amount_key)
                return _money(amount) if amount is not None else "сумма не подтверждена"

            unmapped_count = posting.get("unmapped_type_count", 0)
            unmapped_amount = posting.get("unmapped_type_amount")
            unmapped_text = (
                f"{unmapped_count} строк / {_money(unmapped_amount)}"
                if unmapped_count and unmapped_amount is not None
                else f"{unmapped_count} строк без суммы"
                if unmapped_count
                else "0 строк"
            )
            lines.append(
                "Список начислений по отправлениям: "
                f"записей {posting.get('posting_count', 0)}, "
                f"строк начислений {posting.get('operation_count', 0)}; "
                "комиссия продажи — строк "
                f"{posting.get('commission_sale_operation_count', 0)} / "
                f"{diagnostic_amount('commission_sale_operation_count', 'commission_sale_amount')}; возврат "
                f"— строк {posting.get('commission_refund_operation_count', 0)} / "
                f"{diagnostic_amount('commission_refund_operation_count', 'commission_refund_amount')}; размещение "
                f"— строк {posting.get('storage_service_count', 0)} / "
                f"{diagnostic_amount('storage_service_count', 'paid_storage')}; без типа в справочнике "
                f"{unmapped_text}."
            )
        else:
            code = ExperimentalStoreEconomicsRuntimeService._safe_accrual_posting_failure_code(
                posting.get("failure_code")
            )
            lines.append(f"Начисления по отправлениям недоступны ({code}).")
        accrual = metrics.get("accrual_diagnostics") or {}
        lines.append(
            "Справочник типов начислений: "
            f"{accrual.get('fee_type_count', 0)} типов, "
            f"явные совпадения комиссии {accrual.get('commission_matches', 0)}, "
            f"размещения {accrual.get('storage_matches', 0)}."
        )
        lines.extend(
            [
                "",
                "Analytics заказы, отмены и возвраты показываются отдельно. Отмены Seller API — отправления из фильтра дат, имеющие статус «Отменено» на момент запроса; возвраты Seller API — записи со сменой статуса в периоде.",
                "Разделение рекламы по кампаниям доступно только если источник предоставляет подтверждённые типы и суммы. CPC из Performance не складывается с CPC в начислениях.",
                "Себестоимость и Return COGS этим экспериментальным отчётом не вычитаются.",
            ]
        )
        return "\n".join(lines)

    def _summary_dependencies(self):
        query_service = self.query_service
        provider = getattr(query_service, "product_provider", None)
        summary_service = getattr(query_service, "summary_service", None)
        if not callable(provider) or summary_service is None:
            base = getattr(query_service, "base_service", None)
            provider = getattr(base, "product_provider", None)
            summary_service = getattr(base, "summary_service", None)
        return provider, summary_service

    @classmethod
    def _catalog_skus(cls, products):
        output = set()
        for product in products:
            if not isinstance(product, dict):
                continue
            sku = cls._text(product.get("sku"))
            if sku:
                output.add(sku)
        return output

    @staticmethod
    def _custom_period_retry():
        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_CUSTOM_PERIOD_INPUT_INVALID",
            "message": "Введите две корректные даты в формате 01.01.2026 - 02.02.2026 или отправьте «Отмена».",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_UNAVAILABLE",
            "message": "Не удалось сформировать экспериментальный расчёт. Код диагностики: " + code,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _user_key(user_id):
        value = str(user_id or "").strip()
        return value or None

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

    @staticmethod
    def _freeze_api_value(value):
        """Build a deterministic comparison key for an API JSON value."""
        if isinstance(value, dict):
            return tuple(
                (
                    str(key),
                    ExperimentalStoreEconomicsRuntimeService._freeze_api_value(
                        value[key]
                    ),
                )
                for key in sorted(value, key=lambda item: str(item))
            )
        if isinstance(value, list):
            return tuple(
                ExperimentalStoreEconomicsRuntimeService._freeze_api_value(item)
                for item in value
            )
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _number(value):
        number = ExperimentalStoreEconomicsRuntimeService._decimal(value)
        if number is None:
            return None
        output = float(number)
        return output if isfinite(output) else None

    @staticmethod
    def _decimal(value):
        if value is None or isinstance(value, bool):
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        return number if number.is_finite() else None

    @staticmethod
    def _integer(value):
        number = ExperimentalStoreEconomicsRuntimeService._decimal(value)
        if number is None or number < 0 or number != number.to_integral_value():
            return None
        return int(number)


def _money(value):
    return f"{float(value):,.2f} ₽".replace(",", " ")


def _money_with_revenue_share(value, revenue):
    amount = ExperimentalStoreEconomicsRuntimeService._number(value)
    denominator = ExperimentalStoreEconomicsRuntimeService._number(revenue)
    if amount is None:
        return "—"
    if denominator is None or denominator <= 0:
        return _money(amount) + " (доля не определена: выручка ≤ 0)"
    share = amount / denominator * 100
    if share != 0 and abs(share) < 0.005:
        direction = "расход" if amount < 0 else "доход"
        return f"{_money(amount)} (<0,01% {direction} от общей выручки)"
    percent = f"{share:.2f}".replace(".", ",")
    return f"{_money(amount)} ({percent}% от общей выручки)"


def _fee_with_revenue_share(value, revenue):
    if value is None:
        return "не найдено начисление с однозначной подписью в Ozon"
    return _money_with_revenue_share(value, revenue)


def _units_with_order_share(value, ordered_units, ordered=False):
    if value is None:
        return None
    number = ExperimentalStoreEconomicsRuntimeService._number(value)
    if number is None:
        return None
    formatted = _format_units(number)
    if ordered:
        if number > 0:
            return f"{formatted} шт. (100% базы для долей)"
        return f"{formatted} шт."
    denominator = ExperimentalStoreEconomicsRuntimeService._number(ordered_units)
    if denominator is None or denominator <= 0:
        return f"{formatted} шт."
    share = number / denominator * 100
    percent = f"{share:.2f}".replace(".", ",")
    return f"{formatted} шт. ({percent}% от заказанных единиц)"


def _period_event_units(value, ordered_units, cohort_compatible, explanation):
    if value is None:
        return None
    if cohort_compatible:
        return _units_with_order_share(value, ordered_units)
    return (
        f"{_format_units(value)} шт. "
        f"(доля не показана: {explanation})"
    )


def _format_units(value):
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return f"{int(number):,}".replace(",", " ")
    formatted = f"{number:,.2f}".rstrip("0").rstrip(".")
    return formatted.replace(",", " ").replace(".", ",")


def _money_or_status(value, status):
    if value is not None:
        return _money(value)
    labels = {
        "NOT_CONFIGURED": "Performance не подключён",
        "INCOMPLETE": "данные CPC неполные",
    }
    return labels.get(status, "нет подтверждённых данных")


def _fee_or_unconfirmed(value):
    if value is None:
        return "не найдено начисление с однозначной подписью в Ozon"
    return _money(value)


def _unit_or_unconfirmed(value, status, diagnostic=None, label="показателя"):
    if value is not None:
        return _format_units(value) + " шт."
    if status == "UNAVAILABLE":
        if diagnostic == "ANALYTICS_ACCESS_DENIED":
            return f"нет доступа к показателю «{label}» в Ozon Analytics"
        if diagnostic == "ANALYTICS_RATE_LIMITED":
            return "Ozon Analytics ограничил запрос; повторите позже"
        if (
            isinstance(diagnostic, str)
            and re.fullmatch(r"[A-Z0-9_]{1,64}", diagnostic)
            and _is_missing_analytics_metric(diagnostic)
        ):
            return f"Ozon Analytics не вернул показатель «{label}»"
        return f"показатель «{label}» недоступен в Ozon Analytics"
    if status in {"INVALID", "INCOMPLETE"}:
        return (
            "данные неполные"
            if status == "INCOMPLETE"
            or diagnostic in {
                "ANALYTICS_PAGE_UNAVAILABLE",
                "ANALYTICS_PAGE_LIMIT_REACHED",
            }
            else f"данные по показателю «{label}» не прошли проверку"
        )
    return f"Ozon Analytics не предоставил показатель «{label}»"


def _analytics_metric_value(value, metric_name):
    if value is None:
        return None, metric_name.upper() + "_VALUE_MISSING"
    if isinstance(value, bool):
        return None, metric_name.upper() + "_VALUE_INVALID"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None, metric_name.upper() + "_VALUE_INVALID"
    if not number.is_finite():
        return None, metric_name.upper() + "_VALUE_INVALID"
    if number < 0:
        return None, metric_name.upper() + "_NEGATIVE_VALUE"
    return number, None


def _public_analytics_number(value):
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    output = float(value)
    return output if isfinite(output) else None


def _analytics_result(
    values,
    diagnostics,
    status,
):
    result = {"status": status}
    for metric_name, value in values.items():
        diagnostic = diagnostics.get(metric_name)
        result[metric_name] = value
        result[metric_name + "_status"] = _analytics_field_status(
            value, diagnostic, status
        )
        result[metric_name + "_diagnostic"] = diagnostic
    return result


def _analytics_field_status(value, diagnostic, overall_status):
    if value is not None:
        return "READY"
    if overall_status in {"UNAVAILABLE", "INCOMPLETE"}:
        return overall_status
    if _is_missing_analytics_metric(diagnostic):
        return "UNAVAILABLE"
    return "INVALID"


def _is_missing_analytics_metric(diagnostic):
    return isinstance(diagnostic, str) and diagnostic.endswith(
        ("_VALUE_MISSING", "_NOT_RETURNED")
    )


def _extract_postings_page(response):
    if not isinstance(response, dict) or response.get("error") is True:
        return [], False
    if response.get("complete") is True:
        postings = response.get("postings")
        return (postings, isinstance(postings, list))
    result = response.get("result")
    postings = result.get("postings") if isinstance(result, dict) else None
    if not isinstance(postings, list):
        return [], False
    return postings, response.get("has_next") is False

