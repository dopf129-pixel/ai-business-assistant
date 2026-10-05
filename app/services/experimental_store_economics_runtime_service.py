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
    ANALYTICS_METRICS = ("ordered_units", "cancellations", "returns")
    ANALYTICS_DIMENSIONS = ("day",)
    ANALYTICS_PAGE_SIZE = 1000
    FEE_LABEL_MATCHERS = {
        "last_mile": (
            "последняя миля",
            "последней мили",
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
            "paid storage",
            "paidstorage",
            "storage fee",
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
        metrics["fee_breakdown"] = self._fee_breakdown(summary)
        metrics["finance_advertising"] = self._finance_advertising(
            metrics["fee_breakdown"]
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
        return [
            item
            for item in fee_breakdown
            if not any(
                matcher in item["label"].casefold()
                for matcher in excluded_matchers
            )
        ]

    @staticmethod
    def _render(date_from, date_to, metrics):
        advertising = metrics["advertising"]
        analytics = metrics["analytics"]
        fees = metrics["fee_subcategories"]
        finance_advertising = metrics["finance_advertising"]
        cpc_text = _money_or_status(
            advertising.get("cpc"),
            advertising.get("status"),
        )
        campaign_count = advertising.get("campaign_count")
        if isinstance(campaign_count, int) and not isinstance(campaign_count, bool):
            cpc_text += f" ({campaign_count} камп.)"
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
                    f"{_money(group['amount'])}"
                )
        else:
            ad_lines.append(
                "   • Рекламные типы не распознаны в начислениях Ozon"
            )
        ad_lines.append(
            "   • Performance CPC по сопоставленным SKU (для сверки): "
            + cpc_text
        )
        other_fee_details = ExperimentalStoreEconomicsRuntimeService._other_fee_details(
            metrics["fee_breakdown"]
        )
        lines = [
            f"🧪 Экономика магазина за период {date_from} — {date_to}",
            "",
            "1. Выручка общая (100%): " + _money(metrics["revenue"]),
            "2. Выручка ФНС (выручка − баллы): " + _money(metrics["revenue_tax_base"]),
            "3. Баллы за скидки: " + _money(metrics["discount_points"]),
            "4. Начисления Ozon нетто: " + _money(metrics["net_accrual"]),
            "5. Налог: " + _money(metrics["tax"]),
            "6. Прибыль без себестоимости: " + _money(metrics["profit"]),
            "7. Расходы на рекламу:",
            *ad_lines,
            "8. Эквайринг: " + _money(metrics["acquiring"]),
            "9. Вознаграждение Ozon: " + _money(metrics["commission"]),
            "10. Логистика всего: " + _money(metrics["logistics"]),
            "11. Последняя миля: " + _fee_or_unconfirmed(fees.get("last_mile")),
            "12. Кросс-докинг: " + _fee_or_unconfirmed(fees.get("cross_docking")),
            "13. Платное хранение: " + _fee_or_unconfirmed(fees.get("paid_storage")),
            "14. Прочие начисления Ozon (включая рекламные и складские услуги): "
            + _money(metrics["other_fees"]),
            "15. Заказанные единицы (Analytics): " + _unit_or_unconfirmed(
                analytics.get("ordered_units"),
                analytics.get("ordered_units_status"),
                analytics.get("ordered_units_diagnostic"),
                "заказанных единиц",
            ),
            "16. Отменённые единицы (Analytics): " + _unit_or_unconfirmed(
                analytics.get("cancellations"),
                analytics.get("cancellations_status"),
                analytics.get("cancellations_diagnostic"),
                "отменённых единиц",
            ),
            "17. Возвраты (Analytics): " + _unit_or_unconfirmed(
                analytics.get("returns"),
                analytics.get("returns_status"),
                analytics.get("returns_diagnostic"),
                "возвратов",
            ),
            "",
            "⚠️ Экспериментальный результат, не заменяет основные расчёты.",
            "Источники: суммы и удержания — финансовые начисления Ozon; заказанные единицы, отмены и возвраты — Analytics; CPC по SKU — Ozon Performance.",
            "Прибыль рассчитана по нетто-начислениям Ozon за вычетом налога. Расходы, уже попавшие в начисления, учтены в прибыли. Performance CPC показан для сверки и может пересекаться с финансовыми начислениями; повторно его не вычитайте.",
            "Подтипы ниже раскрывают итоги, а не добавляются к ним: последняя миля входит в логистику; рекламные и складские услуги входят в прочие начисления, если они выставлены Ozon.",
            "Разделение рекламы по типам возможно только по явным названиям начислений; отчёт по начислениям не содержит разбивки по кампаниям.",
            "Прибыль рассчитана существующим способом без себестоимости; это не итоговая прибыль магазина.",
        ]
        if other_fee_details:
            lines.extend(
                [
                    "",
                    "Детализация прочих начислений (уже входит в строку 14):",
                ]
            )
            for item in other_fee_details[:5]:
                lines.append(
                    f"   • {item['label']}: {_money(item['amount'])}"
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
        number = Decimal(str(value))
        if number == number.to_integral_value():
            return f"{int(number):,}".replace(",", " ")
        formatted = f"{number:,.2f}".rstrip("0").rstrip(".")
        return formatted.replace(",", " ").replace(".", ",")
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
