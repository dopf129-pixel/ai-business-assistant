from math import isfinite


class PeriodProfitSkuRuntimeService:
    """Present SKU-attributed rows produced by the canonical Period Profit query."""

    PERIODS = (
        ("Сегодня", "TODAY"),
        ("7 дней", "7D"),
        ("28 дней", "28D"),
        ("56 дней", "56D"),
        ("90 дней", "90D"),
    )
    AMOUNTS = (
        "revenue", "net_accrual", "commission", "logistics",
        "acquiring", "other_fees", "product_cost", "tax", "profit",
    )

    def __init__(self, query_service, cost_service=None):
        self.query_service = query_service
        self.cost_service = cost_service

    def open_sku_menu(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        configured = self._configured_skus()
        if configured is not None:
            products = [product for product in products if product["sku"] in configured]
            if not products:
                return {
                    "error": False,
                    "message": "Сначала укажите себестоимость хотя бы для одного SKU.",
                    "keyboard": {"error": False, "type": "inline_keyboard", "buttons": [{"text": "💰 Указать себестоимость", "callback": "seller_cost"}]},
                    "read_only": True,
                    "executed": False,
                }
        buttons = []
        for product in products:
            label = product["offer_id"] or product["sku"]
            buttons.append({
                "text": label + " · SKU " + product["sku"],
                "callback": "period_profit_sku:" + product["sku"],
            })
        return {
            "error": False,
            "message": "Выберите товар, по которому хотите посмотреть прибыль:",
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": buttons},
            "read_only": True,
            "executed": False,
        }

    def handle_callback(self, callback, today=None):
        parts = str(callback or "").strip().split(":")
        if len(parts) not in {2, 3} or parts[0] != "period_profit_sku":
            return self._error("PERIOD_PROFIT_SKU_CALLBACK_INVALID")
        sku = self._text(parts[1])
        identity = self._selected_identity(sku)
        if isinstance(identity, dict) and identity.get("error") is True:
            return identity
        if len(parts) == 2:
            return {
                "error": False,
                "message": "За какой период показать прибыль по SKU " + sku + "?",
                "keyboard": {
                    "error": False,
                    "type": "inline_keyboard",
                    "buttons": [
                        {"text": label, "callback": "period_profit_sku:" + sku + ":" + code}
                        for label, code in self.PERIODS
                    ],
                },
                "selected_sku": sku,
                "read_only": True,
                "executed": False,
            }
        period = self._text(parts[2]).upper()
        if period not in {code for _, code in self.PERIODS}:
            return self._error("PERIOD_PROFIT_SKU_PERIOD_INVALID")
        try:
            result = self._query_selected_product(
                identity,
                period_code=period,
                compare_previous=True,
                today=today,
            )
        except Exception:
            return self._error("PERIOD_PROFIT_SKU_QUERY_FAILED")
        if not isinstance(result, dict) or type(result.get("error")) is not bool:
            return self._error("PERIOD_PROFIT_SKU_QUERY_INVALID")
        if result.get("error") is True:
            return dict(result)
        selected = self._aggregate(result.get("summary"), identity)
        if selected.get("error") is True:
            return selected
        previous = None
        if isinstance(result.get("previous_summary"), dict):
            candidate = self._aggregate(result["previous_summary"], identity, allow_empty=True)
            if candidate.get("error") is True:
                return candidate
            previous = candidate
        return self._present(selected, identity, previous)

    def _query_selected_product(self, identity, **kwargs):
        """Run Period Profit with the catalog scoped to the selected product.

        A SKU-specific request must not be blocked by missing seller cost or
        unresolved legacy identity for unrelated products in the same store.
        Temporarily narrow the query's product provider to the selected catalog
        identity while preserving the canonical finance, quantity, tax and
        return-processing pipeline.
        """
        services = []
        current = self.query_service
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if hasattr(current, "product_provider"):
                services.append(current)
            current = getattr(current, "base_service", None)

        if not services:
            return self.query_service.query(**kwargs)

        selected = {
            "product_id": identity.get("product_id"),
            "offer_id": identity.get("offer_id"),
            "sku": identity.get("sku"),
        }
        originals = [(service, service.product_provider) for service in services]
        provider = lambda: [dict(selected)]
        try:
            for service, _original in originals:
                service.product_provider = provider
            return self.query_service.query(**kwargs)
        finally:
            for service, original in originals:
                service.product_provider = original

    def _products(self):
        provider = getattr(self.query_service, "product_provider", None)
        if not callable(provider):
            return self._error("PERIOD_PROFIT_SKU_CATALOG_UNAVAILABLE")
        try:
            rows = provider()
        except Exception:
            return self._error("PERIOD_PROFIT_SKU_CATALOG_UNAVAILABLE")
        if not isinstance(rows, list):
            return self._error("PERIOD_PROFIT_SKU_CATALOG_INVALID")
        products, seen = [], set()
        for row in rows:
            product = self._product(row)
            if product is None or product["sku"] in seen:
                return self._error("PERIOD_PROFIT_SKU_CATALOG_AMBIGUOUS")
            seen.add(product["sku"])
            products.append(product)
        if not products:
            return self._error("PERIOD_PROFIT_SKU_CATALOG_EMPTY")
        return sorted(products, key=lambda item: (item["offer_id"] or item["sku"], item["sku"]))

    def _configured_skus(self):
        if self.cost_service is None:
            return None
        getter = getattr(self.cost_service, "get_all_costs", None)
        if not callable(getter):
            return None
        try:
            rows = getter()
        except Exception:
            return None
        if not isinstance(rows, list):
            return None
        configured = set()
        for row in rows:
            if isinstance(row, dict):
                sku = self._text(row.get("sku"))
            elif isinstance(row, (tuple, list)) and len(row) >= 2:
                sku = self._text(row[1])
            else:
                continue
            if sku:
                configured.add(sku)
        return configured

    def _selected_identity(self, sku):
        if not sku:
            return self._error("PERIOD_PROFIT_SKU_INVALID")
        products = self._products()
        if isinstance(products, dict):
            return products
        matches = [row for row in products if row["sku"] == sku]
        if len(matches) != 1:
            return self._error("PERIOD_PROFIT_SKU_NOT_FOUND")
        return matches[0]

    def _aggregate(self, summary, identity, allow_empty=False):
        if not isinstance(summary, dict) or not isinstance(summary.get("products"), list):
            return self._error("PERIOD_PROFIT_SKU_SUMMARY_INVALID")
        rows = []
        for row in summary["products"]:
            if not isinstance(row, dict):
                return self._error("PERIOD_PROFIT_SKU_SUMMARY_INVALID")
            product_id = self._text(row.get("product_id"))
            catalog_sku = self._text(row.get("catalog_sku"))
            finance_sku = self._text(row.get("sku"))
            references_selected = (
                product_id == identity["product_id"]
                or catalog_sku == identity["sku"]
                or finance_sku == identity["sku"]
            )
            if references_selected:
                if product_id and product_id != identity["product_id"]:
                    return self._error("PERIOD_PROFIT_SKU_IDENTITY_CONFLICT")
                rows.append(row)
        if not rows:
            if allow_empty:
                return {field: 0.0 for field in self.AMOUNTS} | {"units_sold": 0}
            return self._error("PERIOD_PROFIT_SKU_FINANCE_MISSING")
        output = {field: 0.0 for field in self.AMOUNTS}
        output["units_sold"] = 0
        for row in rows:
            for field in self.AMOUNTS:
                value = self._number(row.get(field))
                if value is None:
                    return self._error("PERIOD_PROFIT_SKU_AMOUNT_INVALID")
                output[field] += value
                if not isfinite(output[field]):
                    return self._error("PERIOD_PROFIT_SKU_AMOUNT_INVALID")
            units = self._integer(row.get("units_sold"))
            if units is None:
                return self._error("PERIOD_PROFIT_SKU_QUANTITY_INVALID")
            output["units_sold"] += units
        cost_override = self._seller_cost_total(identity, summary, output["units_sold"])
        if isinstance(cost_override, dict) and cost_override.get("error") is True:
            return cost_override
        if cost_override is not None:
            output["product_cost"] = cost_override
        tax = self._tax(summary, output["revenue"], output["net_accrual"] - output["product_cost"])
        if tax is None:
            return self._error("PERIOD_PROFIT_SKU_TAX_UNAVAILABLE")
        output["tax"] = tax
        output["profit"] = output["net_accrual"] - output["product_cost"] - tax
        output = {key: round(value, 2) if key != "units_sold" else value for key, value in output.items()}
        output["margin_percent"] = round(output["profit"] / output["revenue"] * 100, 2) if output["revenue"] else 0.0
        output["date_from"] = summary.get("date_from")
        output["date_to"] = summary.get("date_to")
        return output

    def _seller_cost_total(self, identity, summary, units_sold):
        if self.cost_service is None:
            return None
        getter = getattr(self.cost_service, "get_effective_cost_evidence", None)
        if not callable(getter):
            return None
        at_date = summary.get("date_to") if isinstance(summary, dict) else None
        if not at_date:
            return None
        try:
            evidence = getter(
                at_date=at_date,
                product_id=identity.get("product_id"),
                sku=identity.get("sku"),
                offer_id=identity.get("offer_id"),
            )
        except Exception:
            return self._error("PERIOD_PROFIT_SKU_COST_LOOKUP_FAILED")
        if not isinstance(evidence, dict):
            return self._error("PERIOD_PROFIT_SKU_COST_LOOKUP_INVALID")
        if evidence.get("error") is True or evidence.get("effective_cost_confirmed") is not True:
            return self._error(evidence.get("code") or "PERIOD_PROFIT_SKU_COST_MISSING")
        unit_cost = self._number(evidence.get("cost_price"))
        if unit_cost is None:
            return self._error("PERIOD_PROFIT_SKU_COST_INVALID")
        return round(unit_cost * units_sold, 2)

    def _tax(self, summary, revenue, pre_tax_profit):
        mode = self._text(summary.get("tax_mode")).upper()
        rate = self._number(summary.get("tax_rate_percent"))
        minimum_rate = self._number(summary.get("minimum_tax_rate_percent"))
        if mode == "NONE":
            return 0.0
        if mode == "USN_INCOME" and rate is not None:
            return revenue * rate / 100.0
        if mode == "USN_INCOME_MINUS_EXPENSES" and rate is not None and minimum_rate is not None:
            regular = max(pre_tax_profit, 0.0) * rate / 100.0
            minimum = revenue * minimum_rate / 100.0
            return max(regular, minimum)
        return None

    def _present(self, row, identity, previous):
        lines = [
            "💰 Прибыль по товару", identity["offer_id"] or identity["sku"],
            "SKU: " + identity["sku"],
            "Период: " + str(row.get("date_from")) + " — " + str(row.get("date_to")), "",
            "Продано: " + str(row["units_sold"]),
            "Выручка: " + self._money(row["revenue"]),
            "Начисления Ozon по SKU: " + self._money(row["net_accrual"]),
            "Комиссия: " + self._money(row["commission"]),
            "Логистика: " + self._money(row["logistics"]),
            "Эквайринг: " + self._money(row["acquiring"]),
            "Прочие SKU-расходы: " + self._money(row["other_fees"]),
            "Себестоимость: " + self._money(row["product_cost"]),
            "Налог: " + self._money(row["tax"]),
            "Прибыль: " + self._money(row["profit"]),
            "Маржа: " + self._percent(row["margin_percent"]),
        ]
        if previous is not None:
            delta = round(row["profit"] - previous["profit"], 2)
            lines.append("К прошлому периоду: " + ("+" if delta > 0 else "") + self._money(delta))
        lines.extend(["", "⚠️ Неатрибутированные расходы кабинета, внешние расходы и Return COGS в прибыль этого SKU не включены и не считаются нулём."])
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SKU_READY",
            "text": "\n".join(lines),
            "summary": row,
            "selected_sku": identity["sku"],
            "account_level_expenses_included": False,
            "external_expenses_included": False,
            "return_cogs_included": False,
            "coverage_complete": False,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _product(cls, row):
        if isinstance(row, dict):
            product_id, offer_id, sku = row.get("product_id"), row.get("offer_id"), row.get("sku")
        elif isinstance(row, (tuple, list)) and len(row) >= 3:
            product_id, offer_id, sku = row[:3]
        else:
            return None
        product_id, offer_id, sku = cls._text(product_id), cls._text(offer_id), cls._text(sku)
        return {"product_id": product_id, "offer_id": offer_id, "sku": sku} if product_id and sku else None

    @staticmethod
    def _text(value): return "" if value is None else str(value).strip()

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool): return None
        try: number = float(value)
        except (TypeError, ValueError, OverflowError): return None
        return number if isfinite(number) else None

    @staticmethod
    def _integer(value):
        if value is None or isinstance(value, bool): return None
        try: number = int(value)
        except (TypeError, ValueError, OverflowError): return None
        return number if number >= 0 else None

    @staticmethod
    def _money(value): return ("%.2f" % float(value)).rstrip("0").rstrip(".") + " ₽"

    @staticmethod
    def _percent(value): return ("%.2f" % float(value)).rstrip("0").rstrip(".") + "%"

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "status": "PERIOD_PROFIT_SKU_UNAVAILABLE", "read_only": True, "executed": False}
