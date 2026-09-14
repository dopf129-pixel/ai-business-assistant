import re
from datetime import datetime

from period_profit_compact_response import compact_period_profit_result
from services.period_profit_cost_confirmation_runtime_service import (
    PeriodProfitCostConfirmationRuntimeService,
)
from services.period_profit_effective_cost_service import PeriodProfitEffectiveCostService


class AssistantPeriodProfitRuntimeService:
    """Narrow Period Profit route plus seller-confirmed local cost corrections."""

    PERIOD_CODES = {"TODAY", "7D", "28D", "56D", "90D"}

    def __init__(self, query_service, cost_confirmation_runtime_service=None):
        self.query_service = query_service
        self.cost_confirmation_runtime_service = (
            cost_confirmation_runtime_service
            or PeriodProfitCostConfirmationRuntimeService(
                PeriodProfitEffectiveCostService()
            )
        )

    def handle_text(self, text, today=None):
        if self.cost_confirmation_runtime_service is not None:
            confirmation = self.cost_confirmation_runtime_service.handle_text(text)
            if confirmation is not None:
                return confirmation

        value = " ".join(str(text or "").strip().lower().split())
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
    def _present(result):
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
