"""Read-only readiness projection for saved seller planning documents."""

class PlanningPlanReadinessService:
    """Keep calculation, assumption freshness, and fact status independent."""

    VERSION = 1
    MAX_ITEMS = 10
    MAX_REASONS = 12

    def project(self, document_result, *, active_owner, active_store):
        document = (document_result or {}).get("document")
        if not isinstance(document, dict):
            return self._error("PLANNING_READINESS_DOCUMENT_UNAVAILABLE")
        if (
            str(document.get("owner_id") or "") != str(active_owner or "")
            or str(document.get("store_id") or "") != str(active_store or "")
        ):
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        if type(document.get("revision")) is not int or document["revision"] < 1:
            return self._error("PLANNING_READINESS_REVISION_INVALID")
        payload = document.get("payload")
        source_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(source_items, list) or not 1 <= len(source_items) <= self.MAX_ITEMS:
            return self._error("PLANNING_READINESS_ITEMS_INVALID")

        mix = payload.get("sales_mix")
        cross_docking_enabled = (
            isinstance(payload, dict) and payload.get("calculation_version") == 2
        )
        quantities = mix.get("quantities") if isinstance(mix, dict) else None
        if not isinstance(quantities, dict):
            quantities = {}
        item_rows = []
        math_ready = 0
        identity_ready = 0
        quantity_ready = 0
        for index, source in enumerate(source_items):
            if not isinstance(source, dict):
                return self._error("PLANNING_READINESS_ITEM_INVALID")
            identity = source.get("identity")
            identity = identity if isinstance(identity, dict) else {}
            row_id = str(source.get("row_id") or identity.get("sku") or "").strip()
            exact_identity = all(
                str(identity.get(field) or "").strip()
                for field in ("product_id", "offer_id", "sku")
            ) and str(identity.get("store_id") or "") == str(active_store or "")
            if exact_identity:
                identity_ready += 1
            projection = source.get("projection")
            projection = projection if isinstance(projection, dict) else {}
            status = projection.get("status")
            missing = self._reasons(projection.get("missing_inputs"))
            invalid = self._reasons(projection.get("invalid_inputs"))
            calculated = projection.get("available") is True and status == "READY" and not missing and not invalid
            if calculated:
                math_ready += 1
            quantity = quantities.get(row_id) if isinstance(mix, dict) else None
            quantity_confirmed = type(quantity) is int and 0 <= quantity <= 1_000_000
            if quantity_confirmed:
                quantity_ready += 1
            item_row = {
                "row_id": row_id,
                "label": self._label(identity, index),
                "identity_status": "CONFIRMED" if exact_identity else "IDENTITY_UNRESOLVED",
                "calculation_status": "READY" if calculated else self._projection_status(status),
                "missing_inputs": missing,
                "invalid_inputs": invalid,
                "quantity": quantity if quantity_confirmed else None,
                "quantity_status": "CONFIRMED" if quantity_confirmed else "UNKNOWN",
                "editable_field": next((field for field in missing + invalid if field in {
                    "price", "cost", "commission_rate", "advertising_rate",
                    "discount_points_rate", "logistics_per_unit", "last_mile_per_unit",
                    "acquiring_per_unit",
                }), None),
            }
            if cross_docking_enabled:
                sources = source.get("sources") if isinstance(source.get("sources"), dict) else {}
                evidence = sources.get("cross_docking")
                evidence = evidence if isinstance(evidence, dict) else {}
                rate = (source.get("inputs") or {}).get("cross_docking_per_unit")
                verified = (
                    evidence.get("evidence_complete") is True
                    and evidence.get("rate_available") is True
                    and evidence.get("applicable_to_sku") is True
                    and evidence.get("denominator_kind") == "DELIVERED_CROSSDOCK_UNITS"
                    and rate is not None
                    and str(rate) == str(evidence.get("amount_per_unit"))
                )
                item_row["cross_docking_status"] = "CONFIRMED" if verified else "UNAVAILABLE"
                item_row["cross_docking_reason"] = evidence.get("reason")
                item_row["cross_docking_source"] = {
                    key: evidence.get(key) for key in (
                        "method", "denominator_kind", "amount_per_unit", "expense_total",
                        "expense_by_sku", "supplied_units_sku", "supplied_units_store",
                        "date_from", "date_to", "days_complete", "days_expected",
                        "evidence_complete", "rate_available",
                    )
                }
            item_rows.append(item_row)

        mix_status = "NOT_STARTED" if not isinstance(mix, dict) else (
            "READY" if quantity_ready == len(source_items)
            and mix.get("confirmed") is True
            and isinstance(mix.get("period_label"), str)
            else "INCOMPLETE_INPUTS"
        )
        return {
            "error": False,
            "status": "PLANNING_READINESS_READY",
            "readiness_version": self.VERSION,
            "document_id": str(document.get("document_id") or ""),
            "revision": document["revision"],
            "current_revision": document.get("current_revision"),
            "plan_status": document.get("status"),
            "counts": {
                "items": len(item_rows),
                "identity_confirmed": identity_ready,
                "calculations_ready": math_ready,
                "quantities_confirmed": quantity_ready,
            },
            "calculation_status": "READY" if math_ready == len(item_rows) else "INCOMPLETE_INPUTS",
            "assumption_status": "HISTORICAL_ASSUMPTIONS",
            "fact_status": "NOT_CHECKED",
            "sales_mix_status": mix_status,
            "items": item_rows,
            "read_only": True,
            "executed": False,
        }

    @classmethod
    def _reasons(cls, values):
        if not isinstance(values, list):
            return []
        return list(dict.fromkeys(
            value[:80] for value in values[:cls.MAX_REASONS]
            if isinstance(value, str) and value.strip()
        ))

    @staticmethod
    def _projection_status(value):
        allowed = {
            "INCOMPLETE_INPUTS", "SOURCE_UNAVAILABLE", "SOURCE_STALE",
            "UNSUPPORTED_SCHEME", "TARGET_NOT_CONFIRMED", "BUDGET_EXHAUSTED",
        }
        return value if value in allowed else "UNAVAILABLE"

    @staticmethod
    def _label(identity, index):
        value = identity.get("product_name") or identity.get("offer_id") or identity.get("sku")
        return " ".join(str(value or f"Строка {index + 1}").replace("\r", " ").replace("\n", " ").split())[:60]

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
