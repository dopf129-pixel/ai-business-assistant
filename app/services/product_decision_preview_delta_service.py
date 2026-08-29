from copy import deepcopy


COMPARABLE_FIELDS = (
    "decision_type",
    "priority",
    "confidence",
    "reasons",
)


class ProductDecisionPreviewDeltaService:

    def compare(self, current_decision, recompute_preview):
        current = deepcopy(dict(current_decision or {}))
        preview = deepcopy(dict(recompute_preview or {}))

        preview_id = str(preview.get("recompute_preview_id") or "").strip()
        authorization_id = str(preview.get("recompute_authorization_id") or "").strip()
        draft_id = str(preview.get("draft_id") or "").strip()
        sku = str(preview.get("sku") or "").strip()

        if not preview_id or not authorization_id or not draft_id or not sku:
            return self._blocked("DECISION_PREVIEW_DELTA_CONTEXT_REQUIRED", preview)
        if preview_id != "product-decision-recompute-preview:" + authorization_id:
            return self._blocked("RECOMPUTE_PREVIEW_ID_MISMATCH", preview)
        if preview.get("status") != "PRODUCT_DECISION_RECOMPUTE_PREVIEW_READY":
            return self._blocked("RECOMPUTE_PREVIEW_STATUS_INVALID", preview)
        if preview.get("recompute_preview_computed") is not True:
            return self._blocked("RECOMPUTE_PREVIEW_NOT_COMPUTED", preview)
        if preview.get("product_decision_recomputed") is not True:
            return self._blocked("PRODUCT_DECISION_NOT_RECOMPUTED", preview)
        if (
            preview.get("persistent") is not False
            or preview.get("task_draft_mutated") is not False
            or preview.get("product_decision_mutated") is not False
            or preview.get("product_decision_persisted") is not False
            or preview.get("ozon_mutation_called") is not False
            or preview.get("execution_allowed") is not False
            or preview.get("execution_ready") is not False
            or preview.get("executed") is not False
        ):
            return self._blocked("DECISION_PREVIEW_DELTA_SAFETY_BOUNDARY_VIOLATION", preview)

        preview_decision = preview.get("preview_decision")
        if not isinstance(preview_decision, dict):
            return self._blocked("PREVIEW_DECISION_REQUIRED", preview)
        if str(preview_decision.get("sku") or "").strip() != sku:
            return self._blocked("PREVIEW_DECISION_SKU_MISMATCH", preview)

        if not current:
            return self._blocked("CURRENT_DECISION_REQUIRED", preview)
        if str(current.get("sku") or "").strip() != sku:
            return self._blocked("CURRENT_DECISION_SKU_MISMATCH", preview)
        if not current.get("decision_type") or not current.get("priority"):
            return self._blocked("CURRENT_DECISION_INVALID", preview)

        changes = {}
        changed_fields = []
        for field in COMPARABLE_FIELDS:
            current_value = self._normalized_value(field, current.get(field))
            preview_value = self._normalized_value(field, preview_decision.get(field))
            if current_value != preview_value:
                changed_fields.append(field)
                changes[field] = {
                    "before": deepcopy(current_value),
                    "after": deepcopy(preview_value),
                }

        return {
            "error": False,
            "status": "PRODUCT_DECISION_PREVIEW_DELTA_READY",
            "decision_preview_delta_id": "product-decision-preview-delta:" + preview_id,
            "recompute_preview_id": preview_id,
            "recompute_authorization_id": authorization_id,
            "draft_id": draft_id,
            "sku": sku,
            "decision_changed": bool(changed_fields),
            "changed_fields": changed_fields,
            "changed_field_count": len(changed_fields),
            "changes": changes,
            "current_decision": self._decision_view(current),
            "preview_decision": self._decision_view(preview_decision),
            "persistent": False,
            "task_draft_mutated": False,
            "product_decision_recomputed": True,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @staticmethod
    def _normalized_value(field, value):
        if field == "reasons":
            return list(value or [])
        return value

    @classmethod
    def _decision_view(cls, decision):
        return {
            "sku": decision.get("sku"),
            **{
                field: deepcopy(cls._normalized_value(field, decision.get(field)))
                for field in COMPARABLE_FIELDS
            },
        }

    @staticmethod
    def _blocked(code, preview):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_DECISION_PREVIEW_DELTA_BLOCKED",
            "decision_preview_delta_id": None,
            "recompute_preview_id": preview.get("recompute_preview_id"),
            "recompute_authorization_id": preview.get("recompute_authorization_id"),
            "draft_id": preview.get("draft_id"),
            "sku": preview.get("sku"),
            "decision_changed": False,
            "changed_fields": [],
            "changed_field_count": 0,
            "changes": {},
            "current_decision": None,
            "preview_decision": None,
            "persistent": False,
            "task_draft_mutated": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
