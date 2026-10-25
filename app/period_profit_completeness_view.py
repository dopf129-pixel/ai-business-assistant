from datetime import date
from math import isfinite
import re

from services.period_profit_return_cogs_blocker_stage_service import (
    PeriodProfitReturnCogsBlockerStageService,
)


class PeriodProfitCompletenessViewService:
    """Build a read-only completeness view from one exact profit result."""

    def build(self, result):
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._unavailable()
        if result.get("status") != "PERIOD_PROFIT_QUERY_READY":
            return self._unavailable()

        summary = result.get("summary")
        if (
            not isinstance(summary, dict)
            or summary.get("error") is not False
            or summary.get("status") != "PERIOD_PROFIT_SUMMARY_READY"
        ):
            return self._unavailable()

        start = self._iso_date(summary.get("date_from"))
        end = self._iso_date(summary.get("date_to"))
        request = result.get("request")
        if (
            start is None
            or end is None
            or start > end
            or not isinstance(request, dict)
            or request.get("date_from") != start.isoformat()
            or request.get("date_to") != end.isoformat()
        ):
            return self._unavailable("Период результата не совпадает с запросом.")

        lines = [
            "🔎 Полнота данных " + self._period(start, end),
            "",
        ]
        actions = []
        return_status, return_reason, return_action, identities = self._return_status(
            result, start, end
        )
        application_confirmed = self._application_confirmed(
            summary, result, return_status
        )
        if summary.get("return_cogs_profit_applied") is True:
            base_profit = self._number(
                summary.get("period_profit_before_return_cogs")
            ) if application_confirmed else None
        else:
            base_profit = self._number(summary.get("profit"))
        if base_profit is None:
            reason = (
                "применённая сумма Return COGS не прошла проверку цепочки"
                if summary.get("return_cogs_profit_applied") is True
                else "сумма расчёта некорректна"
            )
            lines.append("Базовая прибыль: неизвестно — " + reason + ".")
        else:
            lines.append("Базовая прибыль: " + self._money(base_profit))

        finance_status, finance_reason = self._finance_status(summary)
        lines.append(self._block("Финансовая база", finance_status, finance_reason))

        quantity_status, quantity_reason = self._quantity_status(summary)
        lines.append(self._block("SKU и количество", quantity_status, quantity_reason))
        if quantity_status != "ПОДТВЕРЖДЕНО":
            actions.append("sku")

        cost_status, cost_reason = self._cost_status(summary)
        lines.append(self._block("Себестоимость продаж", cost_status, cost_reason))
        if cost_status != "ПОДТВЕРЖДЕНО":
            actions.append("cost")

        historical_status, historical_reason = self._historical_cost_status(
            result, start, end
        )
        lines.append(
            self._block("Историческая себестоимость возвратов", historical_status, historical_reason)
        )
        if historical_status != "ПОДТВЕРЖДЕНО":
            actions.append("cost")

        tax_status, tax_reason = self._tax_status(summary)
        lines.append(self._block("Налог", tax_status, tax_reason))

        external_status, external_reason = self._external_status(
            result.get("external_expense_evidence"), start, end
        )
        lines.append(self._block("Внешние расходы", external_status, external_reason))
        if external_status != "ПОДТВЕРЖДЕНО":
            actions.append("external_expenses")

        advertising_status, advertising_reason = self._advertising_status(
            result.get("advertising_financial_evidence")
        )
        lines.append(
            self._block("Реклама (отдельная сверка)", advertising_status, advertising_reason)
        )

        lines.append(self._block("Возвраты / Return COGS", return_status, return_reason))
        if identities:
            lines.append("Возвраты для проверки: " + "; ".join(identities))
        if return_action:
            actions.append(return_action)

        lines.extend([
            "",
        ])
        if application_confirmed:
            amount = self._number(
                summary.get("return_cogs_profit_application_amount")
            )
            if amount is None:
                amount = self._number(
                    result["return_cogs_recovery_evidence"].get(
                        "return_cogs_profit_application_amount"
                    )
                )
            if amount is None:
                lines.append("Применённое дополнение Return COGS: сумма неизвестна.")
            else:
                lines.append(
                    "Подтверждённое дополнение Return COGS уже учтено: "
                    + self._money(amount)
                )
        else:
            lines.append(
                "Return COGS не добавляется к прибыли без полного подтверждения всей цепочки."
            )
        components = self._component_evidence(
            summary,
            result,
            start,
            end,
            {
                "financial_base": finance_status,
                "sku_quantity": quantity_status,
                "cost": cost_status,
                "historical_return_cost": historical_status,
                "tax": tax_status,
                "external_expenses": external_status,
                "advertising": advertising_status,
                "returns": return_status,
            },
            {
                "financial_base": finance_reason,
                "sku_quantity": quantity_reason,
                "cost": cost_reason,
                "historical_return_cost": historical_reason,
                "tax": tax_reason,
                "external_expenses": external_reason,
                "advertising": advertising_reason,
                "returns": return_reason,
            },
        )
        lines.extend(["", "Суммы и источники за период:"])
        for item in components:
            amount = item["amount"]
            if amount is None:
                amount_text = "неизвестно"
            elif item["unit"] == "RUB":
                amount_text = self._money(amount)
            else:
                amount_text = str(int(amount)) + " " + item["unit"]
            lines.append(
                "• "
                + item["label"]
                + ": "
                + amount_text
                + "; "
                + item["source"]
                + "; "
                + item["date_basis"]
                + "; "
                + item["status_label"]
                + " — "
                + item["reason"]
                + "."
            )
        diagnostic_statuses = {
            "financial_base": self._diagnostic_status(finance_status),
            "sku_quantity": self._diagnostic_status(quantity_status),
            "cost": self._diagnostic_status(cost_status),
            "historical_return_cost": self._diagnostic_status(historical_status),
            "tax": self._diagnostic_status(tax_status),
            "external_expenses": self._diagnostic_status(external_status),
            "advertising": self._diagnostic_status(advertising_status),
            "returns": self._diagnostic_status(return_status),
        }
        freshness = str(
            summary.get("source_freshness_status")
            or summary.get("source_cache_status")
            or ""
        ).strip().upper()
        if (
            summary.get("source_stale") is True
            or freshness in {"STALE", "EXPIRED"}
        ):
            diagnostic_statuses["source_freshness"] = "STALE"
        elif freshness == "FRESH":
            diagnostic_statuses["source_freshness"] = "FRESH"
        else:
            diagnostic_statuses["source_freshness"] = "NOT_REPORTED"
        diagnostic_statuses["identity"] = (
            "CONFLICT"
            if summary.get("identity_conflict_detected") is True
            or summary.get("sku_identity_conflict") is True
            else "NOT_CONFIRMED"
            if diagnostic_statuses["sku_quantity"] != "CONFIRMED"
            else "CONFIRMED"
        )
        diagnostic_reason_codes = self._diagnostic_reason_codes(
            diagnostic_statuses
        )
        return {
            "error": False,
            "status": "PERIOD_PROFIT_COMPLETENESS_READY",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "message": "\n".join(lines),
            "component_evidence": components,
            "actions": list(dict.fromkeys(actions)),
            "diagnostic_statuses": diagnostic_statuses,
            "diagnostic_reason_codes": diagnostic_reason_codes,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _component_evidence(
        cls,
        summary,
        result,
        start,
        end,
        statuses,
        reasons,
    ):
        period = {
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        }
        account_scope = summary.get("account_level_ozon_accruals_included") is True
        finance_source = (
            "Финансы Ozon, уровень магазина"
            if account_scope
            else "Финансы Ozon по выбранным SKU; итог магазина не подтверждён"
        )
        source_by_key = {
            "revenue": (finance_source, "дата начисления"),
            "discount_points": (finance_source, "дата начисления"),
            "tax_base": ("расчётная налоговая база", "период отчёта"),
            "net_accrual": (finance_source, "дата начисления"),
            "commission": (finance_source, "дата начисления"),
            "logistics": (finance_source, "дата начисления"),
            "acquiring": (finance_source, "дата начисления"),
            "other_fees": (finance_source, "дата начисления"),
            "tax": ("настройка налоговой политики и TaxService", "период отчёта"),
            "profit": ("существующий расчёт Period Profit", "период отчёта"),
            "units_sold": ("финансовые продажи по SKU", "дата продажи в источнике"),
            "product_cost": ("себестоимость продавца по дате действия", "дата продажи"),
            "external_expenses": ("журнал внешних расходов продавца", "дата расхода"),
            "advertising": ("явные типы рекламных начислений Ozon", "дата начисления"),
            "returns": ("Seller API: выборка возвратов", "период/статус согласно evidence источника"),
            "historical_return_cost": ("история себестоимости продавца и подтверждённые возвраты", "дата исходной продажи и дата действия себестоимости"),
        }
        labels = {
            "revenue": ("Выручка", "RUB"),
            "discount_points": ("Баллы за скидки", "RUB"),
            "tax_base": ("Налоговая база", "RUB"),
            "net_accrual": ("Нетто-начисления", "RUB"),
            "commission": ("Комиссия", "RUB"),
            "logistics": ("Логистика", "RUB"),
            "acquiring": ("Эквайринг", "RUB"),
            "other_fees": ("Прочие начисления", "RUB"),
            "tax": ("Налог", "RUB"),
            "profit": ("Прибыль до внешних расходов", "RUB"),
            "units_sold": ("Проданные единицы", "шт."),
            "product_cost": ("Себестоимость", "RUB"),
            "external_expenses": ("Внешние расходы", "RUB"),
            "advertising": ("Реклама, отдельная сверка", "RUB"),
            "returns": ("Возвраты", "записей"),
            "historical_return_cost": ("Историческая себестоимость возвратов", "RUB"),
        }
        raw_statuses = {
            "financial_base": statuses.get("financial_base"),
            "sku_quantity": statuses.get("sku_quantity"),
            "cost": statuses.get("cost"),
            "tax": statuses.get("tax"),
            "external_expenses": statuses.get("external_expenses"),
            "advertising": statuses.get("advertising"),
            "returns": statuses.get("returns"),
            "historical_return_cost": statuses.get("historical_return_cost"),
        }
        raw_reasons = {
            "financial_base": reasons.get("financial_base"),
            "sku_quantity": reasons.get("sku_quantity"),
            "cost": reasons.get("cost"),
            "tax": reasons.get("tax"),
            "external_expenses": reasons.get("external_expenses"),
            "advertising": reasons.get("advertising"),
            "returns": reasons.get("returns"),
            "historical_return_cost": reasons.get("historical_return_cost"),
        }

        amount_map = {
            "revenue": summary.get("revenue"),
            "discount_points": summary.get("discount_points"),
            "tax_base": summary.get("tax_base") if statuses.get("tax") == "ПОДТВЕРЖДЕНО" else None,
            "net_accrual": summary.get("net_accrual"),
            "commission": summary.get("commission"),
            "logistics": summary.get("logistics"),
            "acquiring": summary.get("acquiring"),
            "other_fees": summary.get("other_fees"),
            "tax": summary.get("tax") if statuses.get("tax") == "ПОДТВЕРЖДЕНО" else None,
            "profit": (
                summary.get("profit")
                if all(
                    statuses.get(key) == "ПОДТВЕРЖДЕНО"
                    for key in ("financial_base", "cost", "tax")
                )
                else None
            ),
            "units_sold": summary.get("units_sold"),
            "product_cost": summary.get("product_cost") if statuses.get("cost") == "ПОДТВЕРЖДЕНО" else None,
        }
        recovery = result.get("return_cogs_recovery_evidence")
        if (
            isinstance(recovery, dict)
            and recovery.get("historical_cost_basis_confirmed") is True
        ):
            amount_map["historical_return_cost"] = recovery.get(
                "candidate_value_at_historical_cost"
            )
        else:
            amount_map["historical_return_cost"] = None
        external = result.get("external_expense_evidence")
        if (
            isinstance(external, dict)
            and external.get("error") is False
            and external.get("date_from") == start.isoformat()
            and external.get("date_to") == end.isoformat()
        ):
            amount_map["external_expenses"] = external.get("observed_expense_total")
        else:
            amount_map["external_expenses"] = None
        advertising = result.get("advertising_financial_evidence")
        if (
            isinstance(advertising, dict)
            and advertising.get("error") is False
            and advertising.get("policy_configured") is True
        ):
            amount_map["advertising"] = advertising.get("matched_amount")
        else:
            amount_map["advertising"] = None
        return_evidence = result.get("return_evidence")
        if (
            isinstance(return_evidence, dict)
            and return_evidence.get("error") is False
            and statuses.get("returns") in {"ПОДТВЕРЖДЕНО", "ЧАСТИЧНО"}
            and return_evidence.get("return_record_count_exact") is True
            and isinstance(return_evidence.get("records"), list)
            and cls._integer(return_evidence.get("return_record_count"))
            == len(return_evidence["records"])
        ):
            amount_map["returns"] = len(return_evidence["records"])
        else:
            amount_map["returns"] = None

        rows = []
        key_to_status = {
            "revenue": "financial_base",
            "discount_points": "financial_base",
            "tax_base": "financial_base",
            "net_accrual": "financial_base",
            "commission": "financial_base",
            "logistics": "financial_base",
            "acquiring": "financial_base",
            "other_fees": "financial_base",
            "tax": "tax",
            "profit": "financial_base",
            "units_sold": "sku_quantity",
            "product_cost": "cost",
            "external_expenses": "external_expenses",
            "advertising": "advertising",
            "returns": "returns",
            "historical_return_cost": "historical_return_cost",
        }
        for key, (label, unit) in labels.items():
            raw = amount_map.get(key)
            amount = cls._number(raw)
            if unit == "шт." or unit == "записей":
                integer = cls._integer(raw)
                amount = float(integer) if integer is not None else None
            status_key = key_to_status[key]
            status = cls._diagnostic_status(raw_statuses.get(status_key))
            source, date_basis = source_by_key[key]
            reason = str(raw_reasons.get(status_key) or "значение подтверждено источником")
            if key == "profit":
                component_statuses = [
                    cls._diagnostic_status(statuses.get(name))
                    for name in ("financial_base", "cost", "tax")
                ]
                severity = {"CONFIRMED": 0, "PARTIAL": 1, "UNKNOWN": 2, "ERROR": 3}
                status = max(component_statuses, key=lambda value: severity[value])
                if status != "CONFIRMED":
                    reason = "итог наследует неполноту финансовой базы, себестоимости или налоговой политики"
            elif key == "tax_base":
                status = cls._diagnostic_status(statuses.get("tax"))
                reason = str(raw_reasons.get("tax") or "налоговая политика не подтверждена")
            if key == "tax_base":
                reason = "база согласно применённой налоговой политике; не налоговое заключение"
            elif key == "profit":
                reason = "расчёт включает налог и себестоимость; внешние расходы отражаются отдельно"
            elif key == "advertising":
                reason += "; сумма уже входит в нетто-начисления и повторно не вычитается"
            elif key == "external_expenses":
                if status != "CONFIRMED":
                    reason += "; показана только наблюдаемая сумма, полнота периода не подтверждена"
                else:
                    reason += "; внешняя корректировка применяется только при полном покрытии"
            elif key == "returns":
                reason += "; количество записей не равно числу единиц и не меняет прибыль автоматически"
            elif key == "historical_return_cost":
                reason = "историческая стоимость подтверждается только при полном совпадении даты продажи и себестоимости"
            rows.append({
                "key": key,
                "label": label,
                "amount": round(amount, 2) if amount is not None and unit == "RUB" else amount,
                "unit": unit,
                "source": source,
                "date_basis": date_basis,
                "period": dict(period),
                "status": status,
                "coverage": status,
                "status_label": {
                    "CONFIRMED": "подтверждено",
                    "PARTIAL": "частично",
                    "UNKNOWN": "неизвестно",
                    "ERROR": "ошибка сверки/источника",
                }.get(status, "неизвестно"),
                "reason": reason,
            })
        return rows

    def _return_status(self, result, start, end):
        raw = result.get("return_evidence")
        evidence = result.get("return_cogs_recovery_evidence")
        if not isinstance(raw, dict) or raw.get("error") is True:
            return "НЕИЗВЕСТНО", "источник возвратов недоступен", None, []
        if (
            raw.get("date_from") != start.isoformat()
            or raw.get("date_to") != end.isoformat()
        ):
            return "ОШИБКА", "период evidence возвратов не совпадает с отчётом", None, []
        if not isinstance(evidence, dict) or evidence.get("error") is True:
            return "ОШИБКА", "не удалось проверить возвраты", None, []
        if evidence.get("status") != "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY":
            return "НЕИЗВЕСТНО", "evidence восстановления недоступен", None, []

        raw_records = raw.get("records")
        candidates = evidence.get("candidate_records")
        compensated = evidence.get("compensated_records")
        unresolved = evidence.get("unresolved_records")
        if (
            not isinstance(raw_records, list)
            or not isinstance(candidates, list)
            or not isinstance(compensated, list)
            or not isinstance(unresolved, list)
        ):
            return "ОШИБКА", "структура возвратов неполная", None, []

        declared_count = self._integer(raw.get("return_record_count"))
        if declared_count is None or declared_count != len(raw_records):
            return "ОШИБКА", "число записей возвратов не сходится с источником", None, []

        candidate_units, candidate_valid = self._record_units(candidates)
        compensated_units, compensated_valid = self._record_units(compensated)
        unresolved_known_units, unresolved_quantity_count = self._known_record_units(unresolved)
        declared_candidates = self._integer(evidence.get("candidate_recovery_units"))
        declared_compensated = self._integer(evidence.get("compensated_units"))
        declared_unresolved = self._integer(evidence.get("unresolved_units"))
        declared_customer_units = self._integer(evidence.get("customer_return_units"))
        if (
            not candidate_valid
            or not compensated_valid
            or declared_candidates is None
            or declared_compensated is None
            or declared_unresolved is None
            or declared_customer_units is None
            or candidate_units != declared_candidates
            or compensated_units != declared_compensated
            or unresolved_known_units != declared_unresolved
            or candidate_units + compensated_units + unresolved_known_units
            != declared_customer_units
        ):
            return "ОШИБКА", "количество записей и единиц Return COGS не сходится", None, []

        if not self._evidence_records_match_source(
            raw_records, candidates + compensated
        ):
            return "ОШИБКА", "идентичность кандидатов не сходится с исходными возвратами", None, []

        record_count = len(candidates)
        reasons = [
            str(record_count) + " кандидатов / " + str(candidate_units) + " шт.",
            str(len(compensated)) + " компенсированных записей / "
            + str(compensated_units) + " шт.",
        ]
        if unresolved:
            reasons.append(
                "не подтверждено записей: " + str(len(unresolved))
                + "; единиц с известным количеством: "
                + str(unresolved_known_units)
                + "; записей без количества: "
                + str(unresolved_quantity_count)
            )

        complete_sample = (
            raw.get("complete") is True
            and raw.get("return_record_count_exact") is True
            and evidence.get("return_sample_complete") is True
        )
        stage = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        if not isinstance(stage, dict) or stage.get("error") is True:
            return "ОШИБКА", "цепочка доказательств возвратов невалидна", None, []

        if not complete_sample or unresolved:
            reasons.append("выборка неполная или есть неподтверждённые возвраты")
            return "ЧАСТИЧНО", "; ".join(reasons), None, []

        if stage.get("stage") == PeriodProfitReturnCogsBlockerStageService.NONE:
            if evidence.get("return_cogs_profit_applied") is True:
                if evidence.get("return_cogs_final_application_chain_bound") is not True:
                    return "ОШИБКА", "применение не связано с подтверждённой цепочкой", None, []
                reasons.append("цепочка применена и подтверждена")
            else:
                reasons.append("нет неподтверждённого блокера; сумма не добавлялась повторно")
            return "ПОДТВЕРЖДЕНО", "; ".join(reasons), None, []

        stage_name = stage.get("stage")
        if stage_name == PeriodProfitReturnCogsBlockerStageService.INVENTORY:
            blocked = [row for row in stage.get("records", []) if isinstance(row, dict)]
            identities = [self._identity(row) for row in blocked[:3]]
            identities = [identity for identity in identities if identity]
            reasons.append("первый блокер — фактическое состояние возврата")
            return "ЧАСТИЧНО", "; ".join(reasons), "return_inventory", identities

        reasons.append(self._stage_reason(stage_name))
        reasons.append("в боте пока нет подтверждённого действия для этой стадии")
        return "ЧАСТИЧНО", "; ".join(reasons), None, []

    def _historical_cost_status(self, result, start, end):
        raw = result.get("return_evidence")
        evidence = result.get("return_cogs_recovery_evidence")
        if not isinstance(raw, dict) or raw.get("error") is True:
            return "НЕИЗВЕСТНО", "источник возвратов недоступен"
        if (
            raw.get("date_from") != start.isoformat()
            or raw.get("date_to") != end.isoformat()
        ):
            return "ОШИБКА", "период evidence возвратов не совпадает с отчётом"
        if not isinstance(evidence, dict) or evidence.get("error") is True:
            return "ОШИБКА", "историческую себестоимость не удалось проверить"
        if evidence.get("status") != "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY":
            return "НЕИЗВЕСТНО", "evidence восстановления себестоимости недоступен"
        candidates = evidence.get("candidate_records")
        if not isinstance(candidates, list):
            return "ОШИБКА", "список кандидатов некорректен"
        if raw.get("complete") is not True or evidence.get("return_sample_complete") is not True:
            return "ЧАСТИЧНО", "полная выборка возвратов не подтверждена"
        candidate_count = self._integer(
            evidence.get("historical_cost_candidate_record_count")
        )
        matched_count = self._integer(
            evidence.get("historical_cost_matched_candidate_record_count")
        )
        if candidate_count is None or candidate_count != len(candidates) or matched_count is None:
            return "ОШИБКА", "количество исторических оценок не сходится с кандидатами"
        if not candidates:
            return "ПОДТВЕРЖДЕНО", "нет кандидатов, для которых нужна историческая себестоимость"
        historical_value = self._number(
            evidence.get("candidate_value_at_historical_cost")
        )
        if (
            evidence.get("historical_cost_basis_confirmed") is True
            and matched_count == len(candidates)
            and historical_value is not None
        ):
            return "ПОДТВЕРЖДЕНО", "оценка подтверждена для " + str(matched_count) + " из " + str(candidate_count) + " кандидатов"
        return "ЧАСТИЧНО", "оценка подтверждена для " + str(matched_count) + " из " + str(candidate_count) + " кандидатов"

    def _application_confirmed(self, summary, result, return_status):
        if summary.get("return_cogs_profit_applied") is not True:
            return False
        if return_status != "ПОДТВЕРЖДЕНО":
            return False
        evidence = result.get("return_cogs_recovery_evidence")
        if not isinstance(evidence, dict):
            return False
        stage = PeriodProfitReturnCogsBlockerStageService.resolve(evidence)
        return (
            isinstance(stage, dict)
            and stage.get("error") is False
            and stage.get("stage") == PeriodProfitReturnCogsBlockerStageService.NONE
            and evidence.get("return_cogs_profit_applied") is True
            and evidence.get("return_cogs_final_application_chain_bound") is True
            and self._number(summary.get("period_profit_before_return_cogs")) is not None
            and self._number(summary.get("return_cogs_profit_application_amount")) is not None
        )

    @classmethod
    def _finance_status(cls, summary):
        values = [summary.get(key) for key in ("revenue", "net_accrual", "tax", "profit")]
        if any(cls._number(value) is None for value in values):
            return "ОШИБКА", "нет корректных финансовых сумм"
        if (
            summary.get("account_level_ozon_accruals_included") is True
            and summary.get("product_revenue_reconciled") is True
        ):
            return "ПОДТВЕРЖДЕНО", "выручка товаров сверена с финансами Ozon"
        return "ЧАСТИЧНО", "не все начисления или сверка выручки подтверждены"

    @classmethod
    def _quantity_status(cls, summary):
        units = cls._integer(summary.get("units_sold"))
        products = summary.get("products")
        product_count = cls._integer(summary.get("product_count"))
        if units is None or not isinstance(products, list) or product_count != len(products):
            return "НЕИЗВЕСТНО", "нет полной сверки количества по товарам"
        row_units = []
        for row in products:
            value = cls._integer(row.get("units_sold")) if isinstance(row, dict) else None
            if value is None:
                return "ЧАСТИЧНО", str(product_count) + " товаров; количество в части строк неизвестно"
            row_units.append(value)
        if sum(row_units) != units:
            return "ОШИБКА", "сумма по товарам не совпадает с общим количеством"
        if summary.get("product_revenue_reconciled") is not True:
            return "ЧАСТИЧНО", str(units) + " шт.; финансовая сверка товаров не подтверждена"
        return "ПОДТВЕРЖДЕНО", str(product_count) + " товаров, " + str(units) + " шт.; сумма строк сходится"

    @classmethod
    def _cost_status(cls, summary):
        cost = cls._number(summary.get("product_cost"))
        if cost is None or cost < 0:
            return "НЕИЗВЕСТНО", "нет подтверждённой суммы себестоимости"
        return "ПОДТВЕРЖДЕНО", "в отчёте учтено " + cls._money(cost)

    @classmethod
    def _tax_status(cls, summary):
        tax = cls._number(summary.get("tax"))
        base = cls._number(summary.get("tax_base"))
        rate = cls._number(summary.get("tax_rate_percent"))
        mode = str(summary.get("tax_mode") or "").strip().upper()
        if (
            summary.get("tax_policy_applied") is not True
            or tax is None
            or base is None
            or rate is None
            or mode not in {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}
        ):
            return "НЕИЗВЕСТНО", "налоговая политика отчёта не подтверждена"
        return "ПОДТВЕРЖДЕНО", mode + ", ставка " + cls._percent(rate) + ", база " + cls._money(base)

    @classmethod
    def _external_status(cls, evidence, start, end):
        if not isinstance(evidence, dict):
            return "НЕИЗВЕСТНО", "учёт внешних расходов за период не подтверждён"
        if evidence.get("error") is True:
            return "ОШИБКА", "источник внешних расходов недоступен"
        if (
            evidence.get("date_from") != start.isoformat()
            or evidence.get("date_to") != end.isoformat()
        ):
            return "ОШИБКА", "период внешних расходов не совпадает с отчётом"
        if evidence.get("status") not in {
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        }:
            return "НЕИЗВЕСТНО", "не удалось подтвердить данные внешних расходов"
        total = cls._number(evidence.get("observed_expense_total"))
        if total is None or total < 0:
            return "ОШИБКА", "сумма внешних расходов некорректна"
        if evidence.get("coverage_complete") is True:
            return "ПОДТВЕРЖДЕНО", "покрыт весь период; внесено " + cls._money(total)
        gaps = evidence.get("coverage_gaps")
        gap_count = len(gaps) if isinstance(gaps, list) else None
        gap_text = str(gap_count) + " пробелов покрытия" if gap_count is not None else "есть пробелы покрытия"
        return "ЧАСТИЧНО", "внесено " + cls._money(total) + "; " + gap_text

    @classmethod
    def _advertising_status(cls, evidence):
        if not isinstance(evidence, dict):
            return "НЕИЗВЕСТНО", "нет отдельной сверки; расходы в начислениях повторно не вычитаются"
        if evidence.get("error") is True:
            return "ОШИБКА", "сверка не загрузилась; net accrual не пересчитывался"
        if evidence.get("policy_configured") is True:
            count = cls._integer(evidence.get("matched_operation_count"))
            amount = cls._number(evidence.get("matched_amount"))
            if count is None or amount is None:
                return "ОШИБКА", "результат сверки рекламы некорректен"
            return "ПОДТВЕРЖДЕНО", str(count) + " операций, " + cls._money(amount) + "; уже в начислениях"
        return "НЕИЗВЕСТНО", "нет подтверждённого сопоставления; это не меняет net accrual"

    @staticmethod
    def _stage_reason(stage):
        labels = {
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_ATTRIBUTION: "бухгалтерская атрибуция",
            PeriodProfitReturnCogsBlockerStageService.ACCOUNTING_RECOGNITION: "бухгалтерское признание",
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_AUTHORIZATION: "авторизация применения",
            PeriodProfitReturnCogsBlockerStageService.APPLICATION_COMMIT: "подтверждение разового применения",
            PeriodProfitReturnCogsBlockerStageService.FINAL_APPLICATION: "отражение в прибыли",
        }
        return "первый блокер — " + labels.get(stage, "неизвестная стадия")

    @classmethod
    def _identity(cls, row):
        values = [row.get(key) for key in ("return_id", "posting_number", "sku")]
        if any(not cls._safe_identifier(value) for value in values):
            return None
        quantity = cls._integer(row.get("quantity"))
        if quantity is None or quantity < 1:
            return None
        return (
            "return " + str(values[0]) + ", отправление " + str(values[1])
            + ", SKU " + str(values[2]) + ", " + str(quantity) + " шт."
        )

    @staticmethod
    def _safe_identifier(value):
        return isinstance(value, (str, int)) and not isinstance(value, bool) and bool(
            re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(value).strip())
        )

    @classmethod
    def _record_units(cls, records):
        total = 0
        for row in records:
            quantity = cls._integer(row.get("quantity")) if isinstance(row, dict) else None
            if quantity is None or quantity < 1:
                return None, False
            total += quantity
        return total, True

    @classmethod
    def _known_record_units(cls, records):
        total = 0
        missing = 0
        for row in records:
            quantity = cls._integer(row.get("quantity")) if isinstance(row, dict) else None
            if quantity is None or quantity < 1:
                missing += 1
            else:
                total += quantity
        return total, missing

    @classmethod
    def _evidence_records_match_source(cls, raw_records, evidence_records):
        source = {}
        for row in raw_records:
            if not isinstance(row, dict):
                continue
            identity = cls._identity_key(row)
            if identity is None:
                continue
            if identity in source:
                return False
            source[identity] = cls._integer(row.get("quantity"))
        seen = set()
        for row in evidence_records:
            if not isinstance(row, dict):
                return False
            identity = cls._identity_key(row)
            if identity is None or identity in seen or identity not in source:
                return False
            quantity = cls._integer(row.get("quantity"))
            if quantity is None or source[identity] != quantity:
                return False
            seen.add(identity)
        return True

    @classmethod
    def _identity_key(cls, row):
        return_id = row.get("return_id")
        if return_id is None:
            return_id = row.get("id")
        posting = row.get("posting_number")
        sku = row.get("sku")
        if not all(cls._safe_identifier(value) for value in (return_id, posting, sku)):
            return None
        return tuple(str(value).strip() for value in (return_id, posting, sku))

    @staticmethod
    def _block(name, status, reason):
        return name + ": " + status + " — " + reason

    @staticmethod
    def _diagnostic_status(status):
        return {
            "ПОДТВЕРЖДЕНО": "CONFIRMED",
            "ЧАСТИЧНО": "PARTIAL",
            "НЕИЗВЕСТНО": "UNKNOWN",
            "ОШИБКА": "ERROR",
        }.get(str(status or ""), "UNKNOWN")

    @staticmethod
    def _diagnostic_reason_codes(statuses):
        reasons = []
        if statuses.get("source_freshness") == "STALE":
            reasons.append("SOURCE_STALE")
        if statuses.get("identity") == "CONFLICT":
            reasons.append("IDENTITY_CONFLICT")
        if any(value == "PARTIAL" for value in statuses.values()):
            reasons.append("PARTIAL_COVERAGE")
        for key, code in (
            ("financial_base", "FINANCIAL_BASE_UNCONFIRMED"),
            ("sku_quantity", "SKU_QUANTITY_UNCONFIRMED"),
            ("cost", "COST_MISSING"),
            ("historical_return_cost", "RETURN_COST_UNCONFIRMED"),
            ("tax", "TAX_POLICY_UNCONFIRMED"),
            ("external_expenses", "EXTERNAL_EXPENSES_UNCONFIRMED"),
            ("advertising", "ADVERTISING_EVIDENCE_UNCONFIRMED"),
            ("returns", "RETURN_EVIDENCE_UNCONFIRMED"),
        ):
            if statuses.get(key) in {"PARTIAL", "UNKNOWN", "ERROR"}:
                reasons.append(code)
        if statuses.get("identity") == "NOT_CONFIRMED":
            reasons.append("IDENTITY_NOT_CONFIRMED")
        return list(dict.fromkeys(reasons))

    @staticmethod
    def _unavailable(reason="сначала сформируйте корректный отчёт о прибыли"):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_COMPLETENESS_UNAVAILABLE",
            "message": "Экран полноты недоступен: " + reason + ".",
            "actions": [],
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _iso_date(value):
        try:
            parsed = date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed.isoformat() == str(value) else None

    @staticmethod
    def _period(start, end):
        return start.strftime("%d.%m") + "–" + end.strftime("%d.%m.%Y")

    @staticmethod
    def _integer(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    @staticmethod
    def _number(value):
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if isfinite(number) else None

    @staticmethod
    def _money(value):
        return f"{value:,.2f} ₽".replace(",", " ")

    @staticmethod
    def _percent(value):
        return ("%.2f" % value).replace(".", ",") + "%"
