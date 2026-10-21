"""Compare two immutable saved planning revisions without external reads."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation

from services.planning_cross_docking_adapter import PlanningCrossDockingAdapter


class PlanningPlanComparisonService:
    INPUT_FIELDS = (
        ("price", "Цена продавца"),
        ("cost", "Себестоимость"),
        ("advertising_rate", "Реклама, %"),
        ("discount_points_rate", "Баллы за скидки, %"),
        ("commission_rate", "Комиссия, %"),
        ("logistics_per_unit", "Логистика на единицу"),
        ("last_mile_per_unit", "Последняя миля на единицу"),
        ("acquiring_per_unit", "Эквайринг на единицу"),
        ("tax_mode", "Налоговый режим"),
        ("tax_rate", "Ставка налога, %"),
        ("minimum_tax_rate", "Минимальная ставка, %"),
        ("cross_docking_per_unit", "Кросс-докинг на поставленную единицу"),
    )
    METRICS = ("revenue", "profit", "margin_percent")

    def __init__(self, sales_mix_planning_service):
        self.sales_mix_planning_service = sales_mix_planning_service

    def compare(self, first_result, second_result):
        first = self._document(first_result)
        second = self._document(second_result)
        if first is None or second is None:
            return self._error("PLANNING_COMPARISON_DOCUMENT_INVALID")
        if (first.get("owner_id") != second.get("owner_id")
                or first.get("store_id") != second.get("store_id")):
            return self._error("PLANNING_COMPARISON_SCOPE_MISMATCH")
        a = first.get("payload") or {}
        b = second.get("payload") or {}
        prerequisite_reason = None
        if a.get("plan_kind") != b.get("plan_kind"):
            prerequisite_reason = "PLAN_KIND_MISMATCH"
        elif a.get("calculation_version") != b.get("calculation_version"):
            prerequisite_reason = "CALCULATION_VERSION_MISMATCH"
        else:
            scenario_service = getattr(self.sales_mix_planning_service, "scenario_service", None)
            current_version = getattr(scenario_service, "VERSION", None)
            if not PlanningCrossDockingAdapter.supports(a, current_version):
                prerequisite_reason = "CALCULATION_VERSION_UNSUPPORTED"
        first_rows = self._identity_map(a.get("items"))
        second_rows = self._identity_map(b.get("items"))
        if first_rows is None or second_rows is None:
            return self._not_comparable("IDENTITY_INVALID_OR_AMBIGUOUS", first, second)
        exact_scope = set(first_rows) == set(second_rows)
        scope_reason = None if exact_scope else "PRODUCT_SCOPE_MISMATCH"
        comparison_reason = prerequisite_reason or scope_reason

        rows = []
        for key in sorted(set(first_rows) | set(second_rows)):
            left, right = first_rows.get(key), second_rows.get(key)
            if left is None or right is None:
                item = right or left
                rows.append({
                    "identity": deepcopy(item.get("identity") or {}),
                    "scope_status": "ADDED_IN_SECOND" if left is None else "REMOVED_FROM_SECOND",
                    "changes": [],
                })
                continue
            left_inputs = left.get("inputs") if isinstance(left.get("inputs"), dict) else {}
            right_inputs = right.get("inputs") if isinstance(right.get("inputs"), dict) else {}
            changes = []
            for field, label in self.INPUT_FIELDS:
                before, after = left_inputs.get(field), right_inputs.get(field)
                if before != after:
                    changes.append({
                        "field": field, "label": label,
                        "before": before, "after": after,
                        "delta": self._delta(after, before),
                        "unit": (
                            "pp" if field.endswith("_rate")
                            else "policy" if field == "tax_mode"
                            else "RUB/supplied_unit" if field == "cross_docking_per_unit"
                            else "RUB"
                        ),
                    })
            left_quantity = self._quantity(a.get("sales_mix"), left)
            right_quantity = self._quantity(b.get("sales_mix"), right)
            if left_quantity != right_quantity:
                changes.append({
                    "field": "successful_quantity", "label": "Успешные продажи",
                    "before": left_quantity, "after": right_quantity,
                    "delta": self._delta(right_quantity, left_quantity), "unit": "шт.",
                })
            rows.append({
                "identity": deepcopy(left.get("identity") or {}),
                "changes": changes,
                **({
                    "cross_docking_source_before": deepcopy(
                        (left.get("sources") or {}).get("cross_docking")
                    ),
                    "cross_docking_source_after": deepcopy(
                        (right.get("sources") or {}).get("cross_docking")
                    ),
                } if PlanningCrossDockingAdapter.is_current(a) else {}),
            })

        first_mix = self._project_mix(a) if comparison_reason is None else None
        second_mix = self._project_mix(b) if comparison_reason is None else None
        if comparison_reason is None:
            compatible, reason = self._mix_compatibility(a, b, first_mix, second_mix)
        else:
            compatible, reason = False, comparison_reason
        metrics = {}
        if compatible:
            for name in self.METRICS:
                if name == "revenue":
                    old_value = (first_mix.get("components") or {}).get("revenue")
                    new_value = (second_mix.get("components") or {}).get("revenue")
                else:
                    old_value = first_mix.get(name)
                    new_value = second_mix.get(name)
                old = self._decimal(old_value)
                new = self._decimal(new_value)
                if old is None or new is None:
                    metrics[name] = {"status": "UNAVAILABLE", "before": None, "after": None, "delta": None}
                    continue
                metrics[name] = {
                    "status": "COMPARABLE", "before": self._money(old),
                    "after": self._money(new), "delta": self._money(new - old),
                    "unit": "pp" if name == "margin_percent" else "RUB",
                }
        else:
            metrics = {name: {
                "status": "NOT_COMPARABLE", "before": None, "after": None,
                "delta": None, "reason": reason,
            } for name in self.METRICS}

        return {
            "error": False,
            "comparison_version": 1,
            "status": "COMPARABLE" if compatible else "NOT_COMPARABLE" if comparison_reason else "INPUTS_ONLY",
            "reason": None if compatible else reason,
            "first": self._document_reference(first),
            "second": self._document_reference(second),
            "scope": {
                "status": "EXACT_IDENTITY_SET" if exact_scope else "IDENTITY_SCOPE_MISMATCH",
                "row_count": len(rows),
                "first_only": len(set(first_rows) - set(second_rows)),
                "second_only": len(set(second_rows) - set(first_rows)),
            },
            "period": {
                "first": (a.get("sales_mix") or {}).get("period_label"),
                "second": (b.get("sales_mix") or {}).get("period_label"),
                "same": self._same_period(a, b),
            },
            "input_changes": rows,
            "metrics": metrics,
            "expense_changes": self._expense_changes(a.get("sales_mix"), b.get("sales_mix")),
            "changed_dimensions": self._changed_dimensions(a, b, rows),
            "historical": True,
            "recalculated_from_saved_inputs": compatible,
            "external_reads": 0,
            "read_only": True,
            "executed": False,
        }

    def _project_mix(self, payload):
        mix = payload.get("sales_mix")
        items = payload.get("items")
        if (not isinstance(mix, dict) or not isinstance(items, list)
                or self.sales_mix_planning_service is None):
            return None
        if mix.get("confirmed") is not True:
            return None
        result = self.sales_mix_planning_service.calculate(
            PlanningCrossDockingAdapter.items_for_sales_mix(payload), quantities=mix.get("quantities"),
            period_label=mix.get("period_label"), expenses=mix.get("expenses"),
            expenses_confirmed=True,
            include_cross_docking=PlanningCrossDockingAdapter.is_current(payload),
        )
        return result if isinstance(result, dict) and result.get("error") is False else None

    def _mix_compatibility(self, first_payload, second_payload, first_mix, second_mix):
        if first_mix is None or second_mix is None:
            return False, "CONFIRMED_SALES_MIX_REQUIRED"
        if not self._same_period(first_payload, second_payload):
            return False, "PERIOD_MISMATCH"
        if first_mix.get("coverage_complete") is not True or second_mix.get("coverage_complete") is not True:
            return False, "INCOMPLETE_SALES_MIX"
        policies_a = self._tax_policies(first_payload.get("items"))
        policies_b = self._tax_policies(second_payload.get("items"))
        if policies_a is None or policies_b is None or policies_a != policies_b:
            return False, "TAX_POLICY_MISMATCH_OR_UNKNOWN"
        if (not (first_mix.get("components") or {}).get("revenue")
                or not (second_mix.get("components") or {}).get("revenue")
                or any(first_mix.get(key) is None or second_mix.get(key) is None
                       for key in ("profit", "margin_percent"))):
            return False, "RESULT_METRIC_UNAVAILABLE"
        return True, None

    @classmethod
    def _same_period(cls, first, second):
        a = first.get("sales_mix") if isinstance(first, dict) else None
        b = second.get("sales_mix") if isinstance(second, dict) else None
        return (isinstance(a, dict) and isinstance(b, dict)
                and a.get("period_label") == b.get("period_label"))

    @staticmethod
    def _identity_map(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            return None
        output = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("identity"), dict):
                return None
            identity = item["identity"]
            key = tuple(str(identity.get(field) or "").strip()
                        for field in ("product_id", "offer_id", "sku"))
            if not all(key) or key in output:
                return None
            output[key] = item
        return output

    @staticmethod
    def _quantity(sales_mix, item):
        if not isinstance(sales_mix, dict):
            return None
        row_id = str(item.get("row_id") or (item.get("identity") or {}).get("sku") or "")
        quantities = sales_mix.get("quantities")
        return quantities.get(row_id) if isinstance(quantities, dict) else None

    @staticmethod
    def _tax_policies(items):
        if not isinstance(items, list):
            return None
        policies = []
        for item in items:
            inputs = item.get("inputs") if isinstance(item, dict) else None
            if not isinstance(inputs, dict):
                return None
            mode = inputs.get("tax_mode")
            if not mode:
                return None
            policies.append((str(mode), str(inputs.get("tax_rate")), str(inputs.get("minimum_tax_rate"))))
        return tuple(sorted(policies))

    @classmethod
    def _expense_changes(cls, first, second):
        def totals(mix):
            output = {}
            for expense in (mix or {}).get("expenses") or []:
                if isinstance(expense, dict):
                    key = " ".join(str(expense.get("name") or "").split())
                    value = cls._decimal(expense.get("amount"))
                    if key and value is not None:
                        output[key] = output.get(key, Decimal("0")) + value
            return output
        left, right = totals(first), totals(second)
        changes = []
        for name in sorted(set(left) | set(right)):
            before = left.get(name, Decimal("0"))
            after = right.get(name, Decimal("0"))
            if before == after:
                continue
            changes.append({
                "name": name,
                "before": cls._money(before),
                "after": cls._money(after),
                "delta": cls._money(after - before),
            })
        return changes

    @staticmethod
    def _changed_dimensions(first, second, rows):
        left, right = first.get("sales_mix"), second.get("sales_mix")
        left_period = left.get("period_label") if isinstance(left, dict) else None
        right_period = right.get("period_label") if isinstance(right, dict) else None
        changed = []
        if left_period != right_period:
            changed.append("period")
        changed_fields = {
            change.get("field") for row in rows for change in row.get("changes", [])
        }
        if "price" in changed_fields:
            changed.append("price")
        if "successful_quantity" in changed_fields:
            changed.append("volume")
        if changed_fields - {"price", "successful_quantity"}:
            changed.append("assumptions")
        if PlanningPlanComparisonService._expense_changes(left, right):
            changed.append("fixed_expenses")
        return changed

    @staticmethod
    def _document(result):
        if not isinstance(result, dict) or result.get("error") is True:
            return None
        document = result.get("document")
        if not isinstance(document, dict) or not isinstance(document.get("payload"), dict):
            return None
        return document

    @staticmethod
    def _document_reference(document):
        payload = document.get("payload") or {}
        return {
            "document_id": document.get("document_id"),
            "title": document.get("title"),
            "revision": document.get("revision"),
            "calculation_version": payload.get("calculation_version"),
            "plan_kind": payload.get("plan_kind"),
            "freshness": "HISTORICAL_ASSUMPTIONS",
        }

    @staticmethod
    def _delta(after, before):
        left, right = PlanningPlanComparisonService._decimal(before), PlanningPlanComparisonService._decimal(after)
        return PlanningPlanComparisonService._money(right - left) if left is not None and right is not None else None

    @staticmethod
    def _decimal(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            parsed = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _money(value):
        return format(value.quantize(Decimal("0.01")), ".2f")

    @staticmethod
    def _not_comparable(reason, first, second):
        return {
            "error": False, "comparison_version": 1, "status": "NOT_COMPARABLE",
            "reason": reason,
            "first": PlanningPlanComparisonService._document_reference(first),
            "second": PlanningPlanComparisonService._document_reference(second),
            "input_changes": [], "metrics": {}, "read_only": True, "executed": False,
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
