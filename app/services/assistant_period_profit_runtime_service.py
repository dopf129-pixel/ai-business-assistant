import re
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from threading import RLock
from time import monotonic
from uuid import uuid4

from period_profit_compact_response import compact_period_profit_result
from period_profit_completeness_view import PeriodProfitCompletenessViewService
from services.period_profit_cost_confirmation_runtime_service import (
    PeriodProfitCostConfirmationRuntimeService,
)
from services.period_profit_effective_cost_service import PeriodProfitEffectiveCostService
from services.period_profit_identity_confirmation_runtime_service import (
    PeriodProfitIdentityConfirmationRuntimeService,
)
from period_profit_request import build_period_profit_request
from services.period_profit_cost_exclusion_context import (
    activate_cost_exclusion,
    reset_cost_exclusion,
)
from services.tenant_context import get_current_tenant_user_id


class AssistantPeriodProfitRuntimeService:
    """Narrow Period Profit route plus seller-confirmed local corrections."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}
    REPORT_VIEW_CACHE_MAX = 64
    REPORT_VIEW_TTL_SECONDS = 600
    ANALYTICS_IDENTIFIER_MAX_CHARS = 80

    def __init__(
        self,
        query_service,
        cost_confirmation_runtime_service=None,
        identity_confirmation_runtime_service=None,
        sku_runtime_service=None,
        keyboard_service=None,
        clock=None,
    ):
        self.query_service = query_service
        self.cost_confirmation_runtime_service = cost_confirmation_runtime_service
        self.identity_confirmation_runtime_service = identity_confirmation_runtime_service
        self.sku_runtime_service = sku_runtime_service
        self.keyboard_service = keyboard_service
        self.clock = clock or monotonic
        self.completeness_view_service = PeriodProfitCompletenessViewService()
        self._custom_period_users = {}
        self._custom_pre_cogs_users = {}
        self._custom_sku_period_users = {}
        self._custom_period_lock = RLock()
        self._custom_period_inflight = set()
        self._report_views = OrderedDict()

    def begin_custom_sku_period(self, user_id, sku):
        user_key = self._user_key(user_id)
        sku_key = str(sku or "").strip()
        if not user_key or not sku_key or self.sku_runtime_service is None:
            return self._custom_period_input_invalid()
        with self._custom_period_lock:
            self._clear_pending_custom_period_input_locked(user_key)
            self._custom_sku_period_users[user_key] = {
                "sku": sku_key,
                "tenant_scope": self._tenant_scope(),
            }
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SKU_CUSTOM_PERIOD_INPUT_REQUIRED",
            "message": "Введите период для SKU " + sku_key + " в формате 01.01.2026-02.02.2026",
            "read_only": True,
            "executed": False,
        }

    def begin_custom_period(self, user_id):
        user_key = self._user_key(user_id)
        if not user_key:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_CUSTOM_PERIOD_USER_REQUIRED",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        with self._custom_period_lock:
            self._clear_pending_custom_period_input_locked(user_key)
            self._custom_period_users[user_key] = self._tenant_scope()
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_REQUIRED",
            "message": "Введите период в формате 01.01.2026-02.02.2026",
            "read_only": True,
            "executed": False,
        }

    def begin_custom_pre_cogs_period(self, user_id):
        user_key = self._user_key(user_id)
        if not user_key:
            return self._custom_period_input_invalid()
        with self._custom_period_lock:
            self._clear_pending_custom_period_input_locked(user_key)
            self._custom_pre_cogs_users[user_key] = self._tenant_scope()
        return {
            "error": False,
            "status": "PERIOD_PROFIT_PRE_COGS_CUSTOM_PERIOD_INPUT_REQUIRED",
            "message": "Введите период в формате 01.01.2026-02.02.2026",
            "read_only": True,
            "executed": False,
        }

    def handle_text(self, text, today=None, user_id=None):
        value = " ".join(str(text or "").strip().lower().split())

        user_key = self._user_key(user_id)
        with self._custom_period_lock:
            tenant_scope = self._tenant_scope()
            sku_pending = self._custom_sku_period_users.get(user_key)
            pre_cogs_scope = self._custom_pre_cogs_users.get(user_key)
            custom_period_scope = self._custom_period_users.get(user_key)
            pending_scope = (
                sku_pending.get("tenant_scope")
                if isinstance(sku_pending, dict)
                else pre_cogs_scope
                if pre_cogs_scope is not None
                else custom_period_scope
            )
            if pending_scope is not None and pending_scope != tenant_scope:
                self._clear_pending_custom_period_input_locked(user_key)
                return self._custom_period_store_stale()
            custom_sku = (
                sku_pending.get("sku")
                if isinstance(sku_pending, dict)
                else None
            )
            custom_pre_cogs = pre_cogs_scope is not None
            custom_period_pending = custom_period_scope is not None
        if (
            not custom_sku
            and not custom_pre_cogs
            and not custom_period_pending
            and re.fullmatch(
                r"\d{1,2}\.\d{1,2}\.\d{4}\s*-\s*"
                r"\d{1,2}\.\d{1,2}\.\d{4}", value
            )
        ):
            dates = self._extract_custom_dates(value)
            if dates and len(dates) == 2 and self._has_custom_period_inflight(
                user_key, dates
            ):
                return self._custom_period_in_progress()
        if custom_sku:
            if value in {"отмена", "cancel", "/cancel"}:
                with self._custom_period_lock:
                    self._custom_sku_period_users.pop(user_key, None)
                return {
                    "error": False,
                    "status": "PERIOD_PROFIT_SKU_CUSTOM_PERIOD_CANCELLED",
                    "message": "Ввод периода отменён.",
                    "read_only": True,
                    "executed": False,
                }
            if not re.fullmatch(
                r"\d{1,2}\.\d{1,2}\.\d{4}\s*-\s*"
                r"\d{1,2}\.\d{1,2}\.\d{4}", value
            ):
                return self._custom_period_input_invalid()
            dates = self._extract_custom_dates(value)
            if dates is None or len(dates) != 2:
                return self._custom_period_input_invalid()
            return self._run_custom_period_once(
                user_key,
                "sku:" + custom_sku,
                dates,
                lambda: self.sku_runtime_service.handle_custom_period(
                    custom_sku, dates[0], dates[1]
                ),
                consume_pending=lambda: self._consume_custom_sku_period(
                    user_key, custom_sku, tenant_scope
                ),
            )
        if custom_pre_cogs:
            if value in {"отмена", "cancel", "/cancel"}:
                with self._custom_period_lock:
                    self._custom_pre_cogs_users.pop(user_key, None)
                return {
                    "error": False,
                    "status": "PERIOD_PROFIT_PRE_COGS_CUSTOM_PERIOD_CANCELLED",
                    "message": "Ввод периода отменён.",
                    "read_only": True,
                    "executed": False,
                }
            if not re.fullmatch(
                r"\d{1,2}\.\d{1,2}\.\d{4}\s*-\s*"
                r"\d{1,2}\.\d{1,2}\.\d{4}", value
            ):
                return self._custom_period_input_invalid()
            dates = self._extract_custom_dates(value)
            if dates is None or len(dates) != 2:
                return self._custom_period_input_invalid()
            return self._run_custom_period_once(
                user_key,
                "pre_cogs",
                dates,
                lambda: self._query_pre_cogs(
                    date_from=dates[0], date_to=dates[1]
                ),
                consume_pending=lambda: self._consume_pending_user(
                    self._custom_pre_cogs_users, user_key, tenant_scope
                ),
            )
        if custom_period_pending:
            if value in {"отмена", "cancel", "/cancel"}:
                with self._custom_period_lock:
                    self._custom_period_users.pop(user_key, None)
                return {
                    "error": False,
                    "status": "PERIOD_PROFIT_CUSTOM_PERIOD_CANCELLED",
                    "message": "Ввод периода отменён.",
                    "read_only": True,
                    "executed": False,
                }
            if not re.fullmatch(
                r"\d{1,2}\.\d{1,2}\.\d{4}\s*-\s*"
                r"\d{1,2}\.\d{1,2}\.\d{4}",
                value,
            ):
                return self._custom_period_input_invalid()
            dates = self._extract_custom_dates(value)
            if dates is None or len(dates) != 2:
                return self._custom_period_input_invalid()
            return self._run_custom_period_once(
                user_key,
                "period_profit_custom",
                dates,
                lambda: self._present_report(
                    self._query_with_optional_comparison(
                        date_from=dates[0], date_to=dates[1], today=today
                    ),
                    user_id=user_id,
                ),
                consume_pending=lambda: self._consume_pending_user(
                    self._custom_period_users, user_key, tenant_scope
                ),
            )

        if self._looks_like_identity_statement(value):
            runtime = self.identity_confirmation_runtime_service
            if runtime is None:
                cost_service = PeriodProfitEffectiveCostService()
                runtime = PeriodProfitIdentityConfirmationRuntimeService(cost_service)
            confirmation = runtime.handle_text(text)
            if confirmation is not None:
                return confirmation

        if "себесто" in value or "cost" in value:
            runtime = self.cost_confirmation_runtime_service
            if runtime is None:
                runtime = PeriodProfitCostConfirmationRuntimeService(
                    PeriodProfitEffectiveCostService()
                )
            confirmation = runtime.handle_text(text)
            if confirmation is not None:
                return confirmation

        if not self._is_profit_request(value):
            return None

        dates = self._extract_custom_dates(value)
        if dates is not None:
            if len(dates) != 2:
                return self._invalid_custom_period()

            return self._run_custom_period_once(
                user_key,
                "period_profit_text",
                dates,
                lambda: self._present_report(
                    self._query_with_optional_comparison(
                        date_from=dates[0],
                        date_to=dates[1],
                        today=today,
                    ),
                    user_id=user_id,
                ),
            )

        period = self._resolve_period(value)
        if period is None:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_PERIOD_REQUIRED",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "message": (
                    "Укажите период: сегодня, 7, 28, 56, 90 дней "
                    "или две даты ДД.ММ.ГГГГ (например, "
                    "01.05.2026 - 03.09.2026)."
                ),
                "read_only": True,
                "executed": False,
            }

        return self._run_custom_period_once(
            user_key,
            "period_profit_text",
            (period,),
            lambda: self._present_report(
                self._query_with_optional_comparison(
                    period_code=period,
                    today=today,
                ),
                user_id=user_id,
            ),
        )

    def handle_callback(self, callback_data, today=None, user_id=None):
        value = str(callback_data or "").strip().upper()
        pre_cogs_prefix = "PERIOD_PROFIT_PRE_COGS:"
        if value.startswith(pre_cogs_prefix):
            period = value[len(pre_cogs_prefix):]
            if period not in self.PERIOD_CODES:
                return self._custom_period_input_invalid()
            return self._query_pre_cogs(period_code=period, today=today)
        prefix = "PERIOD_PROFIT:"
        if not value.startswith(prefix):
            return None
        period = value[len(prefix):]
        if period not in self.PERIOD_CODES:
            return {
                "error": True,
                "code": "PERIOD_PROFIT_CALLBACK_INVALID",
                "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
                "read_only": True,
                "executed": False,
            }
        return self._present_report(
            self._query_with_optional_comparison(
                period_code=period,
                today=today,
            ),
            user_id=user_id,
        )

    def handle_cached_view(self, callback_data, user_id=None):
        value = str(callback_data or "").strip()
        view_prefixes = {
            "period_profit_completeness": "completeness",
            "period_profit_report": "report",
            "period_profit_analytics": "analytics",
            "period_profit_comparison": "comparison",
            "period_profit_bridge": "bridge",
            "period_profit_sku_contribution": "sku_contribution",
        }
        parts = value.split(":")
        if len(parts) != 2 or parts[0] not in view_prefixes:
            return self._cached_view_expired()
        view_id = parts[1].lower()
        if not re.fullmatch(r"[0-9a-f]{12}", view_id):
            return self._cached_view_expired()
        key = self._report_view_key(user_id, view_id)
        if key is None:
            return self._cached_view_expired()
        now = self._monotonic_now()
        if now is None:
            return self._cached_view_expired()
        with self._custom_period_lock:
            cached = self._report_views.get(key)
            if not isinstance(cached, dict):
                return self._cached_view_expired()
            expires_at = cached.get("expires_at")
            if (
                isinstance(expires_at, bool)
                or not isinstance(expires_at, (int, float))
                or now >= expires_at
            ):
                self._report_views.pop(key, None)
                return self._cached_view_expired()
            self._report_views.move_to_end(key)
            cached = deepcopy(cached)
        view_type = view_prefixes[parts[0]]
        if view_type == "report":
            keyboard = self._build_report_keyboard(view_id)
            return {
                "error": False,
                "status": "PERIOD_PROFIT_CACHED_REPORT_READY",
                "text": cached["report_text"],
                "keyboard": keyboard,
                "report_view_id": view_id,
                "read_only": True,
                "executed": False,
            }
        if view_type == "completeness":
            keyboard = self._build_completeness_keyboard(
                view_id, cached.get("actions") or []
            )
            return {
                "error": False,
                "status": "PERIOD_PROFIT_COMPLETENESS_READY",
                "text": cached["completeness_text"],
                "keyboard": keyboard,
                "report_view_id": view_id,
                "read_only": True,
                "executed": False,
            }

        snapshot = cached.get("analytics_snapshot")
        if not isinstance(snapshot, dict):
            return self._cached_view_expired()
        if view_type == "analytics":
            status = "PERIOD_PROFIT_ANALYTICS_READY"
            text = self._analytics_menu_text(snapshot)
            keyboard = self._build_analytics_keyboard(view_id)
        else:
            status, text = self._analytics_detail_text(snapshot, view_type)
            keyboard = self._build_analytics_detail_keyboard(view_id, view_type)
        return {
            "error": False,
            "status": status,
            "text": text,
            "keyboard": keyboard,
            "report_view_id": view_id,
            "read_only": True,
            "executed": False,
        }

    def _query_pre_cogs(self, period_code=None, date_from=None, date_to=None, today=None):
        request = build_period_profit_request(
            period_code=period_code,
            date_from=date_from,
            date_to=date_to,
            today=today,
        )
        if request.get("error") is True:
            return request
        provider = getattr(self.query_service, "product_provider", None)
        summary_service = getattr(self.query_service, "summary_service", None)
        if not callable(provider) or summary_service is None:
            base = getattr(self.query_service, "base_service", None)
            provider = getattr(base, "product_provider", None)
            summary_service = getattr(base, "summary_service", None)
        if not callable(provider) or summary_service is None:
            return self._error("PERIOD_PROFIT_PRE_COGS_DEPENDENCY_UNAVAILABLE")
        products = provider()
        if not isinstance(products, list):
            return self._error("PERIOD_PROFIT_PRODUCTS_UNAVAILABLE")
        token = activate_cost_exclusion()
        try:
            summary = summary_service.calculate(
                request["date_from"], request["date_to"], products
            )
        finally:
            reset_cost_exclusion(token)
        if not isinstance(summary, dict) or summary.get("error") is True:
            return summary if isinstance(summary, dict) else self._error(
                "PERIOD_PROFIT_PRE_COGS_SUMMARY_INVALID"
            )
        before_cogs = summary.get("profit")
        margin = summary.get("margin_percent")
        return {
            "error": False,
            "status": "PERIOD_PROFIT_PRE_COGS_READY",
            "summary": summary,
            "text": (
                "🧮 Результат без учёта себестоимости за период "
                + request["date_from"] + " — " + request["date_to"]
                + "\n\nВыручка: " + self._money(summary.get("revenue"))
                + "\nНачисления Ozon: " + self._money(summary.get("net_accrual"))
                + "\nНалог: " + self._money(summary.get("tax"))
                + "\n\nРезультат до себестоимости: " + self._money(before_cogs)
                + "\nМаржа до себестоимости: " + self._percent(margin)
                + "\n\n⚠️ Себестоимость и Return COGS не вычитались. "
                "Это не итоговая прибыль магазина."
            ),
            "cost_excluded": True,
            "profit_complete": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _money(value):
        try:
            return f"{float(value):,.2f} ₽".replace(",", " ")
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _percent(value):
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE", "read_only": True, "executed": False}

    def _query_with_optional_comparison(self, **kwargs):
        result = self.query_service.query(
            compare_previous=True,
            **kwargs,
        )
        if not isinstance(result, dict):
            return self._error("PERIOD_PROFIT_QUERY_RESULT_INVALID")
        return result

    @staticmethod
    def _custom_period_input_invalid():
        return {
            "error": True,
            "code": "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_INVALID",
            "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
            "message": "Введите две корректные даты: 01.01.2026-02.02.2026",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _user_key(user_id):
        value = str(user_id or "").strip()
        return value or None

    @staticmethod
    def _tenant_scope():
        return str(get_current_tenant_user_id() or "")

    def _run_custom_period_once(
        self, user_key, mode, period_key, callback, consume_pending=None
    ):
        if not user_key:
            return callback()
        tenant_scope = str(get_current_tenant_user_id() or "")
        key = (tenant_scope, user_key, str(mode), tuple(period_key))
        with self._custom_period_lock:
            if key in self._custom_period_inflight:
                return self._custom_period_in_progress()
            if callable(consume_pending) and not consume_pending():
                return self._custom_period_input_stale()
            self._custom_period_inflight.add(key)
        try:
            return callback()
        finally:
            with self._custom_period_lock:
                self._custom_period_inflight.discard(key)

    def _has_custom_period_inflight(self, user_key, period_key):
        tenant_scope = str(get_current_tenant_user_id() or "")
        normalized_period = tuple(period_key)
        with self._custom_period_lock:
            return any(
                key[0] == tenant_scope
                and key[1] == user_key
                and key[3] == normalized_period
                for key in self._custom_period_inflight
            )

    def _consume_custom_sku_period(self, user_key, sku, tenant_scope):
        pending = self._custom_sku_period_users.get(user_key)
        if (
            not isinstance(pending, dict)
            or pending.get("sku") != sku
            or pending.get("tenant_scope") != tenant_scope
        ):
            return False
        self._custom_sku_period_users.pop(user_key, None)
        return True

    def _consume_pending_user(self, pending_users, user_key, tenant_scope):
        if pending_users.get(user_key) != tenant_scope:
            return False
        pending_users.pop(user_key, None)
        return True

    @staticmethod
    def _custom_period_in_progress():
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CUSTOM_PERIOD_ALREADY_RUNNING",
            "message": "Этот расчёт уже выполняется. Дождитесь ответа на первый запрос.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _custom_period_input_stale():
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_ALREADY_USED",
            "message": "Этот ввод периода уже обработан. Выберите период заново, если нужен повторный расчёт.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _custom_period_store_stale():
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CUSTOM_PERIOD_STORE_CHANGED",
            "message": "Вы переключили магазин. Старый ввод периода отменён; выберите период заново в текущем магазине.",
            "read_only": True,
            "executed": False,
        }

    def clear_pending_custom_period_input(self, user_id):
        """Clear a seller's pending custom-period prompt when they navigate away."""
        user_key = self._user_key(user_id)
        if not user_key:
            return
        with self._custom_period_lock:
            self._clear_pending_custom_period_input_locked(user_key)

    def _clear_pending_custom_period_input_locked(self, user_key):
        self._custom_period_users.pop(user_key, None)
        self._custom_pre_cogs_users.pop(user_key, None)
        self._custom_sku_period_users.pop(user_key, None)

    @staticmethod
    def _present(result):
        if isinstance(result, dict) and result.get("error") is True:
            code = str(result.get("code") or "").strip()
            if code in {
                "OZON_OPERATION_TIME_BUDGET_EXHAUSTED",
                "OZON_OPERATION_API_CALL_BUDGET_EXHAUSTED",
            }:
                output = dict(result)
                output["message"] = (
                    "Расчёт остановлен по внутреннему лимиту времени или "
                    "запросов к Ozon. Уменьшите период и повторите запрос."
                )
                output["read_only"] = True
                output["executed"] = False
                return output
            if (
                code == "FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE"
                or code.startswith("OZON_FINANCE_")
                or code.startswith("PERIOD_PROFIT_FINANCE_")
            ):
                output = dict(result)
                diagnostic = str(
                    result.get("finance_diagnostic_code") or code
                ).strip().upper()
                if not diagnostic or not all(
                    character.isalnum() or character == "_"
                    for character in diagnostic
                ):
                    diagnostic = code
                output["finance_diagnostic_code"] = diagnostic
                if diagnostic.startswith("PERIOD_PROFIT_FINANCE_SKU_IDENTITY_"):
                    skus = [
                        str(sku).strip()
                        for sku in result.get("unresolved_finance_skus") or []
                        if str(sku).strip()
                    ][:10]
                    message = (
                        "Не удалось определить, к какому товару из каталога "
                        "относятся операции Ozon. Прибыль за период остановлена, "
                        "чтобы не смешать данные разных товаров."
                    )
                    if skus:
                        message += "\nSKU из операций Ozon: " + ", ".join(skus)
                    message += (
                        "\nЕсли это тот же товар и вариант, укажите SKU из "
                        "операций и SKU из карточки товара."
                    )
                    if skus:
                        message += (
                            "\nОтправьте боту одной строкой:\n"
                            "SKU " + skus[0]
                            + " и SKU [номер из карточки товара] — один товар"
                            "\nЗамените слова в квадратных скобках на номер SKU "
                            "из карточки товара; сами скобки не отправляйте."
                        )
                    message += (
                        "\nЧтобы проверить связь со старым SKU, нажмите "
                        "«Выбрать товар для проверки», затем выберите карточку "
                        "товара и период. Если данных Ozon хватит, бот покажет "
                        "старый SKU для подтверждения. Связь сохранится только "
                        "после вашего отдельного подтверждения."
                    )
                    message += (
                        "\nКод диагностики: " + diagnostic
                    )
                    output["message"] = message
                    output["keyboard"] = {
                        "error": False,
                        "type": "inline_keyboard",
                        "buttons": [{
                            "text": "🔎 Выбрать товар для проверки",
                            "callback": "period_profit_sku",
                        }],
                    }
                else:
                    output["message"] = (
                        "Финансовые данные Ozon недоступны\n"
                        "Код диагностики: " + diagnostic
                    )
                output["read_only"] = True
                output["executed"] = False
                return output

        if (
            isinstance(result, dict)
            and result.get("error") is True
            and result.get("status") == "PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE"
        ):
            code = str(result.get("code") or "").strip()
            if code:
                output = dict(result)
                output["quantity_diagnostic_code"] = code
                message = (
                    "Данные о количестве проданных товаров недоступны\n"
                    "Код диагностики: " + code
                )
                trace = result.get("cost_diagnostic_trace")
                trace_text = AssistantPeriodProfitRuntimeService._safe_trace_text(trace)
                if trace_text:
                    output["cost_diagnostic_trace_text"] = trace_text
                    message += "\nТрассировка: " + trace_text
                output["message"] = message
                output["read_only"] = True
                output["executed"] = False
                return output
        return compact_period_profit_result(result)

    def _present_report(self, result, user_id=None):
        output = self._present(result)
        if (
            isinstance(output, dict)
            and output.get("error") is False
            and output.get("status") == "PERIOD_PROFIT_QUERY_READY"
            and isinstance(output.get("text"), str)
        ):
            self._save_completeness_view(output, result, user_id)
        return output

    def _save_completeness_view(self, compact_result, source_result, user_id):
        scope = self._report_view_scope(user_id)
        if scope is None:
            return None
        view = self.completeness_view_service.build(source_result)
        if not isinstance(view, dict) or view.get("error") is not False:
            return None
        if view.get("status") != "PERIOD_PROFIT_COMPLETENESS_READY":
            return None
        created_at = self._monotonic_now()
        if created_at is None:
            return None
        view_id = uuid4().hex[:12]
        key = (*scope, view_id)
        snapshot = self._build_analytics_snapshot(source_result, scope)
        with self._custom_period_lock:
            self._expire_report_views_locked(created_at)
            self._report_views[key] = {
                "report_text": str(compact_result["text"]),
                "completeness_text": str(view["message"]),
                "actions": list(view.get("actions") or []),
                "analytics_snapshot": snapshot,
                "created_at": created_at,
                "expires_at": created_at + self.REPORT_VIEW_TTL_SECONDS,
            }
            self._report_views.move_to_end(key)
            while len(self._report_views) > self.REPORT_VIEW_CACHE_MAX:
                self._report_views.popitem(last=False)
        compact_result["report_view_id"] = view_id
        compact_result["keyboard"] = self._build_report_keyboard(view_id)
        return view_id

    def _report_view_scope(self, user_id):
        user_key = self._user_key(user_id)
        tenant_scope = self._user_key(get_current_tenant_user_id())
        if user_key is None or tenant_scope is None:
            return None
        return tenant_scope, user_key

    def _report_view_key(self, user_id, view_id):
        scope = self._report_view_scope(user_id)
        if scope is None:
            return None
        return (*scope, view_id)

    def _build_report_keyboard(self, view_id):
        builder = getattr(self.keyboard_service, "build_period_profit_result_keyboard", None)
        if callable(builder):
            return builder(view_id)
        return {"error": False, "type": "inline_keyboard", "buttons": [{
            "text": "📊 Аналитика периода",
            "callback": "period_profit_analytics:" + view_id,
        }, {
            "text": "🔎 Полнота данных",
            "callback": "period_profit_completeness:" + view_id,
        }]}

    def _build_analytics_keyboard(self, view_id):
        builder = getattr(self.keyboard_service, "build_period_profit_analytics_keyboard", None)
        if callable(builder):
            return builder(view_id)
        return {"error": False, "type": "inline_keyboard", "buttons": [
            {"text": "Сравнение периодов", "callback": "period_profit_comparison:" + view_id},
            {"text": "Что изменило прибыль", "callback": "period_profit_bridge:" + view_id},
            {"text": "Вклад SKU", "callback": "period_profit_sku_contribution:" + view_id},
            {"text": "Полнота данных", "callback": "period_profit_completeness:" + view_id},
            {"text": "К расчёту", "callback": "period_profit_report:" + view_id},
        ]}

    def _build_analytics_detail_keyboard(self, view_id, view_type=None):
        if view_type == "sku_contribution":
            sku_builder = getattr(
                self.keyboard_service,
                "build_period_profit_sku_contribution_keyboard",
                None,
            )
            if callable(sku_builder):
                return sku_builder(view_id)
        builder = getattr(
            self.keyboard_service,
            "build_period_profit_analytics_detail_keyboard",
            None,
        )
        if callable(builder):
            return builder(view_id)
        return {"error": False, "type": "inline_keyboard", "buttons": [
            {"text": "↩️ Аналитика", "callback": "period_profit_analytics:" + view_id},
            {"text": "↩️ К расчёту", "callback": "period_profit_report:" + view_id},
        ]}

    def _build_analytics_snapshot(self, result, scope):
        source = result if isinstance(result, dict) else {}
        contract = source.get("comparison_contract")
        current = contract.get("current") if isinstance(contract, dict) else None
        previous = contract.get("previous") if isinstance(contract, dict) else None
        current_period = current.get("period") if isinstance(current, dict) else None
        previous_period = previous.get("period") if isinstance(previous, dict) else None
        summary = source.get("summary")
        if not isinstance(current_period, dict) and isinstance(summary, dict):
            current_period = {
                "date_from": summary.get("date_from"),
                "date_to": summary.get("date_to"),
            }
        bases = contract.get("profit_bases") if isinstance(contract, dict) else None
        basis_b = bases.get("B") if isinstance(bases, dict) else None
        comparison_ready = (
            isinstance(basis_b, dict) and basis_b.get("status") == "CONFIRMED"
        )
        generated_at = (
            contract.get("generated_at")
            if isinstance(contract, dict)
            else None
        )
        if not isinstance(generated_at, str) or not generated_at.strip():
            generated_at = datetime.now(timezone.utc).isoformat()
        comparison_metrics = source.get("comparison_metrics")
        metrics = (
            comparison_metrics.get("metrics")
            if isinstance(comparison_metrics, dict)
            else None
        )
        metric_projection = {}
        if isinstance(metrics, dict):
            for name in (
                "revenue",
                "discount_points",
                "net_accrual",
                "product_cost",
                "tax",
                "profit",
                "margin_percent",
                "external_expenses",
                "profit_after_external_expenses",
                "units_sold",
            ):
                row = metrics.get(name)
                if not isinstance(row, dict):
                    continue
                metric_projection[name] = {
                    key: row.get(key)
                    for key in (
                        "unit",
                        "current_value",
                        "current_status",
                        "previous_value",
                        "previous_status",
                        "comparison_status",
                        "delta",
                        "delta_unit",
                    )
                }
        bridge = self._bridge_snapshot_projection(source.get("profit_bridge"))
        sku_contribution = self._sku_snapshot_projection(
            source.get("sku_contribution")
        )
        return {
            "schema_version": 1,
            "scope": {
                "tenant_scope": scope[0],
                "owner_scope": scope[1],
                "currency": "RUB",
            },
            "generated_at": generated_at,
            "periods": {
                "current": self._period_projection(current_period),
                "previous": self._period_projection(previous_period),
            },
            "comparison_basis": "B",
            "comparison_status": "CONFIRMED" if comparison_ready else "UNAVAILABLE",
            "comparison_reason_code": self._safe_code(
                source.get("comparison_error_code")
                or self._first_reason(contract)
            ),
            "comparison_metrics": metric_projection,
            "profit_bridge": bridge,
            "sku_contribution": sku_contribution,
            "coverage_status": self._safe_code(
                (source.get("coverage") or {}).get("coverage_status")
                if isinstance(source.get("coverage"), dict)
                else None
            ),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _bridge_snapshot_projection(value):
        if not isinstance(value, dict):
            return None

        def project_basis(basis, contribution_keys, detail_keys=()):
            if not isinstance(basis, dict):
                return None
            output = {
                "status": AssistantPeriodProfitRuntimeService._safe_code(
                    basis.get("status")
                ),
                "authoritative_delta": basis.get("authoritative_delta"),
            }
            contributions = basis.get("contributions")
            if isinstance(contributions, dict):
                output["contributions"] = {
                    key: contributions.get(key)
                    for key in contribution_keys
                    if key in contributions
                }
            detail = basis.get("net_accrual_detail")
            if isinstance(detail, dict):
                output["net_accrual_detail"] = {
                    key: detail.get(key)
                    for key in ("status", *detail_keys)
                    if key in detail
                }
            return output

        return {
            "status": AssistantPeriodProfitRuntimeService._safe_code(
                value.get("status")
            ),
            "B": project_basis(
                value.get("B"),
                (
                    "net_accrual_change",
                    "product_cost_contribution",
                    "return_cogs_contribution",
                    "tax_contribution",
                    "rounding_adjustment",
                ),
                ("revenue_change", "other_net_accrual_change"),
            ),
            "E": project_basis(
                value.get("E"),
                (
                    "profit_before_external_expenses_delta",
                    "external_expenses_contribution",
                    "rounding_adjustment",
                ),
            ),
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _sku_snapshot_projection(cls, value):
        if not isinstance(value, dict):
            return None

        def project_rows(rows):
            if not isinstance(rows, list):
                return []
            output = []
            for row in rows[:5]:
                if not isinstance(row, dict):
                    continue
                sku = cls._safe_analytics_identifier(
                    row.get("sku") or row.get("offer_id")
                )
                output.append({
                    "sku": sku,
                    "delta": row.get("delta"),
                    "status": cls._safe_code(row.get("status")),
                })
            return output

        fields = (
            "store_profit_delta",
            "matched_sku_profit_delta",
            "store_minus_sku_delta",
            "matched_sku_count",
            "unmatched_current_count",
            "unmatched_previous_count",
            "ambiguous_identity_count",
            "invalid_row_count",
        )
        projected = {key: value.get(key) for key in fields if key in value}
        projected.update({
            "status": cls._safe_code(value.get("status")),
            "coverage_status": cls._safe_code(value.get("coverage_status")),
            "basis": cls._safe_code(value.get("basis")),
            "reconciliation_status": cls._safe_code(
                value.get("reconciliation_status")
            ),
            "unmatched_rows_are_zero": value.get("unmatched_rows_are_zero") is True,
            "top_growth": project_rows(value.get("top_growth")),
            "top_decline": project_rows(value.get("top_decline")),
            "read_only": True,
            "executed": False,
        })
        return projected

    @classmethod
    def _safe_analytics_identifier(cls, value):
        if not isinstance(value, str):
            return "SKU неизвестен"
        normalized = " ".join(
            "".join(character if character.isprintable() else " " for character in value).split()
        )
        if not normalized:
            return "SKU неизвестен"
        if len(normalized) > cls.ANALYTICS_IDENTIFIER_MAX_CHARS:
            return normalized[: cls.ANALYTICS_IDENTIFIER_MAX_CHARS - 1] + "…"
        return normalized

    @staticmethod
    def _period_projection(period):
        if not isinstance(period, dict):
            return None
        start = period.get("date_from")
        end = period.get("date_to")
        if not isinstance(start, str) or not isinstance(end, str):
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", end
        ):
            return None
        return {"date_from": start, "date_to": end}

    @staticmethod
    def _first_reason(contract):
        if not isinstance(contract, dict):
            return None
        compatibility = contract.get("profit_compatibility")
        reasons = compatibility.get("reason_codes") if isinstance(compatibility, dict) else None
        return reasons[0] if isinstance(reasons, list) and reasons else None

    @staticmethod
    def _safe_code(value):
        text = str(value or "").strip().upper()
        return text if text and re.fullmatch(r"[A-Z0-9_]{1,96}", text) else None

    def _analytics_menu_text(self, snapshot):
        current_period, previous_period = self._snapshot_periods(snapshot)
        lines = ["📊 Аналитика прибыли магазина"]
        lines.append("Текущий период: " + current_period)
        lines.append("Предыдущий период: " + previous_period)
        lines.append("Снимок: " + self._snapshot_timestamp(snapshot.get("generated_at")))
        lines.append("База сравнения: прибыль до внешних расходов (B).")
        metrics = snapshot.get("comparison_metrics") or {}
        profit = metrics.get("profit") if isinstance(metrics, dict) else None
        if (
            snapshot.get("comparison_status") == "CONFIRMED"
            and isinstance(profit, dict)
            and profit.get("comparison_status") == "COMPARABLE"
        ):
            lines.extend([
                "Изменение прибыли: " + self._signed_money(profit.get("delta")),
                "Вклады, объясняющие изменение:",
            ])
            bridge = snapshot.get("profit_bridge")
            bridge_b = bridge.get("B") if isinstance(bridge, dict) else None
            contributions = (
                bridge_b.get("contributions")
                if isinstance(bridge_b, dict)
                else None
            )
            if not isinstance(contributions, dict):
                contributions = {}
            for key, label in (
                ("net_accrual_change", "Начисления Ozon"),
                ("product_cost_contribution", "Себестоимость"),
                ("return_cogs_contribution", "Return COGS"),
                ("tax_contribution", "Налог"),
            ):
                amount = contributions.get(key)
                if amount is not None and amount != 0:
                    lines.append("• " + label + ": " + self._signed_money(amount))
        else:
            lines.append("Сравнение прибыли пока не подтверждено.")
            lines.append("Подробности покажут доступные показатели и ограничения.")
        lines.append("\nРасходы и остаток не распределяются между товарами без подтверждённых данных.")
        return "\n".join(lines)

    def _analytics_detail_text(self, snapshot, view_type):
        if view_type == "comparison":
            return "PERIOD_PROFIT_COMPARISON_VIEW_READY", self._comparison_detail_text(snapshot)
        if view_type == "bridge":
            return "PERIOD_PROFIT_BRIDGE_VIEW_READY", self._bridge_detail_text(snapshot)
        if view_type == "sku_contribution":
            return "PERIOD_PROFIT_SKU_CONTRIBUTION_VIEW_READY", self._sku_detail_text(snapshot)
        return "PERIOD_PROFIT_ANALYTICS_VIEW_UNAVAILABLE", "Этот экран аналитики недоступен. Откройте отчёт заново."

    def _comparison_detail_text(self, snapshot):
        current_period, previous_period = self._snapshot_periods(snapshot)
        lines = [
            "📅 Сравнение периодов",
            "Текущий: " + current_period,
            "Предыдущий: " + previous_period,
            "Снимок: " + self._snapshot_timestamp(snapshot.get("generated_at")),
            "База: прибыль до внешних расходов (B).",
            "",
        ]
        labels = (
            ("revenue", "Выручка", "RUB"),
            ("net_accrual", "Начисления Ozon", "RUB"),
            ("product_cost", "Себестоимость", "RUB"),
            ("tax", "Налог", "RUB"),
            ("profit", "Прибыль до внешних расходов", "RUB"),
            ("margin_percent", "Маржа", "PERCENT"),
            ("external_expenses", "Внешние расходы", "RUB"),
            ("profit_after_external_expenses", "Прибыль после внешних расходов", "RUB"),
            ("units_sold", "Продано единиц", "UNIT"),
        )
        metrics = snapshot.get("comparison_metrics")
        for key, label, unit in labels:
            row = metrics.get(key) if isinstance(metrics, dict) else None
            if not isinstance(row, dict):
                continue
            if row.get("comparison_status") != "COMPARABLE" or row.get("delta") is None:
                lines.append(label + ": нет сопоставимых данных.")
                continue
            current = self._metric_value(row.get("current_value"), unit)
            previous = self._metric_value(row.get("previous_value"), unit)
            delta = self._metric_delta(row.get("delta"), row.get("delta_unit"), unit)
            lines.append(f"{label}: {current}; было {previous}; изменение {delta}.")
        if snapshot.get("comparison_status") != "CONFIRMED":
            lines.extend([
                "",
                "Сравнение прибыли не подтверждено; недоступные значения не считаются нулём.",
            ])
        return "\n".join(lines)

    def _bridge_detail_text(self, snapshot):
        bridge = snapshot.get("profit_bridge")
        b = bridge.get("B") if isinstance(bridge, dict) else None
        lines = ["🧾 Что изменило прибыль", "База: прибыль до внешних расходов (B).", ""]
        if not isinstance(b, dict) or b.get("status") != "CONFIRMED":
            lines.append("Денежный мост прибыли не подтверждён для этих периодов.")
            lines.append("Основной расчёт магазина не менялся.")
        else:
            lines.append("Изменение прибыли: " + self._signed_money(b.get("authoritative_delta")))
            contributions = b.get("contributions") or {}
            for key, label in (
                ("net_accrual_change", "Изменение начислений Ozon"),
                ("product_cost_contribution", "Вклад себестоимости"),
                ("return_cogs_contribution", "Вклад Return COGS"),
                ("tax_contribution", "Вклад налога"),
                ("rounding_adjustment", "Округление"),
            ):
                amount = contributions.get(key)
                if amount is not None:
                    lines.append(label + ": " + self._signed_money(amount))
            detail = b.get("net_accrual_detail")
            if isinstance(detail, dict) and detail.get("status") == "CONFIRMED":
                lines.extend([
                    "  • Выручка внутри начислений: " + self._signed_money(detail.get("revenue_change")),
                    "  • Прочие начисления внутри этой суммы: " + self._signed_money(detail.get("other_net_accrual_change")),
                ])
            lines.append("Суммы внутри начислений не вычитаются повторно.")
        e = bridge.get("E") if isinstance(bridge, dict) else None
        if isinstance(e, dict) and e.get("status") == "CONFIRMED":
            lines.append("\nИзменение после подтверждённых внешних расходов: " + self._signed_money(e.get("authoritative_delta")))
            lines.append("Это отдельная база E, не прибавляйте её к базе B.")
        else:
            lines.append("\nРезультат после внешних расходов не подтверждён для обоих периодов.")
        return "\n".join(lines)

    def _sku_detail_text(self, snapshot):
        contribution = snapshot.get("sku_contribution")
        lines = ["🛍 Вклад сопоставленных SKU", "Изменение относится к прибыли, рассчитанной по строкам SKU.", ""]
        if not isinstance(contribution, dict) or contribution.get("coverage_status") == "UNAVAILABLE":
            lines.append("Сопоставимые данные по SKU недоступны для этих периодов.")
            lines.append("Изменение прибыли магазина остаётся главным итогом.")
            return "\n".join(lines)
        for key, label in (("top_growth", "Наибольший рост"), ("top_decline", "Наибольшее снижение")):
            rows = contribution.get(key)
            lines.append(label + ":")
            if not isinstance(rows, list) or not rows:
                lines.append("• Нет подтверждённых строк.")
                continue
            for row in rows[:5]:
                if not isinstance(row, dict):
                    continue
                sku = self._safe_analytics_identifier(
                    row.get("sku") or row.get("offer_id")
                )
                lines.append("• " + sku + ": " + self._signed_money(row.get("delta")))
        lines.extend([
            "",
            "Изменение прибыли магазина: " + self._signed_money(contribution.get("store_profit_delta")),
            "По сопоставленным SKU: " + self._signed_money(contribution.get("matched_sku_profit_delta")),
            "Арифметический остаток магазина: " + self._signed_money(contribution.get("store_minus_sku_delta")),
        ])
        unmatched_current = self._count(contribution.get("unmatched_current_count"))
        unmatched_previous = self._count(contribution.get("unmatched_previous_count"))
        if unmatched_current or unmatched_previous:
            lines.append(f"Без однозначной пары: {unmatched_current} в текущем и {unmatched_previous} в предыдущем периоде.")
            lines.append("Отсутствующие строки не объявлены нулём и не включены в лидеров.")
        if contribution.get("coverage_status") != "COMPLETE":
            lines.append("Покрытие SKU неполное; остаток не распределяется по товарам.")
        return "\n".join(lines)

    @staticmethod
    def _snapshot_periods(snapshot):
        periods = snapshot.get("periods") if isinstance(snapshot, dict) else None
        current = periods.get("current") if isinstance(periods, dict) else None
        previous = periods.get("previous") if isinstance(periods, dict) else None
        return (
            AssistantPeriodProfitRuntimeService._period_label(current),
            AssistantPeriodProfitRuntimeService._period_label(previous),
        )

    @staticmethod
    def _period_label(period):
        if not isinstance(period, dict):
            return "не подтверждён"
        values = []
        for key in ("date_from", "date_to"):
            try:
                values.append(datetime.strptime(period[key], "%Y-%m-%d").strftime("%d.%m.%Y"))
            except (KeyError, TypeError, ValueError):
                return "не подтверждён"
        return " — ".join(values)

    @staticmethod
    def _snapshot_timestamp(value):
        if not isinstance(value, str):
            return "не указан"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "не указан"
        if parsed.tzinfo is None:
            return parsed.strftime("%d.%m.%Y %H:%M") + " UTC"
        return parsed.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    @staticmethod
    def _metric_value(value, unit):
        if unit == "RUB":
            return AssistantPeriodProfitRuntimeService._finite_money(value)
        if unit == "PERCENT":
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return "—"
            return f"{number:.2f}%" if isfinite(number) else "—"
        if unit == "UNIT":
            return str(value) + " шт." if type(value) is int and value >= 0 else "—"
        return "—"

    @classmethod
    def _metric_delta(cls, value, delta_unit, unit):
        if unit == "RUB":
            return cls._signed_money(value)
        if unit == "PERCENT":
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return "—"
            if not isfinite(number):
                return "—"
            return f"{number:+.2f} п.п." if delta_unit == "PERCENTAGE_POINT" else f"{number:+.2f}%"
        if unit == "UNIT":
            return f"{value:+d} шт." if type(value) is int else "—"
        return "—"

    @classmethod
    def _signed_money(cls, value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return "—"
        if not isfinite(number):
            return "—"
        return ("+" if number > 0 else "") + cls._finite_money(number)

    @staticmethod
    def _finite_money(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return "—"
        if not isfinite(number):
            return "—"
        return f"{number:,.2f} ₽".replace(",", " ")

    @staticmethod
    def _count(value):
        return value if type(value) is int and value >= 0 else 0

    def _monotonic_now(self):
        try:
            value = self.clock()
            number = float(value)
        except Exception:
            return None
        return number if isfinite(number) and number >= 0 else None

    def _expire_report_views_locked(self, now):
        for key, cached in list(self._report_views.items()):
            expires_at = cached.get("expires_at") if isinstance(cached, dict) else None
            if (
                isinstance(expires_at, bool)
                or not isinstance(expires_at, (int, float))
                or now >= expires_at
            ):
                self._report_views.pop(key, None)

    def _build_completeness_keyboard(self, view_id, actions):
        builder = getattr(
            self.keyboard_service,
            "build_period_profit_completeness_keyboard",
            None,
        )
        if callable(builder):
            return builder(view_id, actions)
        return {"error": False, "type": "inline_keyboard", "buttons": [{
            "text": "↩️ К расчёту",
            "callback": "period_profit_report:" + view_id,
        }]}

    @staticmethod
    def _cached_view_expired():
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CACHED_VIEW_EXPIRED",
            "message": "Снимок расчёта устарел или относится к другому магазину. Сформируйте отчёт заново.",
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _safe_trace_text(trace):
        if not isinstance(trace, dict):
            return ""
        keys = (
            "product_id_present",
            "offer_id_present",
            "finance_sku_present",
            "catalog_sku_present",
            "catalog_sku_differs",
            "identity_recovered",
            "primary_lookup_code",
            "catalog_lookup_attempted",
            "catalog_lookup_code",
            "product_id_lookup_code",
            "offer_id_lookup_code",
            "finance_sku_lookup_code",
            "catalog_sku_lookup_code",
            "current_cost_present",
            "current_cost_date_relation",
        )
        parts = []
        for key in keys:
            value = trace.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            parts.append(key + "=" + text)
        return "; ".join(parts)

    @staticmethod
    def _looks_like_identity_statement(value):
        if "sku" not in value:
            return False
        return any(
            phrase in value
            for phrase in (
                "один товар",
                "тот же товар",
                "это один товар",
                "это тот же товар",
                "same product",
                "same item",
                "отменить связь",
                "удалить связь",
                "отозвать связь",
                "не один товар",
                "не тот же товар",
            )
        )

    @staticmethod
    def _is_profit_request(value):
        if "юнит" in value or "unit econom" in value:
            return False

        return any(
            token in value
            for token in (
                "прибыль",
                "заработал",
                "profit",
                "маржа",
                "маржин",
                "margin",
            )
        )

    @classmethod
    def _extract_custom_dates(cls, value):
        tokens = re.findall(
            r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})(?!\d)",
            value,
        )

        if not tokens:
            return None

        if len(tokens) != 2:
            return ()

        normalized = []

        for token in tokens:
            date_format = (
                "%d.%m.%Y"
                if "." in token
                else "%Y-%m-%d"
            )

            try:
                parsed = datetime.strptime(
                    token,
                    date_format,
                ).date()
            except ValueError:
                return ()

            normalized.append(
                parsed.isoformat()
            )

        return tuple(normalized)

    @staticmethod
    def _invalid_custom_period():
        return {
            "error": True,
            "code": "PERIOD_PROFIT_CUSTOM_PERIOD_INVALID",
            "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
            "message": (
                "Проверьте период. Используйте две корректные даты "
                "в формате ДД.ММ.ГГГГ, например "
                "01.05.2026 - 03.09.2026."
            ),
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _resolve_period(value):
        if "сегодня" in value or "today" in value:
            return "TODAY"
        matches = (
            (r"(?<!\d)(90\s*(?:дней|дня)?|90d)(?!\d)", "90D"),
            (r"(?<!\d)(56\s*(?:дней|дня)?|56d)(?!\d)", "56D"),
            (r"(?<!\d)(28\s*(?:дней|дня)?|28d)(?!\d)", "28D"),
            (r"(?<!\d)(7\s*(?:дней|дня)?|7d)(?!\d)", "7D"),
        )
        for pattern, code in matches:
            if re.search(pattern, value):
                return code
        return None
