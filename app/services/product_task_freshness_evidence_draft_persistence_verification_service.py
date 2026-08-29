from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


class ProductTaskFreshnessEvidenceDraftPersistenceVerificationService:

    def __init__(self, storage_service):
        self.storage_service = storage_service

    def verify(self, readiness, persistence_result):
        source = dict(readiness or {})
        persistence = dict(persistence_result or {})
        draft_id = str(source.get("draft_id") or "").strip()
        sku = str(source.get("sku") or "").strip()
        if not draft_id or not sku:
            return self._blocked("DURABLE_VERIFICATION_CONTEXT_REQUIRED", source)

        if persistence.get("persisted") is not True:
            return self._blocked("DURABLE_PERSISTENCE_NOT_CONFIRMED", source)
        if persistence.get("draft_id") != source.get("draft_id"):
            return self._blocked("DURABLE_PERSISTENCE_DRAFT_ID_MISMATCH", source)
        if persistence.get("sku") != source.get("sku"):
            return self._blocked("DURABLE_PERSISTENCE_SKU_MISMATCH", source)
        if persistence.get("execution_allowed") is not False or persistence.get("execution_ready") is not False or persistence.get("executed") is not False:
            return self._blocked("DURABLE_PERSISTENCE_EXECUTION_BOUNDARY_VIOLATION", source)

        expected = self._safe_evidence(source.get("readiness_evidence"))
        if not expected:
            return self._blocked("DURABLE_VERIFICATION_EVIDENCE_REQUIRED", source)
        if expected != source.get("readiness_evidence"):
            return self._blocked("DURABLE_VERIFICATION_EVIDENCE_UNSAFE", source)
        if source.get("readiness_evidence_count") != len(expected):
            return self._blocked("DURABLE_VERIFICATION_EVIDENCE_COUNT_MISMATCH", source)

        records = self.storage_service.load()
        matches = [
            record for record in records
            if str(record.get("draft_id") or "") == draft_id
            and str(record.get("sku") or "") == sku
        ]
        if not matches:
            return self._blocked("DURABLE_VERIFICATION_DRAFT_NOT_FOUND", source)
        if len(matches) != 1:
            return self._blocked("DURABLE_VERIFICATION_DRAFT_AMBIGUOUS", source)

        persisted_draft = deepcopy(matches[0])
        actual = {field: deepcopy(persisted_draft.get(field)) for field in expected}
        mismatched_fields = [field for field, value in expected.items() if actual.get(field) != value]
        if mismatched_fields:
            result = self._blocked("DURABLE_VERIFICATION_EVIDENCE_MISMATCH", source)
            result["mismatched_fields"] = mismatched_fields
            result["verified_evidence"] = actual
            return result

        return {
            "error": False,
            "status": "FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_VERIFIED",
            "draft_id": draft_id,
            "sku": sku,
            "verified": True,
            "verified_evidence": actual,
            "verified_evidence_count": len(actual),
            "mismatched_fields": [],
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @staticmethod
    def _safe_evidence(values):
        if not isinstance(values, dict):
            return {}
        return {
            field: deepcopy(value)
            for field, value in values.items()
            if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
        }

    @staticmethod
    def _blocked(code, source):
        return {
            "error": True,
            "code": code,
            "status": "FRESHNESS_EVIDENCE_DURABLE_VERIFICATION_BLOCKED",
            "draft_id": source.get("draft_id"),
            "sku": source.get("sku"),
            "verified": False,
            "verified_evidence": {},
            "verified_evidence_count": 0,
            "mismatched_fields": [],
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
