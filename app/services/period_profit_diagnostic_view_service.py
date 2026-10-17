"""Build a bounded diagnostic view from one cached Period Profit snapshot."""


class PeriodProfitDiagnosticViewService:
    STATUS_LABELS = {
        "CONFIRMED": "подтверждено",
        "PARTIAL": "частично",
        "UNKNOWN": "неизвестно",
        "ERROR": "ошибка источника или сверки",
        "STALE": "источник устарел",
        "FRESH": "источник помечен свежим",
        "NOT_REPORTED": "источник не сообщает свежесть",
        "CONFLICT": "обнаружено противоречие",
        "NOT_CONFIRMED": "не подтверждено",
    }
    STATUS_KEYS = {
        "financial_base",
        "sku_quantity",
        "cost",
        "historical_return_cost",
        "tax",
        "external_expenses",
        "advertising",
        "returns",
        "source_freshness",
        "identity",
    }
    ALLOWED_STATUS_CODES = frozenset(STATUS_LABELS)
    REASON_LABELS = {
        "SOURCE_STALE": "источник явно помечен устаревшим",
        "IDENTITY_CONFLICT": "идентичность товара противоречит другим данным",
        "IDENTITY_NOT_CONFIRMED": "идентичность SKU не подтверждена",
        "PARTIAL_COVERAGE": "источники подтверждают только часть данных",
        "FINANCIAL_BASE_UNCONFIRMED": "финансовая база не полностью подтверждена",
        "SKU_QUANTITY_UNCONFIRMED": "количество или сверка SKU неполны",
        "COST_MISSING": "не хватает подтверждённой себестоимости",
        "RETURN_COST_UNCONFIRMED": "историческая себестоимость возвратов не подтверждена",
        "TAX_POLICY_UNCONFIRMED": "налоговая политика не подтверждена",
        "EXTERNAL_EXPENSES_UNCONFIRMED": "не подтверждён учёт внешних расходов",
        "ADVERTISING_EVIDENCE_UNCONFIRMED": "данные рекламных расходов неполны",
        "RETURN_EVIDENCE_UNCONFIRMED": "данные о возвратах неполны",
        "HTTP_ATTEMPT_BUDGET_EXHAUSTED": "достигнут лимит запросов к Ozon",
        "TIME_BUDGET_EXHAUSTED": "истекло время запроса",
        "OPERATION_CANCELLED": "операция была отменена",
    }
    ACTION_CODES = {
        "cost",
        "sku",
        "return_inventory",
        "external_expenses",
    }

    def build(self, date_from, date_to, completeness, operation_summary=None):
        start = self._iso_date(date_from)
        end = self._iso_date(date_to)
        if start is None or end is None or start > end:
            return self._unavailable()
        if not isinstance(completeness, dict) or completeness.get("error") is not False:
            return self._unavailable()

        raw_statuses = completeness.get("diagnostic_statuses")
        statuses = {}
        if isinstance(raw_statuses, dict):
            statuses = {
                key: value
                for key, value in raw_statuses.items()
                if key in self.STATUS_KEYS and value in self.ALLOWED_STATUS_CODES
            }
        reason_codes = self._reason_codes(completeness.get("diagnostic_reason_codes"))
        if any(value == "PARTIAL" for value in statuses.values()):
            reason_codes.append("PARTIAL_COVERAGE")
        if statuses.get("source_freshness") == "STALE":
            reason_codes.append("SOURCE_STALE")
        if statuses.get("identity") == "CONFLICT":
            reason_codes.append("IDENTITY_CONFLICT")
        reason_codes = list(dict.fromkeys(reason_codes))
        operation = self._operation_summary(operation_summary)
        budget_reason = operation.get("budget_reason_code")
        if budget_reason in self.REASON_LABELS and budget_reason != "NONE":
            reason_codes.append(budget_reason)
        reason_codes = list(dict.fromkeys(reason_codes))
        actions = [
            value for value in completeness.get("actions", [])
            if isinstance(value, str) and value in self.ACTION_CODES
        ]
        if set(reason_codes) & {
            "SOURCE_STALE",
            "PARTIAL_COVERAGE",
            "TIME_BUDGET_EXHAUSTED",
            "HTTP_ATTEMPT_BUDGET_EXHAUSTED",
        }:
            actions.append("refresh")
        if "IDENTITY_CONFLICT" in reason_codes or "IDENTITY_NOT_CONFIRMED" in reason_codes:
            actions.append("sku")
        if {"COST_MISSING", "RETURN_COST_UNCONFIRMED"} & set(reason_codes):
            actions.append("cost")
        if "EXTERNAL_EXPENSES_UNCONFIRMED" in reason_codes:
            actions.append("external_expenses")
        if "RETURN_EVIDENCE_UNCONFIRMED" in reason_codes:
            actions.append("return_inventory")

        lines = [
            "❓ Почему расчёт неполный? " + start + " — " + end,
            "",
            "Проверка использует сохранённый результат и не запускает новые запросы.",
        ]
        if reason_codes:
            lines.append("")
            lines.append("Подтверждённые причины:")
            lines.extend(
                "• " + self.REASON_LABELS[code]
                for code in reason_codes
                if code in self.REASON_LABELS
            )
        else:
            lines.extend([
                "",
                "Явных причин неполноты в доступной диагностике не найдено.",
            ])
        if statuses:
            lines.extend(["", "Полнота источников:"])
            for key in sorted(statuses):
                lines.append(
                    "• " + key + ": " + self.STATUS_LABELS[statuses[key]]
                )
        lines.extend([
            "",
            "Операция: "
            + str(operation["elapsed_seconds"])
            + " сек.; HTTP-попытки "
            + str(operation["http_attempts"])
            + "/"
            + str(operation["http_attempt_cap"])
            + ".",
            "Проверки отправлений: "
            + str(operation["rows_completed"])
            + " завершено, "
            + str(operation["rows_unknown"])
            + " неизвестно из "
            + str(operation["rows_attempted"])
            + " попыток.",
            "События диагностики: "
            + str(operation["events_total"])
            + " всего, "
            + str(operation["events_dropped"])
            + " удалено из ограниченного буфера.",
        ])
        return {
            "error": False,
            "status": "PERIOD_PROFIT_DIAGNOSTICS_READY",
            "date_from": start,
            "date_to": end,
            "text": "\n".join(lines),
            "reason_codes": reason_codes,
            "source_completeness": statuses,
            "operation": operation,
            "actions": list(dict.fromkeys(actions)),
            "read_only": True,
            "executed": False,
        }

    def _operation_summary(self, value):
        raw = value if isinstance(value, dict) else {}
        operation_id = raw.get("operation_id")
        if not isinstance(operation_id, str) or len(operation_id) != 32:
            operation_id = "unknown"
        else:
            operation_id = operation_id.lower()
            if any(ch not in "0123456789abcdef" for ch in operation_id):
                operation_id = "unknown"
        raw_budget_reason = raw.get("budget_reason_code")
        budget_reason = (
            "NONE"
            if raw_budget_reason in (None, "")
            else self._safe_code(raw_budget_reason)
        )
        return {
            "operation_id": operation_id,
            "operation_type": self._safe_code(raw.get("operation_type")),
            "started_at_utc": self._safe_time(raw.get("started_at_utc")),
            "elapsed_seconds": self._count(raw.get("elapsed_seconds")),
            "stage_code": self._safe_code(raw.get("stage_code")),
            "events_total": self._count(raw.get("events_total")),
            "events_dropped": self._count(raw.get("events_dropped")),
            "http_attempts": self._count(raw.get("http_attempts")),
            "http_attempt_cap": self._count(raw.get("http_attempt_cap")),
            "rows_attempted": self._count(raw.get("rows_attempted")),
            "rows_completed": self._count(raw.get("rows_completed")),
            "rows_unknown": self._count(raw.get("rows_unknown")),
            "budget_reason_code": budget_reason,
        }

    @classmethod
    def _reason_codes(cls, value):
        if not isinstance(value, (list, tuple)):
            return []
        return list(dict.fromkeys(
            item for item in value
            if isinstance(item, str) and item in cls.REASON_LABELS
        ))

    @staticmethod
    def _count(value):
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return min(max(value, 0), 1000000000)

    @staticmethod
    def _safe_code(value, default="UNKNOWN"):
        if not isinstance(value, str) or not value or len(value) > 64:
            return default
        if not all(ch.isascii() and (ch.isalnum() or ch in "_.-") for ch in value):
            return default
        return value.upper()

    @staticmethod
    def _safe_time(value):
        if not isinstance(value, str) or len(value) > 40:
            return "unknown"
        if not value.endswith("Z") or "T" not in value:
            return "unknown"
        return value

    @staticmethod
    def _iso_date(value):
        if not isinstance(value, str) or len(value) != 10:
            return None
        try:
            from datetime import date

            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat()

    @staticmethod
    def _unavailable():
        return {
            "error": False,
            "status": "PERIOD_PROFIT_DIAGNOSTICS_UNAVAILABLE",
            "text": "Диагностика этого отчёта недоступна. Сформируйте отчёт заново.",
            "read_only": True,
            "executed": False,
        }
