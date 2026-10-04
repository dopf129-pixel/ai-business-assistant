import re
from datetime import datetime
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
    ANALYTICS_METRICS = ("ordered_units", "cancellations")
    ANALYTICS_DIMENSIONS = ("day",)
    ANALYTICS_PAGE_SIZE = 1000
    FEE_LABEL_MATCHERS = {
        "last_mile": ("последняя миля", "последней мили", "last mile", "last-mile"),
        "cross_docking": ("кросс-док", "кросс док", "cross-dock", "cross dock"),
        "paid_storage": (
            "платное хран",
            "paid storage",
            "storage fee",
        ),
    }

    def __init__(self, query_service, advertising_service=None, analytics_client=None):
        self.query_service = query_service
        self.advertising_service = advertising_service
        self.analytics_client = analytics_client
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
        metrics["analytics"] = self._load_analytics(date_from, date_to)
        metrics["fee_subcategories"] = self._fee_subcategories(summary)

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
            "profit",
            "acquiring",
            "commission",
            "logistics",
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
        return {
            "status": "READY",
            "cpc": amount,
            "campaign_count": campaign_count,
            "scope": "CPC_MATCHED_SKUS",
        }

    def _load_analytics(self, date_from, date_to):
        getter = getattr(self.analytics_client, "get_analytics_data", None)
        if not callable(getter):
            return {"status": "UNAVAILABLE", "ordered_units": None, "cancellations": None}
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
            return {"status": "UNAVAILABLE", "ordered_units": None, "cancellations": None}
        if not isinstance(response, dict) or response.get("error") is True:
            return {"status": "UNAVAILABLE", "ordered_units": None, "cancellations": None}
        result = response.get("result")
        rows = result.get("data") if isinstance(result, dict) else None
        if not isinstance(rows, list) or len(rows) >= self.ANALYTICS_PAGE_SIZE:
            return {"status": "INCOMPLETE", "ordered_units": None, "cancellations": None}

        totals = [Decimal("0"), Decimal("0")]
        for row in rows:
            values = row.get("metrics") if isinstance(row, dict) else None
            if not isinstance(values, list) or len(values) != len(totals):
                return {"status": "INVALID", "ordered_units": None, "cancellations": None}
            for index, value in enumerate(values):
                number = self._decimal(value)
                if number is None or number < 0:
                    return {"status": "INVALID", "ordered_units": None, "cancellations": None}
                totals[index] += number
                if not totals[index].is_finite():
                    return {"status": "INVALID", "ordered_units": None, "cancellations": None}
        if any(not value.to_integral_value() == value for value in totals):
            return {"status": "INVALID", "ordered_units": None, "cancellations": None}
        return {
            "status": "READY",
            "ordered_units": int(totals[0]),
            "cancellations": int(totals[1]),
        }

    @classmethod
    def _fee_subcategories(cls, summary):
        breakdown = summary.get("fee_breakdown")
        result = {}
        for category, matchers in cls.FEE_LABEL_MATCHERS.items():
            amounts = []
            if isinstance(breakdown, dict):
                for label, value in breakdown.items():
                    normalized = cls._text(label).casefold()
                    if any(matcher in normalized for matcher in matchers):
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

    @staticmethod
    def _render(date_from, date_to, metrics):
        advertising = metrics["advertising"]
        analytics = metrics["analytics"]
        fees = metrics["fee_subcategories"]
        cpc_text = _money_or_status(
            advertising.get("cpc"),
            advertising.get("status"),
        )
        campaign_count = advertising.get("campaign_count")
        if isinstance(campaign_count, int) and not isinstance(campaign_count, bool):
            cpc_text += f" ({campaign_count} камп.)"
        lines = [
            f"🧪 Экономика магазина за период {date_from} — {date_to}",
            "",
            "1. Выручка общая (100%): " + _money(metrics["revenue"]),
            "2. Выручка ФНС (выручка − баллы): " + _money(metrics["revenue_tax_base"]),
            "3. Баллы за скидки: " + _money(metrics["discount_points"]),
            "4. Прибыль без себестоимости: " + _money(metrics["profit"]),
            "5. Расходы на рекламу:",
            "   • CPC по сопоставленным SKU (не общий бюджет): " + cpc_text,
            "   • CPO: не включён — нет надёжного подтверждённого источника в этом эксперименте",
            "   • CPM и другие типы: не включены",
            "6. Эквайринг: " + _money(metrics["acquiring"]),
            "7. Вознаграждение Ozon: " + _money(metrics["commission"]),
            "8. Логистика всего: " + _money(metrics["logistics"]),
            "9. Последняя миля: " + _fee_or_unconfirmed(fees.get("last_mile")),
            "10. Кросс-докинг: " + _fee_or_unconfirmed(fees.get("cross_docking")),
            "11. Платное хранение: " + _fee_or_unconfirmed(fees.get("paid_storage")),
            "12. Заказанные единицы: " + _unit_or_unconfirmed(analytics.get("ordered_units"), analytics.get("status")),
            "13. Отменённые единицы: " + _unit_or_unconfirmed(analytics.get("cancellations"), analytics.get("status")),
            "",
            "⚠️ Экспериментальный результат, не заменяет основные расчёты.",
            "Расход CPC сопоставляется только с SKU каталога и финансового отчёта; CPO, CPM и другие типы не считаются нулём и не входят в сумму. Реклама показана отдельно и не вычтена из прибыли в строке 4.",
            "Строки последней мили, кросс-докинга и хранения выделяются только по явной подписи в начислениях; они входят в общие начисления Ozon и повторно не вычитаются.",
            "Прибыль рассчитана существующим способом без себестоимости; это не итоговая прибыль магазина.",
        ]
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
        return "не выделено отдельной строкой в начислениях Ozon"
    return _money(value)


def _unit_or_unconfirmed(value, status):
    if value is not None:
        return f"{value:,}".replace(",", " ")
    labels = {
        "INCOMPLETE": "данные неполные",
        "INVALID": "данные некорректны",
    }
    return labels.get(status, "аналитика Ozon недоступна")
