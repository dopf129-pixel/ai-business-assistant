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

ALLOWED_DECISION_TYPES = {
    "REPLENISH_HIGH_PRIORITY",
    "REPLENISH_NORMAL",
    "WATCH_LOW_MARGIN",
    "INVESTIGATE_LOW_PROFIT",
    "HOLD_STOCK",
    "INSUFFICIENT_DATA",
}
ALLOWED_PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "LOW", "NONE"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


class ProductDecisionPersistenceVerificationService:

    def __init__(self, history_service):
        self.history_service = history_service

    def verify(self, application):
        if not isinstance(application, dict):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_APPLICATION_INPUT_INVALID",
                {},
            )

        source = deepcopy(application)
        application_id = self._required_string(
            source.get("decision_persistence_application_id")
        )
        readiness_id = self._required_string(
            source.get("decision_persistence_application_readiness_id")
        )
        authorization_id = self._required_string(
            source.get("decision_persistence_authorization_id")
        )
        eligibility_id = self._required_string(
            source.get("decision_persistence_eligibility_id")
        )
        review_id = self._required_string(
            source.get("decision_preview_review_id")
        )
        delta_id = self._required_string(
            source.get("decision_preview_delta_id")
        )
        preview_id = self._required_string(source.get("recompute_preview_id"))
        draft_id = self._required_string(source.get("draft_id"))
        sku = self._required_string(source.get("sku"))

        if not all(
            (
                application_id,
                readiness_id,
                authorization_id,
                eligibility_id,
                review_id,
                delta_id,
                preview_id,
                draft_id,
                sku,
            )
        ):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_CONTEXT_REQUIRED",
                source,
            )
        if (
            application_id
            != "product-decision-persistence-application:" + readiness_id
        ):
            return self._blocked(
                "DECISION_PERSISTENCE_APPLICATION_ID_MISMATCH",
                source,
            )
        if (
            readiness_id
            != "product-decision-persistence-application-readiness:"
            + authorization_id
        ):
            return self._blocked(
                "DECISION_PERSISTENCE_APPLICATION_READINESS_ID_MISMATCH",
                source,
            )
        if (
            authorization_id
            != "product-decision-persistence-authorization:" + eligibility_id
        ):
            return self._blocked(
                "DECISION_PERSISTENCE_AUTHORIZATION_ID_MISMATCH",
                source,
            )
        if (
            eligibility_id
            != "product-decision-persistence-eligibility:" + review_id
        ):
            return self._blocked(
                "DECISION_PERSISTENCE_ELIGIBILITY_ID_MISMATCH",
                source,
            )
        if review_id != "product-decision-preview-review:" + delta_id:
            return self._blocked(
                "DECISION_PREVIEW_REVIEW_ID_MISMATCH",
                source,
            )
        if delta_id != "product-decision-preview-delta:" + preview_id:
            return self._blocked(
                "DECISION_PREVIEW_DELTA_ID_MISMATCH",
                source,
            )
        if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_APPLIED":
            return self._blocked(
                "DECISION_PERSISTENCE_APPLICATION_STATUS_INVALID",
                source,
            )
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
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_SAFETY_BOUNDARY_VIOLATION",
                source,
            )

        expected = source.get("persisted_preview_decision")
        if not isinstance(expected, dict):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_REQUIRED",
                source,
            )
        if "error" in expected and type(expected.get("error")) is not bool:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID",
                source,
            )
        if expected.get("error") is True:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_REQUIRED",
                source,
            )

        expected_sku = self._required_string(expected.get("sku"))
        if not expected_sku:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID",
                source,
            )
        if expected_sku != sku:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_SKU_MISMATCH",
                source,
            )
        if not self._decision_snapshot_semantics_valid(expected):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_EXPECTED_DECISION_INVALID",
                source,
            )

        history_context = source.get("history_context")
        if not isinstance(history_context, dict):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_CONTEXT_REQUIRED",
                source,
            )
        if history_context.get("decision_history_available") is not True:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_NOT_AVAILABLE",
                source,
            )
        expected_recorded_at = self._required_string(
            history_context.get("decision_recorded_at")
        )
        if not expected_recorded_at:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_REQUIRED",
                source,
            )

        persistence_receipt = source.get(
            "history_persistence_receipt"
        )
        receipt_error = self._commit_receipt_error(
            persistence_receipt,
            sku,
            history_context,
            expected_recorded_at,
        )
        if receipt_error is not None:
            return self._blocked(receipt_error, source)

        try:
            latest = self.history_service.latest(sku)
        except Exception:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_READ_FAILED",
                source,
            )

        if not isinstance(latest, dict):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_NOT_FOUND",
                source,
            )

        latest_sku = self._required_string(latest.get("sku"))
        if not latest_sku:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_SNAPSHOT_INVALID",
                source,
            )
        if latest_sku != sku:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_SKU_MISMATCH",
                source,
            )
        if not self._decision_snapshot_semantics_valid(latest):
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_SNAPSHOT_INVALID",
                source,
            )

        actual_recorded_at = self._required_string(latest.get("recorded_at"))
        if not actual_recorded_at:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_HISTORY_SNAPSHOT_INVALID",
                source,
            )
        if actual_recorded_at != expected_recorded_at:
            return self._blocked(
                "DECISION_PERSISTENCE_VERIFICATION_RECORDED_AT_MISMATCH",
                source,
            )

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

        verification_id = (
            "product-decision-persistence-verification:" + application_id
        )
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
            "verified_recorded_at": actual_recorded_at,
            "verified_snapshot": deepcopy(latest),
            "mismatched_fields": [],
            "externally_verified": False,
            "persistent": True,
            "product_decision_recomputed": True,
            "product_decision_mutated": False,
            "product_decision_persisted": True,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @classmethod
    def _commit_receipt_error(
        cls,
        receipt,
        sku,
        history_context,
        expected_recorded_at,
    ):
        if (
            not isinstance(receipt, dict)
            or receipt.get("error") is not False
            or receipt.get("saved") is not True
            or receipt.get("persistence_state") != "COMMITTED"
            or cls._required_string(receipt.get("sku")) != sku
        ):
            return (
                "DECISION_PERSISTENCE_VERIFICATION_COMMIT_RECEIPT_REQUIRED"
            )

        recorded_at = cls._required_string(
            receipt.get("decision_recorded_at")
        )
        history_count = receipt.get("decision_history_count")
        receipt_context = receipt.get("history_context")

        if (
            recorded_at != expected_recorded_at
            or type(history_count) is not int
            or history_count < 1
            or not isinstance(receipt_context, dict)
            or receipt_context != history_context
            or receipt_context.get("decision_recorded_at")
            != expected_recorded_at
            or receipt_context.get("decision_history_count")
            != history_count
        ):
            return (
                "DECISION_PERSISTENCE_VERIFICATION_COMMIT_RECEIPT_INVALID"
            )

        return None

    @classmethod
    def _decision_snapshot_semantics_valid(cls, snapshot):
        decision_type = cls._required_string(snapshot.get("decision_type"))
        priority = cls._required_string(snapshot.get("priority"))
        confidence = cls._required_string(snapshot.get("confidence"))
        reasons = snapshot.get("reasons")

        return (
            decision_type in ALLOWED_DECISION_TYPES
            and priority in ALLOWED_PRIORITIES
            and confidence in ALLOWED_CONFIDENCE
            and isinstance(reasons, list)
            and len(reasons) > 0
            and all(cls._required_string(reason) for reason in reasons)
        )

    @staticmethod
    def _normalized_value(field, value):
        if field == "reasons":
            return deepcopy(value)
        return value

    @staticmethod
    def _required_string(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _blocked(code, source):
        safe_source = source if isinstance(source, dict) else {}
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_DECISION_PERSISTENCE_VERIFICATION_BLOCKED",
            "decision_persistence_verification_id": None,
            "decision_persistence_application_id": safe_source.get(
                "decision_persistence_application_id"
            ),
            "decision_persistence_application_readiness_id": safe_source.get(
                "decision_persistence_application_readiness_id"
            ),
            "decision_persistence_authorization_id": safe_source.get(
                "decision_persistence_authorization_id"
            ),
            "decision_persistence_eligibility_id": safe_source.get(
                "decision_persistence_eligibility_id"
            ),
            "decision_preview_review_id": safe_source.get(
                "decision_preview_review_id"
            ),
            "decision_preview_delta_id": safe_source.get(
                "decision_preview_delta_id"
            ),
            "recompute_preview_id": safe_source.get("recompute_preview_id"),
            "draft_id": safe_source.get("draft_id"),
            "sku": safe_source.get("sku"),
            "decision_persistence_verified": False,
            "verified_recorded_at": None,
            "verified_snapshot": None,
            "mismatched_fields": [],
            "externally_verified": False,
            "persistent": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
