from copy import deepcopy


SNAPSHOT_FIELD_MAP = {
    "sku": "sku",
    "product_id": "product_id",
    "decision_type": "decision_type",
    "priority": "priority",
    "confidence": "confidence",
    "reasons": "reasons",
    "sales_velocity": "sales_velocity",
    "current_stock": "current_stock",
    "days_of_stock": "days_of_stock",
    "decision_profit_per_unit": "profit_per_unit",
    "decision_margin_percent": "margin_percent",
    "economics_basis": "economics_basis",
}


class ProductDecisionPersistenceVerificationService:

    def __init__(self, history_service):
        self.history_service = history_service

    def verify(self, application):
        source = deepcopy(dict(application or {}))
        application_id = str(
            source.get("decision_persistence_application_id") or ""
        ).strip()
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

        if not all((
            application_id,
            readiness_id,
            authorization_id,
            eligibility_id,
            review_id,
            delta_id,
            preview_id,
            draft_id,
            sku,
        )):
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_CONTEXT_REQUIRED", source)
        if application_id != "product-decision-persistence-application:" + readiness_id:
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_ID_MISMATCH", source)
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
        if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_APPLIED":
            return self._blocked("DECISION_PERSISTENCE_APPLICATION_STATUS_INVALID", source)
        if (
            source.get("decision_persistence_allowed") is not True
            or source.get("decision_persistence_application_ready") is not True
            or source.get("decision_persistence_application_started") is not True
            or source.get("decision_persistence_application_completed") is not True
            or source.get("persistent") is not True
            or source.get("product_decision_recomputed") is not True
            or source.get("product_decision_mutated") is not False
            or source.get("product_decision_persisted") is not True
            or source.get("ozon_mutation_called") is not False
            or source.get("execution_allowed") is not False
            or source.get("execution_ready") is not False
            or source.get("executed") is not False
        ):
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_SAFETY_BOUNDARY_VIOLATION", source)

        expected = source.get("persisted_preview_decision")
        if not isinstance(expected, dict) or expected.get("error"):
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_REQUIRED", source)
        if str(expected.get("sku") or "").strip() != sku:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_EXPECTED_SKU_MISMATCH", source)

        history_context = source.get("history_context")
        if not isinstance(history_context, dict):
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_HISTORY_CONTEXT_REQUIRED", source)
        if history_context.get("decision_history_available") is not True:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_HISTORY_NOT_AVAILABLE", source)
        expected_recorded_at = history_context.get("decision_recorded_at")
        if not expected_recorded_at:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_REQUIRED", source)

        try:
            latest = self.history_service.latest(sku)
        except Exception:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_READ_FAILED", source)

        if not isinstance(latest, dict):
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_HISTORY_NOT_FOUND", source)
        if str(latest.get("sku") or "").strip() != sku:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_HISTORY_SKU_MISMATCH", source)
        if latest.get("recorded_at") != expected_recorded_at:
            return self._blocked("DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_MISMATCH", source)

        mismatches = []
        for decision_field, snapshot_field in SNAPSHOT_FIELD_MAP.items():
            expected_value = self._normalized_value(
                decision_field,
                expected.get(decision_field),
            )
            actual_value = self._normalized_value(
                decision_field,
                latest.get(snapshot_field),
            )
            if actual_value != expected_value:
                mismatches.append(decision_field)

        if mismatches:
            result = self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_SNAPSHOT_MISMATCH",
                source,
            )
            result["mismatched_fields"] = mismatches
            return result

        verification_id = "product-decision-persistence-verification:" + application_id
        return {
            "error": False,
            "status": "PRODUCT_DECISION_PERSISTENCE_VERIFIED",
            "decision_persistence_verification_id": verification_id,
            "decision_persistence_application_id": application_id,
            "decision_persistence_application_readiness_id": readiness_id,
            "decision_persistence_authorization_id": authorization_id,
            "decision_persistence_eligibility_id": eligibility_id,
            "decision_preview_review_id": review_id,
            "decision_preview_delta_id": delta_id,
            "recompute_preview_id": preview_id,
            "draft_id": draft_id,
            "sku": sku,
            "decision_persistence_verified": True,
            "verified_recorded_at": latest.get("recorded_at"),
            "verified_snapshot": deepcopy(latest),
            "mismatched_fields": [],
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
            "status": "PRODUCT_DECISION_PERSISTENCE_VERIFICATION_BLOCKED",
            "decision_persistence_verification_id": None,
            "decision_persistence_application_id": source.get(
                "decision_persistence_application_id"
            ),
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
            "decision_persistence_verified": False,
            "verified_recorded_at": None,
            "verified_snapshot": None,
            "mismatched_fields": [],
            "persistent": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
