from math import isfinite
from contextvars import ContextVar

from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.seller_confirmed_product_identity_repository import (
    SellerConfirmedProductIdentityRepository,
)


class _RequestScopedProductProvider:
    """Keep selected-product scope in ContextVar instead of shared mutation."""

    def __init__(self, provider):
        self.provider = provider
        self.override = ContextVar(
            "period_profit_selected_product_" + str(id(self)),
            default=None,
        )

    def __call__(self):
        selected = self.override.get()
        if selected is not None:
            return [dict(selected)]
        return self.provider()


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

    def __init__(self, query_service, cost_service=None, identity_repository=None):
        self.query_service = query_service
        self.cost_service = cost_service
        self.identity_repository = identity_repository or (
            SellerConfirmedProductIdentityRepository(cost_service)
            if cost_service is not None else None
        )
        self._scoped_providers = self._install_request_scoped_providers()

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
        if parts and parts[0] == "period_profit_sku" and len(parts) in {5, 6}:
            return self._handle_identity_confirmation(parts, today=today)
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
                    ] + [{
                        "text": "📅 Указать период",
                        "callback": "period_profit_sku:" + sku + ":custom",
                    }],
                },
                "selected_sku": sku,
                "read_only": True,
                "executed": False,
            }
        period = self._text(parts[2]).upper()
        if period == "CUSTOM":
            return {
                "error": False,
                "status": "PERIOD_PROFIT_SKU_CUSTOM_PERIOD_START_REQUIRED",
                "selected_sku": sku,
                "read_only": True,
                "executed": False,
            }
        if period not in {code for _, code in self.PERIODS}:
            return self._error("PERIOD_PROFIT_SKU_PERIOD_INVALID")
        return self._calculate(identity, period, today=today)

    def handle_custom_period(self, sku, date_from, date_to, today=None):
        identity = self._selected_identity(self._text(sku))
        if isinstance(identity, dict) and identity.get("error") is True:
            return identity
        return self._calculate(
            identity,
            "CUSTOM",
            today=today,
            date_from=date_from,
            date_to=date_to,
        )

    def _calculate(self, identity, period, today=None, date_from=None, date_to=None):
        try:
            query_args = {"compare_previous": True, "today": today}
            if date_from is not None and date_to is not None:
                query_args.update(date_from=date_from, date_to=date_to)
            else:
                query_args["period_code"] = period
            result = self._query_selected_product(identity, **query_args)
        except Exception:
            return self._error("PERIOD_PROFIT_SKU_QUERY_FAILED")
        if not isinstance(result, dict) or type(result.get("error")) is not bool:
            return self._error("PERIOD_PROFIT_SKU_QUERY_INVALID")
        if result.get("error") is True:
            if result.get("code") == (
                "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_CONFIRMATION_REQUIRED"
            ):
                return self._present_identity_candidates(
                    identity,
                    period,
                    result.get("identity_candidates"),
                )
            return dict(result)
        summary = result.get("summary")
        selected = self._aggregate(summary, identity)
        if selected.get("error") is True:
            return selected
        evidence_error = self._validate_selected_finance_evidence(summary, selected)
        if evidence_error is not None:
            return evidence_error
        previous = None
        if isinstance(result.get("previous_summary"), dict):
            candidate = self._aggregate(result["previous_summary"], identity, allow_empty=True)
            if candidate.get("error") is True:
                return candidate
            previous = candidate
        presented = self._present(selected, identity, previous)
        return self._with_identity_revocation_buttons(
            presented, summary, identity, period
        )

    def _with_identity_revocation_buttons(
        self, response, summary, identity, period
    ):
        getter = getattr(self.identity_repository, "get_mapping", None)
        batch_getter = getattr(self.identity_repository, "get_mappings", None)
        products = summary.get("products") if isinstance(summary, dict) else None
        if (
            not callable(getter) and not callable(batch_getter)
        ) or not isinstance(products, list):
            return response
        observed_skus = sorted({
            self._text(row.get("sku"))
            for row in products
            if isinstance(row, dict)
            and self._text(row.get("sku"))
            and self._text(row.get("sku")) != identity["sku"]
        })
        mappings = None
        if callable(batch_getter):
            try:
                mappings = batch_getter(observed_skus)
            except Exception:
                mappings = None
        finance_skus = []
        for finance_sku in observed_skus:
            if isinstance(mappings, dict):
                mapping = mappings.get(finance_sku)
            elif callable(getter):
                try:
                    mapping = getter(finance_sku)
                except Exception:
                    mapping = None
            else:
                mapping = None
            if (
                isinstance(mapping, dict)
                and mapping.get("error") is False
                and mapping.get("mapping_confirmed") is True
                and self._text(mapping.get("current_sku")) == identity["sku"]
                and self._text(mapping.get("current_product_id"))
                == identity["product_id"]
            ):
                finance_skus.append(finance_sku)
        finance_skus = sorted(set(finance_skus))
        if not finance_skus:
            return response
        output = dict(response)
        output["keyboard"] = {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [{
                "text": "↩️ Отменить связь SKU " + finance_sku,
                "callback": ":".join((
                    "period_profit_sku", identity["sku"], period,
                    "unmap", finance_sku,
                )),
            } for finance_sku in finance_skus],
        }
        return output

    def _present_identity_candidates(self, identity, period, candidates):
        if not isinstance(candidates, list):
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_CANDIDATES_INVALID")
        buttons = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            finance_sku = self._text(candidate.get("finance_sku"))
            offer_id = self._text(candidate.get("historical_offer_id"))
            if not finance_sku:
                continue
            buttons.append({
                "text": (offer_id or "Старый товар") + " · SKU " + finance_sku,
                "callback": ":".join((
                    "period_profit_sku", identity["sku"], period,
                    "map", finance_sku,
                )),
            })
        if not buttons:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_CANDIDATES_EMPTY")
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_REQUIRED",
            "message": (
                "Ozon нашёл продажи под историческими SKU, но не подтвердил их связь "
                "с текущим SKU " + identity["sku"] + ". Выберите старый SKU только "
                "если уверены, что это тот же товар и вариант:"
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": buttons,
            },
            "read_only": True,
            "executed": False,
        }

    def _handle_identity_confirmation(self, parts, today=None):
        current_sku, period, action, finance_sku = (
            self._text(parts[1]), self._text(parts[2]).upper(),
            self._text(parts[3]), self._text(parts[4]),
        )
        if action not in {"map", "unmap"} or period not in {
            code for _, code in self.PERIODS
        }:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_CALLBACK_INVALID")
        identity = self._selected_identity(current_sku)
        if isinstance(identity, dict) and identity.get("error") is True:
            return identity
        if action == "unmap":
            return self._handle_identity_revocation(
                parts, identity, current_sku, period, finance_sku
            )
        if len(parts) == 5:
            return {
                "error": False,
                "status": "PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_PENDING",
                "message": (
                    "Подтвердите: исторический SKU " + finance_sku
                    + " и текущий SKU " + current_sku
                    + " — один и тот же товар и вариант?"
                ),
                "keyboard": {
                    "error": False,
                    "type": "inline_keyboard",
                    "buttons": [
                        {
                            "text": "✅ Да, это один товар",
                            "callback": ":".join(parts + ["confirm"]),
                        },
                        {
                            "text": "↩️ Отмена",
                            "callback": "period_profit_sku:" + current_sku + ":" + period,
                        },
                    ],
                },
                "read_only": True,
                "executed": False,
            }
        if parts[5] != "confirm" or self.identity_repository is None:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_INVALID")
        verification = self._query_selected_product(
            identity,
            period_code=period,
            compare_previous=True,
            today=today,
        )
        verified_candidates = (
            verification.get("identity_candidates")
            if isinstance(verification, dict)
            and verification.get("code") == (
                "PERIOD_PROFIT_SELECTED_SKU_IDENTITY_CONFIRMATION_REQUIRED"
            )
            else None
        )
        if not isinstance(verified_candidates, list) or finance_sku not in {
            self._text(candidate.get("finance_sku"))
            for candidate in verified_candidates
            if isinstance(candidate, dict)
        }:
            return self._error(
                "PERIOD_PROFIT_SKU_IDENTITY_CANDIDATE_NOT_VERIFIED"
            )
        try:
            recorded = self.identity_repository.record_mapping(
                finance_sku=finance_sku,
                current_product_id=identity["product_id"],
                current_sku=current_sku,
                current_offer_id=identity.get("offer_id"),
                source="SELLER_CONFIRMED_TELEGRAM_BUTTON",
            )
        except Exception:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_FAILED")
        if not isinstance(recorded, dict) or recorded.get("error") is True:
            return self._error(
                (recorded.get("code") if isinstance(recorded, dict) else None)
                or "PERIOD_PROFIT_SKU_IDENTITY_CONFIRMATION_FAILED"
            )
        calculated = self.handle_callback(
            "period_profit_sku:" + current_sku + ":" + period,
            today=today,
        )
        if (
            isinstance(calculated, dict)
            and calculated.get("error") is False
            and not calculated.get("keyboard")
        ):
            calculated = dict(calculated)
            calculated["keyboard"] = {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [{
                    "text": "↩️ Отменить связь SKU",
                    "callback": ":".join((
                        "period_profit_sku", current_sku, period,
                        "unmap", finance_sku,
                    )),
                }],
            }
        return calculated

    def _handle_identity_revocation(
        self, parts, identity, current_sku, period, finance_sku
    ):
        if self.identity_repository is None:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_INVALID")
        if len(parts) == 5:
            return {
                "error": False,
                "status": "PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_PENDING",
                "message": (
                    "Отменить связь исторического SKU " + finance_sku
                    + " с текущим SKU " + current_sku + "? Ранее полученный "
                    "расчёт по этой связи станет недействительным."
                ),
                "keyboard": {
                    "error": False,
                    "type": "inline_keyboard",
                    "buttons": [
                        {
                            "text": "✅ Да, отменить связь",
                            "callback": ":".join(parts + ["confirm"]),
                        },
                        {
                            "text": "↩️ Не отменять",
                            "callback": (
                                "period_profit_sku:" + current_sku + ":" + period
                            ),
                        },
                    ],
                },
                "read_only": True,
                "executed": False,
            }
        if parts[5] != "confirm":
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_INVALID")
        getter = getattr(self.identity_repository, "get_mapping", None)
        revoker = getattr(self.identity_repository, "revoke_mapping", None)
        if not callable(getter) or not callable(revoker):
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_INVALID")
        try:
            mapping = getter(finance_sku)
        except Exception:
            mapping = None
        if (
            not isinstance(mapping, dict)
            or mapping.get("error") is True
            or mapping.get("mapping_confirmed") is not True
            or self._text(mapping.get("current_sku")) != current_sku
            or self._text(mapping.get("current_product_id")) != identity["product_id"]
        ):
            return self._error(
                "PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_NOT_VERIFIED"
            )
        try:
            revoked = revoker(
                finance_sku=finance_sku,
                current_sku=current_sku,
                source="SELLER_REVOKED_TELEGRAM_BUTTON",
            )
        except Exception:
            revoked = None
        if not isinstance(revoked, dict) or revoked.get("error") is True:
            return self._error("PERIOD_PROFIT_SKU_IDENTITY_REVOCATION_FAILED")
        return {
            "error": False,
            "status": "PERIOD_PROFIT_SKU_IDENTITY_REVOKED",
            "message": (
                "Связь исторического SKU " + finance_sku + " с текущим SKU "
                + current_sku + " отменена. Она больше не используется. "
                "Предыдущий расчёт следует считать недействительным."
            ),
            "keyboard": {
                "error": False,
                "type": "inline_keyboard",
                "buttons": [{
                    "text": "🔄 Рассчитать заново",
                    "callback": "period_profit_sku:" + current_sku + ":" + period,
                }],
            },
            "read_only": True,
            "executed": True,
        }

    def _query_selected_product(self, identity, **kwargs):
        """Run Period Profit with the catalog scoped to the selected product.

        A SKU-specific request must not be blocked by missing seller cost or
        unresolved legacy identity for unrelated products in the same store.
        Temporarily narrow the query's product provider to the selected catalog
        identity while preserving the canonical finance, quantity, tax and
        return-processing pipeline.
        """
        if not self._scoped_providers:
            return self.query_service.query(**kwargs)

        selected = {
            "product_id": identity.get("product_id"),
            "offer_id": identity.get("offer_id"),
            "sku": identity.get("sku"),
            "_period_profit_selected_scope": True,
        }
        trace = current_period_profit_trace() or PeriodProfitOperationTrace(
            "selected_sku_profit"
        )
        trace.update(
            "selected_sku_query_start",
            service=type(self).__name__,
            method="_query_selected_product",
            catalog_sku=selected.get("sku"),
        )
        trace_token = activate_period_profit_trace(trace)
        provider_tokens = [
            provider.override.set(selected)
            for provider in self._scoped_providers
        ]
        try:
            return self.query_service.query(**kwargs)
        finally:
            for provider, token in zip(self._scoped_providers, provider_tokens):
                provider.override.reset(token)
            reset_period_profit_trace(trace_token)

    def _install_request_scoped_providers(self):
        providers = []
        current = self.query_service
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            provider = getattr(current, "product_provider", None)
            if callable(provider):
                if isinstance(provider, _RequestScopedProductProvider):
                    scoped = provider
                else:
                    scoped = _RequestScopedProductProvider(provider)
                    current.product_provider = scoped
                if scoped not in providers:
                    providers.append(scoped)
            current = getattr(current, "base_service", None)
        return providers

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

    def _validate_selected_finance_evidence(self, summary, selected):
        """Reject only an unproven all-zero selected-SKU result.

        Positive money or physical quantity is sufficient business evidence.
        Metadata counters are used only to distinguish a real scoped zero from
        a synthetic zero when the production pipeline provides them.
        """
        if not isinstance(summary, dict):
            return self._error("PERIOD_PROFIT_SKU_SUMMARY_INVALID")
        monetary_evidence = any(
            abs(float(selected.get(field) or 0.0)) > 0.000001
            for field in (
                "revenue", "net_accrual", "commission", "logistics",
                "acquiring", "other_fees",
            )
        )
        physical_evidence = int(selected.get("units_sold") or 0) > 0
        if monetary_evidence or physical_evidence:
            return None

        metadata_present = any(
            key in summary
            for key in (
                "finance_sku_count",
                "sale_quantity_record_count",
                "sale_quantity_reconciled",
            )
        )
        if not metadata_present:
            # Legacy/test query implementations may not expose evidence
            # metadata. They are protected by the upstream finance-scope
            # fail-closed gates when running the production chain.
            return None

        finance_count = self._integer(summary.get("finance_sku_count"))
        quantity_records = self._integer(summary.get("sale_quantity_record_count"))
        reconciled = summary.get("sale_quantity_reconciled") is True
        if (
            finance_count is not None
            and finance_count > 0
            and reconciled
            and quantity_records is not None
            and quantity_records == 0
        ):
            return self._error(
                "PERIOD_PROFIT_SELECTED_SKU_FINANCE_EVIDENCE_MISSING"
            )
        if finance_count == 0:
            return self._error(
                "PERIOD_PROFIT_SELECTED_SKU_FINANCE_EVIDENCE_MISSING"
            )
        return None

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
            "Выручка: " + self._money_with_revenue_share(
                row["revenue"], row["revenue"]
            ),
            "Начисления Ozon по SKU: " + self._money_with_revenue_share(
                row["net_accrual"], row["revenue"]
            ),
            "Комиссия: " + self._money_with_revenue_share(
                row["commission"], row["revenue"]
            ),
            "Логистика: " + self._money_with_revenue_share(
                row["logistics"], row["revenue"]
            ),
            "Эквайринг: " + self._money_with_revenue_share(
                row["acquiring"], row["revenue"]
            ),
            "Прочие SKU-расходы: " + self._money_with_revenue_share(
                row["other_fees"], row["revenue"]
            ),
            "Себестоимость: " + self._money_with_revenue_share(
                row["product_cost"], row["revenue"]
            ),
            "Налог: " + self._money_with_revenue_share(
                row["tax"], row["revenue"]
            ),
            "Прибыль: " + self._money_with_revenue_share(
                row["profit"], row["revenue"]
            ),
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

    @classmethod
    def _money_with_revenue_share(cls, value, revenue):
        money = cls._money(value)
        if not revenue:
            return money
        return money + " (" + cls._percent(float(value) / float(revenue) * 100.0) + ")"

    @staticmethod
    def _percent(value): return ("%.2f" % float(value)).rstrip("0").rstrip(".") + "%"

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "status": "PERIOD_PROFIT_SKU_UNAVAILABLE", "read_only": True, "executed": False}
