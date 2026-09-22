import re
from datetime import datetime
from threading import RLock

from period_profit_compact_response import compact_period_profit_result
from services.period_profit_cost_confirmation_runtime_service import (
    PeriodProfitCostConfirmationRuntimeService,
)
from services.period_profit_effective_cost_service import PeriodProfitEffectiveCostService
from services.period_profit_identity_confirmation_runtime_service import (
    PeriodProfitIdentityConfirmationRuntimeService,
)


class AssistantPeriodProfitRuntimeService:
    """Narrow Period Profit route plus seller-confirmed local corrections."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}

    def __init__(
        self,
        query_service,
        cost_confirmation_runtime_service=None,
        identity_confirmation_runtime_service=None,
    ):
        self.query_service = query_service
        self.cost_confirmation_runtime_service = cost_confirmation_runtime_service
        self.identity_confirmation_runtime_service = identity_confirmation_runtime_service
        self._custom_period_users = set()
        self._custom_period_lock = RLock()

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
            self._custom_period_users.add(user_key)
        return {
            "error": False,
            "status": "PERIOD_PROFIT_CUSTOM_PERIOD_INPUT_REQUIRED",
            "message": "Введите период в формате 01.01.2026-02.02.2026",
            "read_only": True,
            "executed": False,
        }

    def handle_text(self, text, today=None, user_id=None):
        value = " ".join(str(text or "").strip().lower().split())

        user_key = self._user_key(user_id)
        with self._custom_period_lock:
            custom_period_pending = user_key in self._custom_period_users
        if custom_period_pending:
            if value in {"отмена", "cancel", "/cancel"}:
                with self._custom_period_lock:
                    self._custom_period_users.discard(user_key)
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
            with self._custom_period_lock:
                self._custom_period_users.discard(user_key)
            return self._present(
                self._query_with_optional_comparison(
                    date_from=dates[0], date_to=dates[1], today=today
                )
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

            return self._present(
                self._query_with_optional_comparison(
                    date_from=dates[0],
                    date_to=dates[1],
                    today=today,
                )
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

        return self._present(
            self._query_with_optional_comparison(
                period_code=period,
                today=today,
            )
        )

    def handle_callback(self, callback_data, today=None):
        value = str(callback_data or "").strip().upper()
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
        return self._present(
            self._query_with_optional_comparison(
                period_code=period,
                today=today,
            )
        )

    def _query_with_optional_comparison(self, **kwargs):
        compared = self.query_service.query(
            compare_previous=True,
            **kwargs,
        )
        if not isinstance(compared, dict) or compared.get("error") is not True:
            return compared

        current = self.query_service.query(
            compare_previous=False,
            **kwargs,
        )
        if not isinstance(current, dict) or current.get("error") is not False:
            return current if isinstance(current, dict) else compared

        degraded = dict(current)
        degraded["comparison"] = None
        degraded["previous_summary"] = None
        degraded["comparison_status"] = "PERIOD_PROFIT_COMPARISON_UNAVAILABLE"
        degraded["comparison_error_code"] = compared.get("code")
        degraded["comparison_read_only"] = True
        return degraded

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
    def _present(result):
        if isinstance(result, dict) and result.get("error") is True:
            code = str(result.get("code") or "").strip()
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
                        "Операции Ozon найдены, но не все исторические SKU "
                        "удалось однозначно сопоставить с товарами каталога. "
                        "Расчёт остановлен, чтобы не смешать данные разных товаров."
                    )
                    if skus:
                        message += "\nSKU без подтверждённой связи: " + ", ".join(skus)
                    message += (
                        "\nОткройте «Прибыль за период» → «По выбранному SKU» "
                        "для нужного товара: бот покажет подтверждение связи, "
                        "если Ozon предоставляет достаточные доказательства."
                        "\nКод диагностики: " + diagnostic
                    )
                    output["message"] = message
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
