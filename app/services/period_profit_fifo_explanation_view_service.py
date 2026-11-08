"""Canonical screen/export view of Period Profit FIFO cost evidence."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


class PeriodProfitFifoExplanationViewService:
    """Project FIFO evidence once so Telegram and file exports share values."""

    _SKU_TEXT = re.compile(r"^[^\r\n\x00]{1,100}$")
    _BASIS_REF = re.compile(r"^fifo-basis-[0-9a-f]{20}$")
    _CORRECTION_REF = re.compile(r"^fifo-correction-[0-9a-f]{20}$")
    _CONFIRMATION_LABELS = {
        "OWNER_CONFIRMED": "подтверждено владельцем",
        "OZON_CONFIRMED_FIELD": "подтверждено полем Ozon",
        "DOCUMENT_RECONCILED": "сверено по документу",
    }
    _REASON_LABELS = {
        "FIFO_LAYER_EXPLANATION_INCOMPLETE": "неполные данные по слоям или их подтверждению",
        "FIFO_CORRECTION_HISTORY_UNAVAILABLE": "история корректировок недоступна",
        "FIFO_CORRECTION_HISTORY_INVALID": "история корректировок не прошла сверку",
        "FIFO_CORRECTION_PERIOD_NOT_ALIGNED": "корректировку нельзя точно сравнить с неполным месяцем",
        "FIFO_REPORT_TOTAL_MISMATCH": "сумма детализации не сходится с итогом себестоимости",
        "LEGACY_COST_SOURCE_INCOMPLETE": "датированная история себестоимости неполна",
        "PERIOD_COST_MODE_UNKNOWN": "режим расчёта себестоимости неизвестен",
        "PERIOD_PRODUCT_COST_DETAILS_UNAVAILABLE": "нет детализации себестоимости по товарам",
        "PERIOD_PRODUCT_ROW_INVALID": "строка товара не прошла проверку",
        "FIFO_CUTOFF_PARTITION_INCOMPLETE": "не удалось полностью сверить продажи до и после среза",
    }
    _SAFE_REASON_CODES = set(_REASON_LABELS)

    def build(self, summary):
        if not isinstance(summary, dict):
            return None
        rows = summary.get("products")
        if not isinstance(rows, list):
            return None
        products = []
        fifo_cost = Decimal("0.00")
        legacy_cost = Decimal("0.00")
        fifo_rows = 0
        legacy_rows = 0
        complete_fifo_rows = 0
        mixed_cutoff_rows = 0
        overall_complete = True
        reasons = []
        for row in rows:
            if not isinstance(row, dict):
                overall_complete = False
                reasons.append("PERIOD_PRODUCT_ROW_INVALID")
                continue
            sku = row.get("sku")
            units = row.get("units_sold")
            amount = self._money(row.get("product_cost"))
            if (
                not isinstance(sku, str) or not self._SKU_TEXT.fullmatch(sku)
                or type(units) is not int or units < 0 or amount is None
            ):
                overall_complete = False
                reasons.append("PERIOD_PRODUCT_ROW_INVALID")
                continue
            source = row.get("cost_source")
            if source == "FIFO_ALLOCATION_REVISION":
                fifo_rows += 1
                explanation = self._fifo_product(
                    row, sku=sku, units=units, amount=amount,
                )
                products.append(explanation)
                fifo_cost += amount
                if explanation["status"] == "CONFIRMED":
                    complete_fifo_rows += 1
                else:
                    overall_complete = False
                    reason_code = explanation.get("reason_code")
                    if reason_code in self._SAFE_REASON_CODES:
                        reasons.append(reason_code)
            elif source == "CUTOFF_PARTITIONED_FIFO_AND_LEGACY":
                projected = self._mixed_cutoff_product(row, sku=sku, units=units, amount=amount)
                products.append(projected)
                fifo_amount = self._money(projected.get("fifo_cogs_rub"))
                legacy_amount = self._money(projected.get("legacy_cogs_rub"))
                if fifo_amount is None or legacy_amount is None:
                    overall_complete = False
                    reasons.append("FIFO_REPORT_TOTAL_MISMATCH")
                else:
                    fifo_cost += fifo_amount
                    legacy_cost += legacy_amount
                if projected.get("fifo_units_sold", 0) > 0:
                    fifo_rows += 1
                    if projected.get("fifo_status") == "CONFIRMED":
                        complete_fifo_rows += 1
                    else:
                        overall_complete = False
                        reasons.append("FIFO_LAYER_EXPLANATION_INCOMPLETE")
                if projected.get("legacy_units_sold", 0) > 0:
                    legacy_rows += 1
                    if projected.get("legacy_status") != "CONFIRMED":
                        overall_complete = False
                        reasons.append("LEGACY_COST_SOURCE_INCOMPLETE")
                if projected.get("fifo_units_sold", 0) and projected.get("legacy_units_sold", 0):
                    mixed_cutoff_rows += 1
                if projected.get("status") != "CONFIRMED":
                    overall_complete = False
                    if projected.get("reason_code") in self._SAFE_REASON_CODES:
                        reasons.append(projected["reason_code"])
            elif source == "LEGACY_DATED_COST":
                legacy_rows += 1
                legacy_cost += amount
                products.append({
                    "sku": sku,
                    "cost_mode": "LEGACY_DATED_COST",
                    "status": "CONFIRMED" if summary.get("effective_cost_reconciled") is True else "UNKNOWN",
                    "reason_code": None if summary.get("effective_cost_reconciled") is True else "LEGACY_COST_SOURCE_INCOMPLETE",
                    "units_sold": units,
                    "product_cost_rub": format(amount, ".2f"),
                    "cutoff_date": None,
                    "stream_revision": None,
                    "allocation_revision": None,
                    "layers": [],
                    "corrections": {"status": "NOT_APPLICABLE", "reason_code": None, "revisions": []},
                })
                if summary.get("effective_cost_reconciled") is not True:
                    overall_complete = False
                    reasons.append("LEGACY_COST_SOURCE_INCOMPLETE")
            else:
                overall_complete = False
                reasons.append("PERIOD_COST_MODE_UNKNOWN")
                products.append({
                    "sku": sku,
                    "cost_mode": "UNKNOWN",
                    "status": "UNKNOWN",
                    "reason_code": "PERIOD_COST_MODE_UNKNOWN",
                    "units_sold": units,
                    "product_cost_rub": format(amount, ".2f"),
                    "cutoff_date": None,
                    "stream_revision": None,
                    "allocation_revision": None,
                    "layers": [],
                    "corrections": {"status": "UNKNOWN", "reason_code": "PERIOD_COST_MODE_UNKNOWN", "revisions": []},
                })

        fifo_cost = fifo_cost.quantize(Decimal("0.01"))
        legacy_cost = legacy_cost.quantize(Decimal("0.01"))
        expected_total = self._money(summary.get("product_cost"))
        displayed_total = (fifo_cost + legacy_cost).quantize(Decimal("0.01"))
        if expected_total is None or expected_total != displayed_total:
            overall_complete = False
            reasons.append("FIFO_REPORT_TOTAL_MISMATCH")
        mode = (
            "MIXED_CUTOFF" if mixed_cutoff_rows == 1 and fifo_rows == 1 and legacy_rows == 1
            else "MIXED" if fifo_rows and legacy_rows
            else "FIFO" if fifo_rows
            else "LEGACY_DATED_COST" if products
            else "UNKNOWN"
        )
        if not fifo_rows:
            status = "NOT_APPLICABLE" if products else "UNKNOWN"
            if not products:
                reasons.append("PERIOD_PRODUCT_COST_DETAILS_UNAVAILABLE")
        else:
            status = "CONFIRMED" if overall_complete else "PARTIAL"
        cutoff_dates = sorted({
            item["cutoff_date"] for item in products
            if item.get("cost_mode") in {"FIFO", "MIXED_CUTOFF"}
            and item.get("cutoff_date")
        })
        result = {
            "schema_version": 1,
            "cost_mode": mode,
            "status": status,
            "reason_codes": list(dict.fromkeys(reasons)),
            "total_cogs_rub": format(expected_total, ".2f") if expected_total is not None else None,
            "fifo_cogs_rub": format(fifo_cost, ".2f"),
            "legacy_cogs_rub": format(legacy_cost, ".2f"),
            "fifo_sku_count": fifo_rows,
            "confirmed_fifo_sku_count": complete_fifo_rows,
            "mixed_cutoff_sku_count": mixed_cutoff_rows,
            "cutoff_dates": cutoff_dates,
            "products": products,
            "read_only": True,
            "executed": False,
        }
        return result

    def sanitize_projection(self, value):
        """Rebuild an already projected object using the same allowlist as the screen."""
        if (
            not isinstance(value, dict) or value.get("schema_version") != 1
            or not isinstance(value.get("products"), list)
            or len(value["products"]) > 100_000
        ):
            return None
        products = []
        legacy_complete = True
        for item in value["products"]:
            if not isinstance(item, dict):
                return None
            mode = item.get("cost_mode")
            cost_source = (
                "FIFO_ALLOCATION_REVISION" if mode == "FIFO"
                else "LEGACY_DATED_COST" if mode == "LEGACY_DATED_COST"
                else "CUTOFF_PARTITIONED_FIFO_AND_LEGACY" if mode == "MIXED_CUTOFF"
                else None
            )
            if cost_source is None:
                return None
            if mode == "LEGACY_DATED_COST" and item.get("status") != "CONFIRMED":
                legacy_complete = False
            projected_row = {
                "sku": item.get("sku"),
                "cost_source": cost_source,
                "units_sold": item.get("units_sold"),
                "product_cost": item.get("product_cost_rub"),
                "fifo_cost_explanation": item if mode == "FIFO" else None,
            }
            if mode == "MIXED_CUTOFF":
                projected_row.update({
                    "fifo_units_sold": item.get("fifo_units_sold"),
                    "fifo_product_cost": item.get("fifo_cogs_rub"),
                    "legacy_cutoff_units_sold": item.get("legacy_units_sold"),
                    "legacy_cutoff_product_cost": item.get("legacy_cogs_rub"),
                    "legacy_cutoff_cost_reconciled": item.get("legacy_status") == "CONFIRMED",
                    "fifo_stream_revision": item.get("stream_revision"),
                    "fifo_allocation_revision": item.get("allocation_revision"),
                    "fifo_cutoff_date": item.get("cutoff_date"),
                    "fifo_cutoff_mapping_revision": item.get("cutoff_mapping_revision"),
                    "fifo_cutoff_bridge_fingerprint": item.get("cutoff_bridge_fingerprint"),
                    "fifo_cost_explanation": {
                        "cost_mode": "FIFO",
                        "status": item.get("fifo_status"),
                        "reason_code": item.get("reason_code"),
                        "cutoff_date": item.get("cutoff_date"),
                        "stream_revision": item.get("stream_revision"),
                        "allocation_revision": item.get("allocation_revision"),
                        "layers": item.get("layers"),
                        "corrections": item.get("corrections"),
                    },
                })
            products.append(projected_row)
        return self.build({
            "products": products,
            "product_cost": value.get("total_cogs_rub"),
            "effective_cost_reconciled": legacy_complete,
        })

    @classmethod
    def compact_lines(cls, explanation):
        if not isinstance(explanation, dict) or not explanation.get("fifo_sku_count"):
            return []
        status = "полнота подтверждена" if explanation.get("status") == "CONFIRMED" else "полнота неполная"
        cutoffs = explanation.get("cutoff_dates")
        cutoff_text = ", ".join(cutoffs) if isinstance(cutoffs, list) and cutoffs else "не подтверждён"
        line = (
            "FIFO-себестоимость: "
            + cls._count(explanation.get("fifo_sku_count"), "SKU")
            + ", " + cls._money_text(explanation.get("fifo_cogs_rub"))
            + "; " + status + "; cutoff " + cutoff_text + "."
        )
        if explanation.get("cost_mode") == "MIXED":
            if explanation.get("mixed_cutoff_sku_count"):
                line += " Для части SKU стоимость объединяет датированную историю до cutoff и FIFO после него."
            else:
                line += " Остальные SKU рассчитаны в датированном режиме."
        elif explanation.get("cost_mode") == "MIXED_CUTOFF":
            line += " Внутри SKU объединены датированная история до cutoff и FIFO после него."
        if explanation.get("status") != "CONFIRMED":
            reason = next(iter(explanation.get("reason_codes") or []), None)
            if reason:
                line += " Причина: " + cls._reason(reason) + "."
        return [line, "Слои и ревизии FIFO: кнопка «Подробнее»." ]

    @classmethod
    def detail_lines(cls, explanation):
        if not isinstance(explanation, dict):
            return []
        products = explanation.get("products")
        if not isinstance(products, list) or not products:
            return []
        lines = [
            "Себестоимость по режимам и слоям FIFO:",
            "Итог за период: " + cls._money_text(explanation.get("total_cogs_rub"))
            + "; FIFO: " + cls._money_text(explanation.get("fifo_cogs_rub"))
            + "; датированная история: " + cls._money_text(explanation.get("legacy_cogs_rub")) + ".",
        ]
        for product in products:
            if not isinstance(product, dict):
                continue
            sku = product.get("sku") if isinstance(product.get("sku"), str) else "SKU не определён"
            mode = product.get("cost_mode")
            lines.append(
                sku + ": " + str(mode)
                + "; " + cls._count(product.get("units_sold"), "шт.")
                + "; COGS " + cls._money_text(product.get("product_cost_rub"))
                + "; полнота " + str(product.get("status", "UNKNOWN")) + "."
            )
            if mode == "FIFO":
                lines.append(
                    "Cutoff " + str(product.get("cutoff_date") or "не подтверждён")
                    + "; stream rev " + cls._revision_text(product.get("stream_revision"))
                    + "; allocation rev " + cls._revision_text(product.get("allocation_revision")) + "."
                )
                layers = product.get("layers")
                if isinstance(layers, list) and layers:
                    for layer in layers:
                        if not isinstance(layer, dict):
                            continue
                        confirmation = cls._CONFIRMATION_LABELS.get(
                            layer.get("confirmation"), "подтверждение неизвестно",
                        )
                        lines.append(
                            "• " + str(layer.get("basis_kind", "слой"))
                            + " #" + cls._revision_text(layer.get("sequence"))
                            + " [" + str(layer.get("basis_ref", "ref недоступен")) + "]: "
                            + cls._count(layer.get("quantity"), "шт.") + " × "
                            + cls._money_text(layer.get("unit_cost_rub")) + " = "
                            + cls._money_text(layer.get("total_cogs_rub"))
                            + "; дата " + str(layer.get("effective_date") or "неизвестна")
                            + "; " + confirmation
                            + "; источник " + str(layer.get("source_method", "UNKNOWN"))
                            + "; статус источника " + str(layer.get("source_status", "UNKNOWN")) + "."
                        )
                elif product.get("units_sold") == 0:
                    lines.append("• В периоде нет продаж; распределённых слоёв нет.")
                else:
                    lines.append(
                        "⚠️ Разбивка по слоям неполная: "
                        + cls._reason(product.get("reason_code")) + "."
                    )
                lines.extend(cls._correction_lines(product.get("corrections")))
            elif mode == "LEGACY_DATED_COST":
                lines.append("Источник: действующий режим датированной истории, FIFO-слои не применяются.")
            elif mode == "MIXED_CUTOFF":
                lines.append(
                    "До cutoff: " + cls._count(product.get("legacy_units_sold"), "шт.")
                    + "; датированная себестоимость "
                    + cls._money_text(product.get("legacy_cogs_rub")) + "."
                )
                lines.append(
                    "После cutoff: " + cls._count(product.get("fifo_units_sold"), "шт.")
                    + "; FIFO-себестоимость "
                    + cls._money_text(product.get("fifo_cogs_rub")) + "."
                )
                lines.append(
                    "Cutoff " + str(product.get("cutoff_date") or "не подтверждён")
                    + "; stream rev " + cls._revision_text(product.get("stream_revision"))
                    + "; allocation rev " + cls._revision_text(product.get("allocation_revision"))
                    + "; mapping rev " + cls._revision_text(product.get("cutoff_mapping_revision")) + "."
                )
                layers = product.get("layers")
                if isinstance(layers, list):
                    for layer in layers:
                        if not isinstance(layer, dict):
                            continue
                        lines.append(
                            "• FIFO " + cls._count(layer.get("quantity"), "шт.")
                            + " × " + cls._money_text(layer.get("unit_cost_rub"))
                            + " = " + cls._money_text(layer.get("total_cogs_rub"))
                            + "; дата " + str(layer.get("effective_date") or "неизвестна") + "."
                        )
                if product.get("fifo_units_sold") == 0:
                    lines.append("• После cutoff продаж нет; FIFO-себестоимость не начислялась.")
                lines.extend(cls._correction_lines(product.get("corrections")))
            else:
                lines.append("⚠️ Режим себестоимости неизвестен; детализация не считается подтверждённой.")
            if product.get("status") not in {"CONFIRMED", "NOT_APPLICABLE"} and product.get("reason_code"):
                lines.append("⚠️ Причина неполноты: " + cls._reason(product["reason_code"]) + ".")
        return lines

    @classmethod
    def _correction_lines(cls, corrections):
        if not isinstance(corrections, dict):
            return ["Корректировки: история неизвестна."]
        status = corrections.get("status")
        if status == "NO_CORRECTION":
            return ["Корректировки: сохранённых изменений для периода нет."]
        if status in {"UNKNOWN", "UNAVAILABLE", "NOT_ALIGNED"}:
            return [
                "⚠️ Сравнение коррекции: "
                + cls._reason(corrections.get("reason_code")) + "."
            ]
        lines = []
        for correction in corrections.get("revisions", []):
            if not isinstance(correction, dict):
                continue
            version_label = (
                "текущий результат"
                if correction.get("status") == "CURRENT_RESULT"
                else "сохранённый исторический снимок; текущие данные могли измениться"
            )
            lines.append(
                "↻ Коррекция stream rev " + cls._revision_text(correction.get("correction_revision"))
                + " [" + str(correction.get("correction_ref")) + "] (" + version_label + "); "
                + "до allocation rev " + cls._revision_text(correction.get("previous_allocation_revision"))
                + ": COGS SKU " + cls._money_text(correction.get("before_sku_cogs_rub"))
                + " → " + cls._money_text(correction.get("after_sku_cogs_rub"))
                + " (Δ " + cls._money_text(correction.get("delta_cogs_rub")) + "); налог "
                + cls._money_text(correction.get("before_tax_rub"))
                + " → " + cls._money_text(correction.get("after_tax_rub"))
                + " (Δ " + cls._money_text(correction.get("delta_tax_rub")) + "); прибыль "
                + cls._money_text(correction.get("before_profit_rub"))
                + " → " + cls._money_text(correction.get("after_profit_rub"))
                + " (Δ " + cls._money_text(correction.get("delta_profit_rub")) + ")"
                + ". Предыдущий результат сохранён в записи коррекции."
            )
        return lines or ["Корректировка обнаружена, но её детализация недоступна."]

    @classmethod
    def _reason(cls, value):
        return cls._REASON_LABELS.get(value, "причина не подтверждена")

    @staticmethod
    def _revision_text(value):
        return str(value) if type(value) is int and value >= 0 else "неизвестна"

    @staticmethod
    def _count(value, suffix):
        return (f"{value:,}".replace(",", " ") + " " + suffix) if type(value) is int and value >= 0 else "количество неизвестно"

    @staticmethod
    def _money_text(value):
        amount = PeriodProfitFifoExplanationViewService._money(value, signed=True)
        if amount is None:
            return "сумма неизвестна"
        return f"{amount:,.2f}".replace(",", " ") + " ₽"

    def _fifo_product(self, row, *, sku, units, amount):
        raw = row.get("fifo_cost_explanation")
        explanation = raw if isinstance(raw, dict) else {}
        status = explanation.get("status")
        layers = explanation.get("layers")
        projected_layers = []
        total_units = 0
        total_amount = Decimal("0.00")
        complete = (
            status == "CONFIRMED"
            and explanation.get("cost_mode") == "FIFO"
            and isinstance(layers, list)
        )
        if isinstance(layers, list) and len(layers) <= 100_000:
            for layer in layers:
                if not isinstance(layer, dict):
                    complete = False
                    continue
                ref = layer.get("basis_ref")
                quantity = layer.get("quantity")
                unit_cost = self._money(layer.get("unit_cost_rub"))
                layer_amount = self._money(layer.get("total_cogs_rub"))
                date_value = layer.get("effective_date")
                if (
                    not isinstance(ref, str) or not self._BASIS_REF.fullmatch(ref)
                    or type(quantity) is not int or quantity <= 0
                    or unit_cost is None or layer_amount is None
                    or not self._iso_date(date_value)
                    or (unit_cost * quantity).quantize(Decimal("0.01")) != layer_amount
                ):
                    complete = False
                    continue
                confirmation = layer.get("confirmation")
                method = layer.get("source_method")
                source_status = layer.get("source_status")
                coverage = layer.get("coverage_status")
                if not (
                    confirmation in FifoConfirmationValues
                    and method in FifoSourceMethods
                    and source_status in {"COMPLETE", "OWNER_CONFIRMED"}
                    and coverage in {"COMPLETE", "OWNER_CONFIRMED"}
                ):
                    complete = False
                projected_layers.append({
                    "basis_ref": ref,
                    "basis_kind": layer.get("basis_kind") if layer.get("basis_kind") in {"FIFO_LAYER", "OPEN_RATE"} else "UNKNOWN",
                    "sequence": layer.get("sequence") if type(layer.get("sequence")) is int else None,
                    "effective_date": date_value,
                    "confirmation": confirmation if confirmation in FifoConfirmationValues else "UNKNOWN",
                    "source_method": method if method in FifoSourceMethods else "UNKNOWN",
                    "source_status": source_status if source_status in {"COMPLETE", "OWNER_CONFIRMED"} else "UNKNOWN",
                    "coverage_status": coverage if coverage in {"COMPLETE", "OWNER_CONFIRMED"} else "UNKNOWN",
                    "quantity": quantity,
                    "unit_cost_rub": format(unit_cost, ".2f"),
                    "total_cogs_rub": format(layer_amount, ".2f"),
                })
                total_units += quantity
                total_amount += layer_amount
        else:
            complete = False
        total_amount = total_amount.quantize(Decimal("0.01"))
        if total_units != units or total_amount != amount:
            complete = False
        corrections = self._corrections(explanation.get("corrections"))
        cutoff = explanation.get("cutoff_date")
        if not self._iso_date(cutoff):
            complete = False
            cutoff = None
        stream_revision = explanation.get("stream_revision")
        allocation_revision = explanation.get("allocation_revision")
        if type(stream_revision) is not int or stream_revision < 1:
            complete = False
            stream_revision = None
        if type(allocation_revision) is not int or allocation_revision < 0:
            complete = False
            allocation_revision = None
        return {
            "sku": sku,
            "cost_mode": "FIFO",
            "status": "CONFIRMED" if complete else "PARTIAL",
            "reason_code": (
                None if complete else
                explanation.get("reason_code")
                if explanation.get("reason_code") in self._SAFE_REASON_CODES
                else "FIFO_LAYER_EXPLANATION_INCOMPLETE"
            ),
            "units_sold": units,
            "product_cost_rub": format(amount, ".2f"),
            "cutoff_date": cutoff,
            "stream_revision": stream_revision,
            "allocation_revision": allocation_revision,
            "layers": projected_layers,
            "corrections": corrections,
        }

    def _mixed_cutoff_product(self, row, *, sku, units, amount):
        fifo_units = row.get("fifo_units_sold")
        legacy_units = row.get("legacy_cutoff_units_sold")
        fifo_amount = self._money(row.get("fifo_product_cost"))
        legacy_amount = self._money(row.get("legacy_cutoff_product_cost"))
        complete = (
            type(fifo_units) is int and fifo_units >= 0
            and type(legacy_units) is int and legacy_units >= 0
            and fifo_amount is not None and legacy_amount is not None
            and fifo_units + legacy_units == units
            and (fifo_amount + legacy_amount).quantize(Decimal("0.01")) == amount
        )
        cutoff = row.get("fifo_cutoff_date")
        stream_revision = row.get("fifo_stream_revision")
        allocation_revision = row.get("fifo_allocation_revision")
        mapping_revision = row.get("fifo_cutoff_mapping_revision")
        bridge_fingerprint = row.get("fifo_cutoff_bridge_fingerprint")
        if (
            not self._iso_date(cutoff)
            or type(stream_revision) is not int or stream_revision < 1
            or type(allocation_revision) is not int or allocation_revision < 0
        ):
            complete = False

        if fifo_units:
            fifo_row = dict(row)
            fifo_row["units_sold"] = fifo_units
            fifo_row["product_cost"] = format(fifo_amount, ".2f")
            fifo_projection = self._fifo_product(
                fifo_row, sku=sku, units=fifo_units, amount=fifo_amount,
            )
            if (
                fifo_projection.get("stream_revision") != stream_revision
                or fifo_projection.get("allocation_revision") != allocation_revision
                or fifo_projection.get("cutoff_date") != cutoff
            ):
                complete = False
            fifo_status = fifo_projection.get("status")
            layers = fifo_projection.get("layers") or []
            corrections = fifo_projection.get("corrections")
        else:
            if fifo_amount != Decimal("0.00"):
                complete = False
            fifo_status = "CONFIRMED"
            layers = []
            corrections = {"status": "NO_CORRECTION", "reason_code": None, "revisions": []}
        legacy_status = (
            "CONFIRMED"
            if row.get("legacy_cutoff_cost_reconciled") is True
            else "UNKNOWN"
        )
        if legacy_units and legacy_status != "CONFIRMED":
            complete = False
        mapping_fingerprint_valid = (
            isinstance(bridge_fingerprint, str)
            and len(bridge_fingerprint) == 64
            and all(char in "0123456789abcdef" for char in bridge_fingerprint)
        )
        if (legacy_units or fifo_units) and (
            type(mapping_revision) is not int or mapping_revision < 1
            or not mapping_fingerprint_valid
        ):
            complete = False
        status = (
            "CONFIRMED" if complete and fifo_status == "CONFIRMED"
            and legacy_status in {"CONFIRMED", "UNKNOWN"}
            else "PARTIAL"
        )
        return {
            "sku": sku,
            "cost_mode": "MIXED_CUTOFF",
            "status": status,
            "reason_code": None if status == "CONFIRMED" else "FIFO_CUTOFF_PARTITION_INCOMPLETE",
            "units_sold": units,
            "product_cost_rub": format(amount, ".2f"),
            "fifo_units_sold": fifo_units if type(fifo_units) is int else None,
            "fifo_cogs_rub": format(fifo_amount, ".2f") if fifo_amount is not None else None,
            "legacy_units_sold": legacy_units if type(legacy_units) is int else None,
            "legacy_cogs_rub": format(legacy_amount, ".2f") if legacy_amount is not None else None,
            "legacy_status": legacy_status,
            "fifo_status": fifo_status,
            "cutoff_date": cutoff if self._iso_date(cutoff) else None,
            "stream_revision": stream_revision if type(stream_revision) is int else None,
            "allocation_revision": allocation_revision if type(allocation_revision) is int else None,
            "cutoff_mapping_revision": mapping_revision if type(mapping_revision) is int else None,
            "cutoff_bridge_fingerprint": bridge_fingerprint if mapping_fingerprint_valid else None,
            "layers": layers,
            "corrections": corrections,
        }

    def _corrections(self, value):
        if not isinstance(value, dict):
            return {"status": "UNKNOWN", "reason_code": "FIFO_CORRECTION_HISTORY_INVALID", "revisions": []}
        status = value.get("status")
        allowed = {"AVAILABLE", "NO_CORRECTION", "NOT_ALIGNED", "UNAVAILABLE", "UNKNOWN"}
        rows = value.get("revisions")
        if status not in allowed or not isinstance(rows, list) or len(rows) > 200:
            return {"status": "UNKNOWN", "reason_code": "FIFO_CORRECTION_HISTORY_INVALID", "revisions": []}
        projected = []
        for row in rows:
            if not isinstance(row, dict):
                return {"status": "UNKNOWN", "reason_code": "FIFO_CORRECTION_HISTORY_INVALID", "revisions": []}
            ref = row.get("correction_ref")
            amounts = {
                key: self._money(
                    row.get(key),
                    signed=key in {
                        "delta_cogs_rub", "delta_tax_rub", "delta_profit_rub",
                        "before_profit_rub", "after_profit_rub",
                    },
                )
                for key in (
                    "before_sku_cogs_rub", "after_sku_cogs_rub", "delta_cogs_rub",
                    "before_total_cogs_rub", "after_total_cogs_rub",
                    "before_tax_rub", "after_tax_rub", "delta_tax_rub",
                    "before_profit_rub", "after_profit_rub", "delta_profit_rub",
                )
            }
            if (
                not isinstance(ref, str) or not self._CORRECTION_REF.fullmatch(ref)
                or type(row.get("correction_revision")) is not int
                or row.get("correction_revision") < 1
                or type(row.get("previous_allocation_revision")) is not int
                or row.get("previous_allocation_revision") < 0
                or not self._iso_month(row.get("period"))
                or row.get("status") not in {"CURRENT_RESULT", "HISTORICAL_SNAPSHOT"}
                or any(amount is None for amount in amounts.values())
                or amounts["after_sku_cogs_rub"] - amounts["before_sku_cogs_rub"] != amounts["delta_cogs_rub"]
                or amounts["after_total_cogs_rub"] - amounts["before_total_cogs_rub"] != amounts["delta_cogs_rub"]
                or amounts["after_tax_rub"] - amounts["before_tax_rub"] != amounts["delta_tax_rub"]
                or amounts["after_profit_rub"] - amounts["before_profit_rub"] != amounts["delta_profit_rub"]
            ):
                return {"status": "UNKNOWN", "reason_code": "FIFO_CORRECTION_HISTORY_INVALID", "revisions": []}
            projected.append({
                "correction_ref": ref,
                "correction_revision": row["correction_revision"],
                "previous_allocation_revision": row["previous_allocation_revision"],
                "period": row["period"],
                "status": row["status"],
                **{key: format(amount, ".2f") for key, amount in amounts.items()},
            })
        return {
            "status": status,
            "reason_code": value.get("reason_code") if value.get("reason_code") in self._SAFE_REASON_CODES else None,
            "revisions": projected,
        }

    @staticmethod
    def _money(value, *, signed=False):
        if value is None or isinstance(value, bool):
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            return None
        if not amount.is_finite() or not signed and amount < 0:
            return None
        normalized = amount.quantize(Decimal("0.01"))
        return normalized if normalized == amount else None

    @staticmethod
    def _iso_date(value):
        if not isinstance(value, str):
            return False
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False

    @classmethod
    def _iso_month(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
            return False
        try:
            year, month = (int(part) for part in value.split("-"))
            return 1 <= month <= 12 and year >= 1
        except (TypeError, ValueError):
            return False


FifoConfirmationValues = {"OWNER_CONFIRMED", "OZON_CONFIRMED_FIELD", "DOCUMENT_RECONCILED"}
FifoSourceMethods = {
    "OWNER_CONFIRMED_FIFO_CUTOFF", "OWNER_CONFIRMED_NEW_COST_RATE",
    "OWNER_CONFIRMED_TEST_RECEIPT", "OZON_REALIZATION_REPORT",
}
