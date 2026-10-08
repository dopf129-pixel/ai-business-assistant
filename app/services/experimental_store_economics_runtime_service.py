import re
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from threading import RLock

from period_profit_request import build_period_profit_request
from services.period_profit_cost_exclusion_context import (
    activate_cost_exclusion,
    reset_cost_exclusion,
)


class ExperimentalStoreEconomicsRuntimeService:
    """Read-only experimental store economics based on existing Ozon services."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}
    ANALYTICS_METRICS = ("ordered_units", "cancellations", "returns")
    ANALYTICS_DIMENSIONS = ("day",)
    ANALYTICS_PAGE_SIZE = 1000
    ACCRUAL_POSTING_BATCH_SIZE = 100
    ACCRUAL_POSTING_WORKERS = 4
    OPERATIONAL_POSTING_MAX_PAGES = 20
    OPERATIONAL_RETURN_MAX_PAGES = 20
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
        self._pending_custom_period_users = set()
        self._pending_lock = RLock()

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
        return self.calculate(request["date_from"], request["date_to"])

    def begin_custom_period(self, user_id):
        user_key = self._user_key(user_id)
        if not user_key:
            return self._error("EXPERIMENTAL_STORE_ECONOMICS_USER_REQUIRED")
        with self._pending_lock:
            self._pending_custom_period_users.add(user_key)
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
        with self._pending_lock:
            pending = user_key in self._pending_custom_period_users
        if not pending:
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
        parsed = []
        for token in match.groups():
            try:
                parsed.append(datetime.strptime(token, "%d.%m.%Y").date())
            except ValueError:
                return self._custom_period_retry()
        request = build_period_profit_request(
            date_from=parsed[0],
            date_to=parsed[1],
            today=today,
        )
        if request.get("error") is True:
            return self._custom_period_retry()

        self.clear_pending_custom_period_input(user_id)
        return self.calculate(request["date_from"], request["date_to"])

    def clear_pending_custom_period_input(self, user_id):
        user_key = self._user_key(user_id)
        if user_key:
            with self._pending_lock:
                self._pending_custom_period_users.discard(user_key)

    def calculate(self, date_from, date_to):
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
            and realization_commission.get("return_commission_row_count", 0) == 0
        ):
            realization_commission = self._failed_realization_commission(
                "OZON_FINANCE_REALIZATION_COMMISSION_MISSING",
                realization_commission,
            )
        metrics["realization_commission_diagnostics"] = realization_commission
        explicit_commission = realization_commission.get("commission")
        commission_source = "FINANCE_REALIZATION_POSTING"
        if explicit_commission is None:
            explicit_commission = accrual_posting_categories.get("commission")
            commission_source = "FINANCE_ACCRUAL_POSTINGS"
        if explicit_commission is None:
            explicit_commission = self._commission_from_explicit_types(summary)
            commission_source = "ACCRUAL_FEE_TYPES"
        if explicit_commission is None:
            commission_source = "POSTING_SALE_COMMISSION"
        elif commission_source != "FINANCE_REALIZATION_POSTING":
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

        return {
            "error": False,
            "status": "EXPERIMENTAL_STORE_ECONOMICS_READY",
            "date_from": date_from,
            "date_to": date_to,
            "metrics": metrics,
            "text": self._render(date_from, date_to, metrics),
            "cost_excluded": True,
            "profit_complete": False,
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
        try:
            response = getter(
                date_from,
                date_to,
                metrics=list(self.ANALYTICS_METRICS),
                dimension=list(self.ANALYTICS_DIMENSIONS),
                limit=self.ANALYTICS_PAGE_SIZE,
                offset=0,
            )
        except Exception:
            return self._empty_analytics_result(
                "UNAVAILABLE", "ANALYTICS_REQUEST_FAILED"
            )
        if not isinstance(response, dict) or response.get("error") is True:
            return self._empty_analytics_result(
                "UNAVAILABLE", "ANALYTICS_RESPONSE_UNAVAILABLE"
            )
        result = response.get("result")
        rows = result.get("data") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            return self._empty_analytics_result(
                "INVALID", "ANALYTICS_DATA_MISSING"
            )
        if len(rows) >= self.ANALYTICS_PAGE_SIZE:
            return self._empty_analytics_result(
                "INCOMPLETE", "ANALYTICS_PAGE_LIMIT_REACHED"
            )

        totals = result.get("totals") if isinstance(result, dict) else None
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

    def _fill_analytics_from_seller_api(self, analytics, date_from, date_to):
        """Use complete Seller API operational records when Analytics omits a metric.

        Cancellation counts are based on FBO/FBS postings created in the
        requested window that are currently cancelled. Return counts are based
        on FBO/FBS return records whose status changed in that window. These
        are explicitly named as fallbacks in the report because their date
        semantics differ from the Analytics metrics.
        """
        result = dict(analytics or {})
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

        postings = []
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
        postings.extend(fbo_postings)
        postings.extend(fbs_postings)

        total = 0
        for posting in postings:
            if not isinstance(posting, dict):
                return None
            if str(posting.get("status") or "").casefold() != "cancelled":
                continue
            products = posting.get("products")
            if not isinstance(products, list):
                return None
            for product in products:
                if not isinstance(product, dict):
                    return None
                quantity = self._integer(product.get("quantity"))
                if quantity is None:
                    return None
                total += quantity
        return total

    def _load_return_units(self, date_from, date_to):
        getter = getattr(self.analytics_client, "get_returns", None)
        if not callable(getter):
            return None

        total = 0
        for schema in ("FBO", "FBS"):
            last_id = 0
            seen_ids = set()
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
                    if str(row.get("type") or "").casefold() != "clientreturn":
                        continue
                    product = row.get("product")
                    if not isinstance(product, dict):
                        return None
                    quantity = self._integer(product.get("quantity"))
                    if quantity is None:
                        return None
                    total += quantity
                if response.get("has_next") is not True:
                    break
                if not rows:
                    return None
                try:
                    next_id = int(rows[-1].get("id"))
                except (AttributeError, TypeError, ValueError, OverflowError):
                    return None
                if next_id <= last_id or next_id in seen_ids:
                    return None
                seen_ids.add(next_id)
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
        getter = getattr(ozon_client, "get_realization_posting", None)
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
                # A report row may describe only a delivery or only a return.
                # Sum the commission object that Ozon supplied; fail closed if
                # neither component is present or a present amount is invalid.
                sale_amount = (
                    0.0
                    if delivery_missing
                    else self._number(delivery.get("commission"))
                )
                return_amount = (
                    0.0
                    if return_missing
                    else self._number(returned.get("commission"))
                )
                if sale_amount is None or return_amount is None:
                    return self._failed_realization_commission(
                        "OZON_FINANCE_REALIZATION_COMMISSION_INVALID",
                        result,
                    )
                sale_total += sale_amount
                return_total += return_amount
                if sale_amount:
                    result["sale_operation_count"] += 1
                if return_amount:
                    result["return_operation_count"] += 1

            result["month_count"] += 1
            current = (
                date(current.year + 1, 1, 1)
                if current.month == 12
                else date(current.year, current.month + 1, 1)
            )

        result["sale_commission_amount"] = round(sale_total, 2)
        result["return_commission_amount"] = round(return_total, 2)
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
            "sale_operation_count": 0,
            "sale_commission_amount": None,
            "return_operation_count": 0,
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
            result.append({"label": label[:72], "amount": round(amount, 2)})
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
        finance_advertising = metrics["finance_advertising"]
        revenue = metrics["revenue"]
        cpc_text = _money_or_status(
            advertising.get("cpc"),
            advertising.get("status"),
        )
        if advertising.get("cpc") is not None:
            cpc_text = _money_with_revenue_share(
                advertising["cpc"], revenue
            )
        campaign_count = advertising.get("campaign_count")
        ad_groups = finance_advertising["groups"]
        ad_lines = []
        if finance_advertising["has_explicit_types"]:
            for group_name in ("CPC", "CPO", "CPM", "OTHER"):
                group = ad_groups[group_name]
                if not group["count"]:
                    continue
                title = "другие явные рекламные услуги" if group_name == "OTHER" else group_name
                ad_lines.append(
                    f"   • По начислениям Ozon, {title}: "
                    f"{_money_with_revenue_share(group['amount'], revenue)}"
                )
        else:
            ad_lines.append(
                "   • Рекламные типы не распознаны в начислениях Ozon"
            )
        ad_lines.append(
            "   • Performance CPC по сопоставленным SKU (для сверки): "
            + cpc_text
        )
        if isinstance(campaign_count, int) and not isinstance(campaign_count, bool):
            ad_lines[-1] += f" ({campaign_count} камп.)"
        other_fee_details = ExperimentalStoreEconomicsRuntimeService._other_fee_details(
            metrics["fee_breakdown"]
        )
        ordered_units = analytics.get("ordered_units")
        ordered_text = _units_with_order_share(
            ordered_units,
            ordered_units,
            ordered=True,
        )
        cancellation_text = _units_with_order_share(
            analytics.get("cancellations"), ordered_units
        )
        returns_text = _units_with_order_share(
            analytics.get("returns"), ordered_units
        )
        cancellations_source = analytics.get("cancellations_source")
        returns_source = analytics.get("returns_source")
        cancellation_label = (
            "Отменённые единицы (FBO/FBS, заказы периода)"
            if cancellations_source == "SELLER_POSTINGS"
            else "Отменённые единицы (Analytics)"
        )
        returns_label = (
            "Возвраты (FBO/FBS, статус изменён в периоде)"
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
        lines = [
            f"🧪 Экономика магазина за период {date_from} — {date_to}",
            "",
            "1. Выручка общая (100%): " + _money(metrics["revenue"]),
            "2. Выручка ФНС (выручка − баллы): " + _money_with_revenue_share(metrics["revenue_tax_base"], revenue),
            "3. Баллы за скидки: " + _money_with_revenue_share(metrics["discount_points"], revenue),
            "4. Начисления Ozon нетто: " + _money_with_revenue_share(metrics["net_accrual"], revenue),
            "5. Налог: " + _money_with_revenue_share(metrics["tax"], revenue),
            "6. Прибыль без себестоимости: " + _money_with_revenue_share(metrics["profit"], revenue),
            "7. Расходы на рекламу:",
            *ad_lines,
            "8. Эквайринг: " + _money_with_revenue_share(metrics["acquiring"], revenue),
            (
                "9. Комиссия Ozon (предварительно; возвратная комиссия не подтверждена): "
                if metrics.get("commission_source") == "POSTING_SALE_COMMISSION"
                else (
                    "9. Комиссия Ozon (отчёт о реализации): "
                    if metrics.get("commission_source")
                    == "FINANCE_REALIZATION_POSTING"
                    else "9. Комиссия Ozon (вознаграждение за продажу): "
                )
            ) + _money_with_revenue_share(metrics["commission"], revenue),
            "10. Логистика доставки (без обратной логистики): " + _money_with_revenue_share(metrics["logistics"], revenue),
            "11. Доставка до места выдачи и выдача товара (части «последней мили»): " + _fee_with_revenue_share(fees.get("last_mile"), revenue),
            "12. Кросс-докинг: " + _fee_with_revenue_share(fees.get("cross_docking"), revenue),
            "13. Стоимость размещения на складе Ozon: " + _fee_with_revenue_share(fees.get("paid_storage"), revenue),
            "14. Остаток начислений Ozon после основных категорий: "
            + _money_with_revenue_share(metrics["other_fees"], revenue),
            "15. Заказанные единицы (Analytics): " + ordered_text,
            f"16. {cancellation_label}: {cancellation_text}",
            f"17. {returns_label}: {returns_text}",
            "",
            "⚠️ Экспериментальный результат, не заменяет основные расчёты.",
            "Денежные доли указаны от общей выручки. Для количества показана доля от заказанных единиц, поскольку штуки нельзя делить на рубли.",
            "Источники: суммы и удержания — финансовые начисления Ozon; комиссия за полные месяцы — отчёт реализации; размещение — типы начислений Seller API; заказанные единицы — Analytics; отмены и возвраты — Analytics либо подтверждённые записи Seller API; CPC по SKU — Ozon Performance.",
            "Прибыль рассчитана по нетто-начислениям Ozon за вычетом налога. Расходы, уже попавшие в начисления, учтены в прибыли. Performance CPC показан для сверки и может пересекаться с финансовыми начислениями; повторно его не вычитайте.",
            "Комиссия за полные календарные месяцы берётся из отчёта реализации (/v1/finance/realization/posting): отдельно суммируются комиссии за продажу и возврат. Для неполного месяца, если возвратная комиссия не подтверждена, сумма помечается как предварительная. Переразнесение между комиссией и строкой 14 не меняет начисления нетто.",
            "Строка 14 — расчётный остаток начислений нетто после выручки, эквайринга, комиссии и логистики доставки. В нём уже могут быть учтены реклама, кросс-докинг, обратная логистика, размещение и другие операции, показанные отдельно. Это не дополнительная сумма к вычитанию: не складывайте эти начисления повторно.",
            "Если плата за размещение не найдена в финансовых начислениях, проверьте Ozon Seller → Экономика магазина → Стоимость размещения на складе Ozon → Всего за период. В Seller API для этого есть отдельный отчёт по товарам; его данные пока не включаются в итог начислений.",
            "Отмены из Seller API — отправления, попавшие в фильтр дат API и имеющие статус «Отменено» на момент запроса. Возвраты из Seller API учитываются по смене статуса возврата в периоде.",
            "Разделение рекламы по типам возможно только по явным названиям начислений; отчёт по начислениям не содержит разбивки по кампаниям.",
            "Прибыль рассчитана существующим способом без себестоимости; это не итоговая прибыль магазина.",
        ]
        accrual_diagnostics = metrics.get("accrual_diagnostics") or {}
        posting_diagnostics = (
            metrics.get("accrual_posting_category_diagnostics") or {}
        )
        realization_diagnostics = (
            metrics.get("realization_commission_diagnostics") or {}
        )
        if (
            realization_diagnostics.get("available") is not True
            and realization_diagnostics.get("failure_code")
        ):
            failure_code = (
                ExperimentalStoreEconomicsRuntimeService
                ._safe_realization_commission_failure_code(
                    realization_diagnostics.get("failure_code")
                )
            )
            if failure_code == "OZON_FINANCE_REALIZATION_PERIOD_NOT_FULL_MONTHS":
                diagnostic = "период неполный; месячный отчёт не запрашивался"
            else:
                fallback = (
                    "использован предварительный источник по отправлениям"
                    if metrics.get("commission_source") == "POSTING_SALE_COMMISSION"
                    else "использован доступный источник начислений"
                )
                diagnostic = f"источник недоступен ({failure_code}); {fallback}"
            lines.extend(
                [
                    "",
                    "Диагностика комиссии (/v1/finance/realization/posting): "
                    f"{diagnostic}.",
                ]
            )
        if realization_diagnostics.get("available") is True:
            lines.extend(
                [
                    "",
                    "Диагностика комиссии (/v1/finance/realization/posting): "
                    f"полных месяцев {realization_diagnostics.get('month_count', 0)}, "
                    f"строк {realization_diagnostics.get('row_count', 0)} "
                    "(без комиссии продажи: "
                    f"{realization_diagnostics.get('delivery_commission_missing_row_count', 0)}, "
                    "без комиссии возврата: "
                    f"{realization_diagnostics.get('return_commission_missing_row_count', 0)}); "
                    "продажа — операций "
                    f"{realization_diagnostics.get('sale_operation_count', 0)}, "
                    f"{_money(realization_diagnostics.get('sale_commission_amount'))}; "
                    "возврат — операций "
                    f"{realization_diagnostics.get('return_operation_count', 0)}, "
                    f"{_money(realization_diagnostics.get('return_commission_amount'))}."
                ]
            )
        elif posting_diagnostics.get("available") is True:
            def diagnostic_subtotal(count, value):
                if count == 0:
                    return _money(0)
                return (
                    _money(value)
                    if value is not None
                    else "сумма не подтверждена"
                )

            commission_sale_count = posting_diagnostics.get(
                "commission_sale_operation_count", 0
            )
            commission_refund_count = posting_diagnostics.get(
                "commission_refund_operation_count", 0
            )
            commission_other_count = posting_diagnostics.get(
                "commission_other_operation_count", 0
            )
            unmapped_type_count = posting_diagnostics.get(
                "unmapped_type_count", 0
            )
            storage_service_count = posting_diagnostics.get(
                "storage_service_count", 0
            )
            lines.extend(
                [
                    "",
                    "Диагностика начислений (/v1/finance/accrual/postings): "
                    f"отправлений {posting_diagnostics.get('posting_count', 0)}, "
                    f"строк начислений {posting_diagnostics.get('operation_count', 0)}, "
                    "комиссия: продажа — операций "
                    f"{commission_sale_count}, "
                    f"{diagnostic_subtotal(commission_sale_count, posting_diagnostics.get('commission_sale_amount'))}; "
                    "возврат — операций "
                    f"{commission_refund_count}, "
                    f"{diagnostic_subtotal(commission_refund_count, posting_diagnostics.get('commission_refund_amount'))}; "
                    "прочие явные типы — операций "
                    f"{commission_other_count}, "
                    f"{diagnostic_subtotal(commission_other_count, posting_diagnostics.get('commission_other_amount'))}; "
                    "без типа в справочнике — операций "
                    f"{unmapped_type_count}, "
                    f"{diagnostic_subtotal(unmapped_type_count, posting_diagnostics.get('unmapped_type_amount'))}; "
                    "размещение — операций "
                    f"{storage_service_count}, "
                    f"{diagnostic_subtotal(storage_service_count, posting_diagnostics.get('paid_storage'))}."
                ]
            )
        elif (
            metrics.get("commission_source") != "FINANCE_ACCRUAL_POSTINGS"
            or fees.get("paid_storage") is None
        ):
            failure_code = (
                ExperimentalStoreEconomicsRuntimeService._safe_accrual_posting_failure_code(
                    posting_diagnostics.get("failure_code")
                )
            )
            posting_source = f"недоступен ({failure_code})"
            lines.extend(
                [
                    "",
                    "Диагностика разбивки (/v1/finance/accrual/by-day и "
                    "/v1/finance/accrual/postings): типов начислений "
                    f"{accrual_diagnostics.get('fee_type_count', 0)}, "
                    f"совпадений комиссии {accrual_diagnostics.get('commission_matches', 0)}, "
                    f"размещения {accrual_diagnostics.get('storage_matches', 0)}; "
                    f"источник начислений по отправлениям {posting_source}, "
                    f"отправлений {posting_diagnostics.get('posting_count', 0)}, "
                    f"строк начислений {posting_diagnostics.get('operation_count', 0)}, "
                    f"строк комиссии {posting_diagnostics.get('commission_operation_count', 0)}, "
                    f"строк размещения {posting_diagnostics.get('storage_service_count', 0)}."
                ]
            )
        if other_fee_details:
            lines.extend(
                [
                    "",
                    "Детализация типов начислений, вошедших в строку 14 (группы типов Ozon могут объединять несколько операций из XLSX):",
                ]
            )
            for item in other_fee_details[:5]:
                lines.append(
                    f"   • Тип Ozon «{item['label']}»: "
                    f"{_money_with_revenue_share(item['amount'], revenue)}"
                )
            if len(other_fee_details) > 5:
                lines.append(
                    f"   • Ещё типов начислений: {len(other_fee_details) - 5}"
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
        return _money(amount)
    share = amount / denominator * 100
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

