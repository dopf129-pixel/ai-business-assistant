from copy import deepcopy


COMPARABLE_FIELDS = (
    "decision_type",
    "priority",
    "confidence",
    "reasons",
)


class ProductDecisionPersistenceApplicationService:

    def __init__(self, history_service):
        self.history_service = history_service

    def apply(self, readiness, full_preview_decision):
        source = deepcopy(dict(readiness or {}))
        decision = deepcopy(dict(full_preview_decision or {}))

        readiness_id = str(
            source.get("decision_persistence_application_readiness_id") or ""
        ).strip()
        authorization_id = str(
            source.get("decision_persistence_authorization_id") or ""
        ).strip()
        eligibility_id = str(
            source.get("decision_persistence_eligibility_id") or ""
        ).strip()
        review_id = str(source.get("decision_preview_review_id") or "").strip()
        delta_id = str(source.get("decision_preview_delta_id") or "").strip()
        preview_id = str(source.get("recompute_preview_id") or "").strip()
        draft_id = str(source.get("draft_id") or "").strip()
        sku = str(source.get("sku") or "").strip()

        if (
            not readiness_id
            or not authorization_id
            or not eligibility_id
            or not review_id
            or not delta_id
            or not preview_id
            or not draft_id
            or not sku
        ):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_CONTEXT_REQUIRED", source)
        if readiness_id != "product-decision-persistence-application-readiness:" + authorization_id:
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_READINESS_ID_MISMATCH", source)
        if authorization_id != "product-decision-persistence-authorization:" + eligibility_id:
            return self._blocked("DECISION_PERSISTENCE_AUTHORIZATION_ID_MISMATCH", source)
        if eligibility_id != "product-decision-persistence-eligibility:" + review_id:
            return self._blocked("DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH", source)
        if review_id != "product-decision-preview-review:" + delta_id:
            return self._blocked("DECISION_PREVIEW_REVIEW_ID_MISMATCH", source)
        if delta_id != "product-decision-preview-delta:" + preview_id:
            return self._blocked("DECISION_PREVIEW_DELTA_ID_MISMATCH", source)
        if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY":
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_STATUS_INVALID", source)
        if source.get("decision_persistence_allowed") is not True:
            return self._blocked("DECISION_PERSISTENCE_PERMISSION_REQUIRED", source)
        if source.get("decision_persistence_application_ready") is not True:
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_NOT_READY", source)
        if source.get("decision_persistence_application_started") is not False:
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_ALREADY_STARTED", source)
        if (
            source.get("persistent") is not False
            or source.get("product_decision_recomputed") is not True
            or source.get("product_decision_mutated") is not False
            or source.get("product_decision_persisted") is not False
            or source.get("ozon_mutation_called") is not False
            or source.get("execution_allowed") is not False
            or source.get("execution_ready") is not False
            or source.get("executed") is not False
        ):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_SAFETY_BOUNDARY_VIOLATION", source)

        compact_preview = source.get("ready_preview_decision")
        if not isinstance(compact_preview, dict):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_PREVIEW_REQUIRED", source)
        if str(compact_preview.get("sku") or "").strip() != sku:
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_PREVIEW_SKU_MISMATCH", source)

        if not decision or decision.get("error"):
            return self._blocked("DECISION_PERSISTENCE_FULL_PREVIEW_REQUIRED", source)
        if str(decision.get("sku") or "").strip() != sku:
            return self._blocked("DECISION_PERSISTENCE_FULL_PREVIEW_SKU_MISMATCH", source)
        if not decision.get("decision_type") or not decision.get("priority"):
            return self._blocked("DECISION_PERSISTENCE_FULL_PREVIEW_INVALID", source)
        if (
            decision.get("execution_allowed") is True
            or decision.get("execution_ready") is True
            or decision.get("executed") is True
            or decision.get("ozon_mutation_called") is True
        ):
            return self._blocked("DECISION_PERSISTENCE_FULL_PREVIEW_SAFETY_VIOLATION", source)

        for field in COMPARABLE_FIELDS:
            expected = self._normalized_value(field, compact_preview.get(field))
            actual = self._normalized_value(field, decision.get(field))
            if actual != expected:
                return self._blocked("DECISION_PERSISTENCE_FULL_PREVIEW_MISMATCH", source)

        changed_fields = list(source.get("ready_changed_fields") or [])
        changes = source.get("ready_changes")
        if not changed_fields or not isinstance(changes, dict):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_CHANGES_REQUIRED", source)
        if any(field not in COMPARABLE_FIELDS for field in changed_fields):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_CHANGES_UNSAFE", source)
        if set(changes) != set(changed_fields):
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_SET_MISMATCH", source)
        for field in changed_fields:
            change = changes.get(field)
            if not isinstance(change, dict) or "after" not in change:
                return self._blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_INVALID", source)
            expected = self._normalized_value(field, decision.get(field))
            actual = self._normalized_value(field, change.get("after"))
            if actual != expected:
                return self._blocked("DECISION_PERSISTENCE_APPLICATION_CHANGE_PREVIEW_MISMATCH", source)

        try:
            previous = self.history_service.latest(sku)
        except Exception:
            return self._blocked("DECISION_HISTORY_READ_FAILED", source)

        if previous is not None and (
            previous.get("decision_type"),
            previous.get("priority"),
        ) == (
            decision.get("decision_type"),
            decision.get("priority"),
        ):
            return self._blocked("DECISION_HISTORY_SIGNATURE_UNCHANGED", source)

        try:
            history_context = self.history_service.record(deepcopy(decision))
        except Exception:
            return self._blocked("DECISION_HISTORY_WRITE_FAILED", source)

        if not isinstance(history_context, dict) or history_context.get("decision_history_available") is not True:
            return self._blocked("DECISION_HISTORY_WRITE_NOT_CONFIRMED", source)

        return {
            "error": False,
            "status": "PRODUCT_DECISION_PERSISTENCE_APPLIED",
            "decision_persistence_application_id": "product-decision-persistence-application:" + readiness_id,
            "decision_persistence_application_readiness_id": readiness_id,
            "decision_persistence_authorization_id": authorization_id,
            "decision_persistence_eligibility_id": eligibility_id,
            "decision_preview_review_id": review_id,
            "decision_preview_delta_id": delta_id,
            "recompute_preview_id": preview_id,
            "draft_id": draft_id,
            "sku": sku,
            "decision_persistence_allowed": True,
            "decision_persistence_application_ready": True,
            "decision_persistence_application_started": True,
            "decision_persistence_application_completed": True,
            "history_context": deepcopy(history_context),
            "persisted_preview_decision": deepcopy(decision),
            "persistent": True,
            "product_decision_recomputed": True,
            "product_decision_mutated": False,
            "product_decision_persisted": True,
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

    @staticmethod
    def _blocked(code, source):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_BLOCKED",
            "decision_persistence_application_id": None,
            "decision_persistence_application_readiness_id": source.get(
                "decision_persistence_application_readiness_id"
            ),
            "decision_persistence_authorization_id": source.get(
                "decision_persistence_authorization_id"
            ),
            "decision_persistence_eligibility_id": source.get(
                "decision_persistence_eligibility_id"
            ),
            "decision_preview_review_id": source.get("decision_preview_review_id"),
            "decision_preview_delta_id": source.get("decision_preview_delta_id"),
            "recompute_preview_id": source.get("recompute_preview_id"),
            "draft_id": source.get("draft_id"),
            "sku": source.get("sku"),
            "decision_persistence_allowed": False,
            "decision_persistence_application_ready": False,
            "decision_persistence_application_started": False,
            "decision_persistence_application_completed": False,
            "history_context": None,
            "persisted_preview_decision": None,
            "persistent": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
