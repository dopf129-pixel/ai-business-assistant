from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
from threading import RLock

from services.tenant_context import get_current_tenant_user_id


class SellerAttentionSummaryService:
    """Build a bounded, read-only seller summary from existing decisions."""

    CACHE_TTL_SECONDS = 300
    CACHE_MAX_ENTRIES = 64
    FRESHNESS_LIMIT_SECONDS = 3600
    MAX_MESSAGE_UTF16_UNITS = 3500
    MAX_PRIORITIES = 5
    MAX_MISSING_DETAILS = 3

    PRIORITY_ORDER = {
        "CRITICAL": 0,
        "HIGH": 1,
        "NORMAL": 2,
        "LOW": 3,
        "NONE": 4,
    }
    PRIORITY_LABELS = {
        "CRITICAL": "Критический",
        "HIGH": "Высокий",
        "NORMAL": "Обычный",
        "LOW": "Низкий",
        "NONE": "Нет",
    }
    DECISION_PRIORITY = {
        "REPLENISH_HIGH_PRIORITY": "CRITICAL",
        "REPLENISH_NORMAL": "HIGH",
        "WATCH_LOW_MARGIN": "NORMAL",
        "INVESTIGATE_LOW_PROFIT": "HIGH",
        "HOLD_STOCK": "LOW",
        "INSUFFICIENT_DATA": "NONE",
    }
    REASON_LABELS = {
        "DAYS_OF_STOCK_CRITICAL": "критически мало дней запаса",
        "DAYS_OF_STOCK_LOW": "запас ниже комфортного уровня",
        "NEGATIVE_UNIT_PROFIT": "отрицательная прибыль с единицы",
        "LOW_UNIT_PROFIT": "низкая прибыль с единицы",
        "LOW_MARGIN": "низкая маржа",
        "SALES_DECLINING": "продажи снижаются к предыдущему периоду",
        "ECONOMICS_INCOMPLETE": "экономика товара рассчитана не полностью",
        "IDENTITY_MISMATCH": "идентификаторы товара расходятся",
    }
    MISSING_LABELS = {
        "advertising": "реклама",
        "storage": "хранение",
        "returns": "расходы на возвраты",
        "returns_finance": "финансы возвратов",
        "tax": "налог",
        "cost": "себестоимость",
        "profit_per_unit": "прибыль с единицы",
        "margin_percent": "маржа",
        "sales_velocity": "скорость продаж",
        "sales_trend": "тренд продаж",
        "current_stock": "остаток",
        "days_of_stock": "дни запаса",
        "stock_priority": "приоритет остатка",
        "unit_economics": "юнит-экономика",
        "decision": "решение по товару",
        "IDENTITY_MISMATCH": "идентификатор товара",
        "external_expenses": "внешние расходы",
    }
    SOURCE_FIELDS = {
        "sales": ("sales_source_recorded_at", "sales_observed_at", "Продажи"),
        "stock": ("stock_source_recorded_at", "stock_observed_at", "Остатки"),
        "unit_economics": (
            "unit_economics_source_recorded_at",
            "unit_economics_observed_at",
            "Юнит-экономика",
        ),
    }
    SKU_PATTERN = re.compile(r"[^\x00-\x1f\x7f]{1,128}\Z")

    def __init__(
        self,
        product_decision_query,
        keyboard_service=None,
        clock=None,
        cache_ttl_seconds=CACHE_TTL_SECONDS,
        cache_max_entries=CACHE_MAX_ENTRIES,
        freshness_limit_seconds=FRESHNESS_LIMIT_SECONDS,
    ):
        self.product_decision_query = product_decision_query
        self.keyboard_service = keyboard_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.cache_max_entries = max(1, int(cache_max_entries))
        self.freshness_limit_seconds = max(0, int(freshness_limit_seconds))
        self._cache = OrderedDict()
        self._lock = RLock()

    def build(self, user_id=None):
        user_key = str(user_id or "").strip()
        if not user_key:
            return self._error("SELLER_ATTENTION_USER_REQUIRED")
        if self.product_decision_query is None:
            return self._error("SELLER_ATTENTION_SOURCE_UNAVAILABLE")

        now = self._now()
        scope = (
            str(get_current_tenant_user_id() or user_key).strip(),
            user_key,
        )
        with self._lock:
            cached = self._cache.get(scope)
            if isinstance(cached, dict) and cached["valid_until"] > now:
                self._cache.move_to_end(scope)
                return deepcopy(cached["result"])
            self._cache.pop(scope, None)

        try:
            overview = self.product_decision_query.query_all()
        except Exception:
            return self._error("SELLER_ATTENTION_QUERY_FAILED")

        prepared = self._prepare(overview, now)
        if prepared.get("error") is True:
            return prepared

        result = self._render(prepared, now)
        deadlines = [now + timedelta(seconds=self.cache_ttl_seconds)]
        deadlines.extend(prepared.get("freshness_deadlines") or [])
        valid_until = min(deadlines)
        with self._lock:
            self._cache[scope] = {
                "valid_until": valid_until,
                "result": deepcopy(result),
            }
            self._cache.move_to_end(scope)
            while len(self._cache) > self.cache_max_entries:
                self._cache.popitem(last=False)
        return result

    def _prepare(self, overview, now):
        if (
            not isinstance(overview, dict)
            or overview.get("error") is not False
            or not isinstance(overview.get("decisions"), list)
            or type(overview.get("total")) is not int
            or overview["total"] != len(overview["decisions"])
        ):
            return self._error("SELLER_ATTENTION_SOURCE_INVALID")

        priorities = []
        missing = []
        deadlines = []
        seen_skus = set()
        for decision in overview["decisions"]:
            if not self._valid_decision(decision, seen_skus):
                return self._error("SELLER_ATTENTION_SOURCE_INVALID")
            sku = decision["sku"].strip()
            seen_skus.add(sku)
            reasons = set(decision["reasons"])
            stock_without_sales = (
                decision.get("stock_priority") == "NO_SALES"
                and self._finite_non_negative(decision.get("current_stock"))
                and float(decision.get("current_stock")) > 0
            )
            if stock_without_sales:
                reasons.add("STOCK_WITHOUT_SALES")
            alert_reasons = reasons.intersection(
                set(self.REASON_LABELS) | {"STOCK_WITHOUT_SALES"}
            )
            actionable_reasons = alert_reasons.difference({
                "ECONOMICS_INCOMPLETE", "IDENTITY_MISMATCH"
            })
            missing_data = decision["missing_data"]

            if actionable_reasons:
                required = self._required_sources(actionable_reasons)
                freshness = self._freshness(decision, required, now)
                if freshness["status"] == "FRESH":
                    item = self._priority_item(
                        decision, actionable_reasons, freshness
                    )
                    priorities.append(item)
                    deadlines.extend(freshness["deadlines"])
                    if missing_data:
                        missing.append(
                            self._missing_item(
                                decision,
                                self._missing_labels(missing_data),
                            )
                        )
                else:
                    explanation = freshness["reason"]
                    labels = self._missing_labels(missing_data)
                    if labels:
                        explanation += "; не хватает: " + ", ".join(labels)
                    missing.append({
                        "sku": sku,
                        "reason": explanation,
                        "priority": decision["priority"],
                    })
            elif (
                decision["decision_type"] == "INSUFFICIENT_DATA"
                or missing_data
                or alert_reasons
            ):
                labels = self._missing_labels(missing_data)
                if not labels:
                    labels = ["данные для решения"]
                missing.append(self._missing_item(decision, labels))

        priorities.sort(key=lambda item: (
            self.PRIORITY_ORDER[item["priority"]], item["sku"].casefold()
        ))
        missing.sort(key=lambda item: (
            self.PRIORITY_ORDER.get(item["priority"], 4),
            item["sku"].casefold(),
        ))
        return {
            "error": False,
            "priorities": priorities[:self.MAX_PRIORITIES],
            "priority_total": len(priorities),
            "missing": missing,
            "missing_total": len(missing),
            "freshness_deadlines": deadlines,
        }

    def _valid_decision(self, decision, seen_skus):
        if not isinstance(decision, dict) or decision.get("error") is not False:
            return False
        sku = decision.get("sku")
        reasons = decision.get("reasons")
        missing = decision.get("missing_data")
        priority = decision.get("priority")
        decision_type = decision.get("decision_type")
        return (
            isinstance(sku, str)
            and bool(self.SKU_PATTERN.fullmatch(sku.strip()))
            and sku.strip() not in seen_skus
            and decision_type in self.DECISION_PRIORITY
            and self.DECISION_PRIORITY[decision_type] == priority
            and isinstance(reasons, list)
            and all(isinstance(item, str) for item in reasons)
            and isinstance(missing, list)
            and all(isinstance(item, str) for item in missing)
        )

    @staticmethod
    def _required_sources(reasons):
        required = set()
        if reasons.intersection({
            "DAYS_OF_STOCK_CRITICAL", "DAYS_OF_STOCK_LOW", "STOCK_WITHOUT_SALES"
        }):
            required.update(("sales", "stock"))
        if reasons.intersection({
            "NEGATIVE_UNIT_PROFIT", "LOW_UNIT_PROFIT", "LOW_MARGIN",
            "POSITIVE_UNIT_PROFIT",
        }):
            required.add("unit_economics")
        if "SALES_DECLINING" in reasons:
            required.add("sales")
        return tuple(sorted(required))

    def _freshness(self, decision, required, now):
        deadlines = []
        dates = []
        problems = []
        for component in required:
            source_field, observed_field, label = self.SOURCE_FIELDS[component]
            source_time = decision.get(source_field)
            observed_fallback = source_time is None
            value = decision.get(observed_field) if observed_fallback else source_time
            parsed = self._parse_time(value)
            if parsed is None:
                problems.append(label + ": время источника неизвестно")
                continue
            age_seconds = (now - parsed).total_seconds()
            if age_seconds < 0:
                problems.append(label + ": время источника некорректно")
                continue
            if age_seconds > self.freshness_limit_seconds:
                problems.append(label + ": данные старше одного часа")
                continue
            deadlines.append(
                parsed + timedelta(seconds=self.freshness_limit_seconds)
            )
            suffix = " (проверено ботом)" if observed_fallback else ""
            dates.append(label + " " + parsed.strftime("%d.%m %H:%M UTC") + suffix)
        if problems:
            return {
                "status": "UNKNOWN",
                "reason": "; ".join(problems),
                "dates": dates,
                "deadlines": [],
            }
        return {
            "status": "FRESH",
            "reason": "",
            "dates": dates,
            "deadlines": deadlines,
        }

    def _priority_item(self, decision, reasons, freshness):
        reasons_ordered = sorted(
            reasons,
            key=lambda item: (item != "STOCK_WITHOUT_SALES", item),
        )
        labels = [
            "есть остаток, продаж в периоде нет"
            if reason == "STOCK_WITHOUT_SALES"
            else self.REASON_LABELS[reason]
            for reason in reasons_ordered
        ]
        facts = []
        stock = self._finite_non_negative(decision.get("current_stock"))
        days = self._finite_non_negative(decision.get("days_of_stock"))
        profit = self._finite_number(decision.get("decision_profit_per_unit"))
        margin = self._finite_number(decision.get("decision_margin_percent"))
        if stock is not None:
            facts.append("остаток " + self._quantity(stock) + " шт.")
        if days is not None:
            facts.append("запаса примерно на " + self._quantity(days) + " дн.")
        if profit is not None:
            facts.append("прибыль с единицы " + self._money(profit))
        if margin is not None:
            facts.append("маржа " + self._percent(margin))
        limitations = self._missing_labels(decision["missing_data"])
        return {
            "sku": decision["sku"].strip(),
            "priority": decision["priority"],
            "reason": ", ".join(labels),
            "facts": "; ".join(facts),
            "dates": "; ".join(freshness["dates"]),
            "limitations": limitations,
        }

    def _missing_item(self, decision, labels):
        reasons = []
        if decision["decision_type"] == "INSUFFICIENT_DATA":
            reasons.append("решение пока невозможно подтвердить")
        if labels:
            reasons.append("не хватает: " + ", ".join(labels))
        return {
            "sku": decision["sku"].strip(),
            "priority": decision["priority"],
            "reason": "; ".join(reasons) or "нужна проверка данных",
        }

    def _missing_labels(self, values):
        return list(dict.fromkeys(
            self.MISSING_LABELS.get(value, "дополнительные данные")
            for value in values
        ))

    def _render(self, prepared, now):
        priorities = prepared["priorities"]
        missing = prepared["missing"]
        lines = [
            "🔎 На что обратить внимание",
            "Сформировано: " + now.strftime("%d.%m.%Y %H:%M UTC"),
            "Приоритеты построены по существующим решениям и фактам Ozon.",
            "",
            "Актуальные приоритеты: " + str(len(priorities)),
        ]
        if priorities:
            for index, item in enumerate(priorities, 1):
                lines.append(
                    str(index) + ". Приоритет: "
                    + self.PRIORITY_LABELS[item["priority"]] + " — SKU "
                    + item["sku"] + ": " + item["reason"]
                )
                if item["facts"]:
                    lines.append("   Факты: " + item["facts"])
                if item["dates"]:
                    lines.append("   Срез: " + item["dates"])
                if item["limitations"]:
                    lines.append(
                        "   Не подтверждено: " + ", ".join(item["limitations"])
                    )
        else:
            lines.append("По последнему срезу подтверждённых актуальных приоритетов нет.")
        if prepared["priority_total"] > len(priorities):
            lines.append(
                "Показаны первые " + str(self.MAX_PRIORITIES)
                + " из " + str(prepared["priority_total"]) + " приоритетов."
            )

        lines.extend(["", "Нужно уточнить данные: " + str(len(missing))])
        if missing:
            for item in missing[:self.MAX_MISSING_DETAILS]:
                lines.append("• SKU " + item["sku"] + " — " + item["reason"])
            if prepared["missing_total"] > self.MAX_MISSING_DETAILS:
                lines.append(
                    "• Ещё товаров с неполными/устаревшими данными: "
                    + str(prepared["missing_total"] - self.MAX_MISSING_DETAILS)
                )
        else:
            lines.append("По данным текущего обзора уточнения не требуются.")

        lines.extend([
            "",
            "Реклама: ДРР и ROAS не рассчитываются без подтверждённых расходов "
            "и сопоставленной выручки.",
            "Внешние расходы и Return COGS проверяйте через «Прибыль за период» "
            "→ «Полнота данных»; этот обзор не пересчитывает прибыль магазина.",
        ])
        priority_skus = [item["sku"] for item in priorities]
        missing_skus = [item["sku"] for item in missing[:self.MAX_MISSING_DETAILS]]
        message = "\n".join(lines)
        if self._utf16_units(message) > self.MAX_MESSAGE_UTF16_UNITS:
            message = self._render_compact(prepared, now)

        keyboard = self._keyboard(priority_skus, missing_skus)
        return {
            "error": False,
            "status": "SELLER_ATTENTION_SUMMARY_READY",
            "message": message,
            "keyboard": keyboard,
            "priority_count": len(priorities),
            "missing_data_count": len(missing),
            "read_only": True,
            "executed": False,
        }

    def _render_compact(self, prepared, now):
        priorities = prepared["priorities"]
        missing = prepared["missing"]
        lines = [
            "🔎 На что обратить внимание",
            "Сформировано: " + now.strftime("%d.%m.%Y %H:%M UTC"),
            "Короткий формат: подробности доступны по кнопкам.",
            "Актуальные приоритеты: " + str(len(priorities)),
        ]
        if priorities:
            for index, item in enumerate(priorities, 1):
                lines.append(
                    str(index) + ". "
                    + self.PRIORITY_LABELS[item["priority"]]
                    + " — SKU " + item["sku"] + ": "
                    + self._truncate_utf16(item["reason"], 48)
                    + " (факты: "
                    + self._truncate_utf16(item["facts"], 40)
                    + "; срез: "
                    + self._truncate_utf16(item["dates"], 32)
                    + ")"
                )
        else:
            lines.append("Подтверждённых актуальных приоритетов нет.")
        if prepared["priority_total"] > len(priorities):
            lines.append(
                "Показаны первые " + str(len(priorities)) + " из "
                + str(prepared["priority_total"]) + " приоритетов."
            )

        lines.append("Нужно уточнить данные: " + str(len(missing)))
        for item in missing[:self.MAX_MISSING_DETAILS]:
            lines.append(
                "• SKU " + item["sku"] + ": "
                + self._truncate_utf16(item["reason"], 48)
            )
        if prepared["missing_total"] > self.MAX_MISSING_DETAILS:
            lines.append(
                "• Ещё товаров с неполными/устаревшими данными: "
                + str(prepared["missing_total"] - self.MAX_MISSING_DETAILS)
            )
        lines.extend([
            "ДРР/ROAS не рассчитываются без подтверждённых расходов "
            "и атрибутированной выручки.",
            "Внешние расходы и Return COGS: «Прибыль за период» "
            "→ «Полнота данных»; прибыль здесь не пересчитывается.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _utf16_units(value):
        return len(value.encode("utf-16-le")) // 2

    @classmethod
    def _truncate_utf16(cls, value, max_units):
        text = str(value or "")
        if cls._utf16_units(text) <= max_units:
            return text
        suffix = "…"
        remaining = max(0, max_units - cls._utf16_units(suffix))
        result = []
        for character in text:
            width = 2 if ord(character) > 0xFFFF else 1
            if width > remaining:
                break
            result.append(character)
            remaining -= width
        return "".join(result) + suffix

    def _keyboard(self, priority_skus, missing_skus):
        builder = getattr(
            self.keyboard_service, "build_seller_attention_keyboard", None
        )
        if callable(builder):
            return builder(priority_skus, missing_skus)
        buttons = [
            {"text": "🔎 SKU " + sku, "callback": "product_decision:" + sku}
            for sku in priority_skus + missing_skus
        ]
        buttons.extend([
            {"text": "🎯 Решения по товарам", "callback": "product_decisions"},
            {"text": "💵 Прибыль за период", "callback": "period_profit"},
        ])
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime):
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_time(value):
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _finite_number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None

    @classmethod
    def _finite_non_negative(cls, value):
        number = cls._finite_number(value)
        return number if number is not None and number >= 0 else None

    @staticmethod
    def _quantity(value):
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:.1f}"

    @staticmethod
    def _money(value):
        return f"{value:,.2f} ₽".replace(",", " ")

    @staticmethod
    def _percent(value):
        return ("%.2f" % value).replace(".", ",") + "%"

    @staticmethod
    def _error(code):
        messages = {
            "SELLER_ATTENTION_USER_REQUIRED": "Для обзора нужен Telegram-пользователь.",
            "SELLER_ATTENTION_SOURCE_UNAVAILABLE": "Решения по товарам недоступны.",
            "SELLER_ATTENTION_QUERY_FAILED": "Не удалось получить текущие решения по товарам.",
            "SELLER_ATTENTION_SOURCE_INVALID": "Данные обзора не прошли проверку; приоритеты не показаны.",
        }
        return {
            "error": True,
            "code": code,
            "message": messages.get(code, "Обзор временно недоступен."),
            "read_only": True,
            "executed": False,
        }
